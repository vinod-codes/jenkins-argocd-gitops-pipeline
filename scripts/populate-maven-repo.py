#!/usr/bin/env python3
"""Populate a local Maven repository by resolving artifacts with curl.

Why this exists: in this sandbox, Java cannot fetch anything through the
egress proxy (the proxy completes the TLS handshake and then drops Java's
connections for every host), while curl works fine. So this script does the
dependency resolution that Maven would normally do over the network:
download each POM with curl, read its dependencies, and download every
transitive jar + pom into the local repo layout. Maven is then run in
offline mode (-o) against that populated repo.

Scope rules (matching Maven for this project):
  - Provided/system scope dependencies are skipped: they are supplied by
    Maven core itself at runtime.
  - Optional dependencies are skipped.
  - Import-scope dependencyManagement entries (BOMs) are followed so
    managed versions resolve.
  - First-seen version wins (BFS from the seeds approximates Maven's
    nearest-definition rule for this small tree).
"""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import deque

CENTRAL = "https://repo.maven.apache.org/maven2"
LOCAL = os.path.expanduser("~/workspace/.m2")
NS = "{http://maven.apache.org/POM/4.0.0}"

SEEDS = [
    ("org.apache.maven.plugins", "maven-clean-plugin", "3.2.0"),
    ("org.apache.maven.plugins", "maven-resources-plugin", "3.3.1"),
    ("org.apache.maven.plugins", "maven-compiler-plugin", "3.11.0"),
    ("org.apache.maven.plugins", "maven-surefire-plugin", "3.0.0"),
    ("org.apache.maven.plugins", "maven-jar-plugin", "3.3.0"),
    ("org.junit.jupiter", "junit-jupiter-api", "5.11.3"),
    ("org.junit.jupiter", "junit-jupiter-engine", "5.11.3"),
    # Spring Boot application (adapted from the reference project)
    ("org.springframework.boot", "spring-boot-starter-parent", "3.4.1"),
    ("org.springframework.boot", "spring-boot-starter-web", "3.4.1"),
    ("org.springframework.boot", "spring-boot-starter-thymeleaf", "3.4.1"),
    ("org.springframework.boot", "spring-boot-starter-test", "3.4.1"),
    ("org.springframework.boot", "spring-boot-maven-plugin", "3.4.1"),
    ("org.sonarsource.scanner.maven", "sonar-maven-plugin", "4.0.0.4121"),
]


def artifact_dir(g, a, v):
    return os.path.join(LOCAL, *g.split("."), a, v)


def curl(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    r = subprocess.run(
        ["curl", "-fsSL", "--max-time", "60", "-o", dest, url],
        capture_output=True, text=True)
    if r.returncode != 0:
        if os.path.exists(dest):
            os.remove(dest)
        return False
    return True


def fetch_pom(g, a, v):
    dest = os.path.join(artifact_dir(g, a, v), f"{a}-{v}.pom")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    url = f"{CENTRAL}/{'/'.join(g.split('.'))}/{a}/{v}/{a}-{v}.pom"
    if not curl(url, dest):
        print(f"  !! POM not found: {g}:{a}:{v}")
        return None
    return dest


def fetch_jar(g, a, v):
    dest = os.path.join(artifact_dir(g, a, v), f"{a}-{v}.jar")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    url = f"{CENTRAL}/{'/'.join(g.split('.'))}/{a}/{v}/{a}-{v}.jar"
    if not curl(url, dest):
        # Some artifacts are pom-only (no jar). That is fine.
        print(f"  (no jar for {g}:{a}:{v})")
        return None
    return dest


def text(elem, tag):
    child = elem.find(f"{NS}{tag}")
    return child.text.strip() if child is not None and child.text else None


def substitute(value, props):
    if value is None:
        return None
    for _ in range(10):
        m = re.search(r"\$\{([^}]+)\}", value)
        if not m:
            return value
        key = m.group(1)
        if key in props:
            value = value.replace("${" + key + "}", props[key])
        else:
            return None
    return value


def parse_pom(path):
    # Some old POMs on Central contain undefined XML entities (e.g. &copy;)
    # or a DOCTYPE with entity declarations, which ElementTree rejects.
    # Sanitize those away (they only ever appear in free-text fields) and
    # skip a POM entirely if it still will not parse.
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        try:
            raw = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return None
        raw = re.sub(r"<!DOCTYPE[^>]*(\[[^\]]*\])?>", "", raw, flags=re.S)
        raw = re.sub(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)"
            r"[A-Za-z][A-Za-z0-9]*;",
            "", raw)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            print(f"  !! unparseable POM, skipping: {path} ({e})")
            return None
        tree = ET.ElementTree(root)
    root = tree.getroot()
    props = {}
    props_elem = root.find(f"{NS}properties")
    if props_elem is not None:
        for p in props_elem:
            if p.tag.startswith(NS) and p.text:
                props[p.tag[len(NS):]] = p.text.strip()
    parent = root.find(f"{NS}parent")
    parent_ref = None
    if parent is not None:
        parent_ref = (text(parent, "groupId"), text(parent, "artifactId"),
                      text(parent, "version"))
    deps = []
    deps_elem = root.find(f"{NS}dependencies")
    if deps_elem is not None:
        for d in deps_elem.findall(f"{NS}dependency"):
            deps.append({
                "groupId": text(d, "groupId"),
                "artifactId": text(d, "artifactId"),
                "version": text(d, "version"),
                "scope": text(d, "scope") or "compile",
                "optional": (text(d, "optional") or "false").lower() == "true",
            })
    mgmt = {}
    imports = []
    mgmt_elem = root.find(f"{NS}dependencyManagement")
    if mgmt_elem is not None:
        mgmt_deps = mgmt_elem.find(f"{NS}dependencies")
        if mgmt_deps is not None:
            for d in mgmt_deps.findall(f"{NS}dependency"):
                g = text(d, "groupId")
                a = text(d, "artifactId")
                v = text(d, "version")
                scope = text(d, "scope") or ""
                if scope == "import" and v:
                    imports.append((g, a, v))
                elif v:
                    mgmt[(g, a)] = v
    return {"props": props, "parent": parent_ref, "deps": deps,
            "mgmt": mgmt, "imports": imports}


def effective_pom(g, a, v, depth=0):
    """Merge a POM with its parent chain (parent first, child overrides)."""
    if depth > 8:
        return None
    path = fetch_pom(g, a, v)
    if path is None:
        return None
    pom = parse_pom(path)
    if pom is None:
        return None
    props = dict(pom["props"])
    mgmt = dict(pom["mgmt"])
    imports = list(pom["imports"])
    deps = list(pom["deps"])
    if pom["parent"]:
        pg, pa, pv = pom["parent"]
        parent = effective_pom(pg, pa, pv, depth + 1)
        if parent:
            merged_props = dict(parent["props"])
            merged_props.update(props)
            props = merged_props
            merged_mgmt = dict(parent["mgmt"])
            merged_mgmt.update(mgmt)
            mgmt = merged_mgmt
            imports = list(parent["imports"]) + imports
    # Follow BOM imports for managed versions.
    for ig, ia, iv in imports:
        iv = substitute(iv, props) or iv
        bom_path = fetch_pom(ig, ia, iv)
        if bom_path:
            bom = parse_pom(bom_path)
            if bom is None:
                continue
            for key, val in bom["mgmt"].items():
                mgmt.setdefault(key, val)
            props.update({k: v for k, v in bom["props"].items()
                          if k not in props})
    return {"props": props, "mgmt": mgmt, "deps": deps, "imports": imports}


def main():
    seen = set()
    queue = deque(SEEDS)
    fetched_jars = 0
    fetched_poms = 0
    while queue:
        g, a, v = queue.popleft()
        key = (g, a)
        if key in seen:
            continue
        seen.add(key)
        print(f"== {g}:{a}:{v}")
        pom = effective_pom(g, a, v)
        if pom is None:
            continue
        fetched_poms += 1
        if fetch_jar(g, a, v):
            fetched_jars += 1
        props = dict(pom["props"])
        props["project.version"] = v
        props["version"] = v
        for dep in pom["deps"]:
            if dep["optional"]:
                continue
            if dep["scope"] in ("provided", "system"):
                continue
            dg, da = dep["groupId"], dep["artifactId"]
            if dg is None or da is None:
                continue
            dv = dep["version"]
            if dv is None:
                dv = pom["mgmt"].get((dg, da))
            if dv is None:
                print(f"  !! no version for {dg}:{da} (from {g}:{a})")
                continue
            dv = substitute(dv, props)
            if dv is None:
                print(f"  !! unresolvable version for {dg}:{da}")
                continue
            dg = substitute(dg, props) or dg
            da = substitute(da, props) or da
            if (dg, da) not in seen:
                queue.append((dg, da, dv))
    print(f"\nDone: {len(seen)} artifacts, {fetched_jars} jars, "
          f"{fetched_poms} POMs resolved.")


if __name__ == "__main__":
    main()
