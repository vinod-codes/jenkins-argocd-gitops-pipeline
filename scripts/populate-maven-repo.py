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
  - Test-scope dependencies are skipped: Maven never resolves a
    dependency's test-scoped dependencies onto any classpath (the
    project's own test libraries arrive through spring-boot-starter-test,
    whose dependencies are compile-scoped in its own POM). Resolving
    them here only dragged in stale versions of artifacts the project
    also needs (Mockito, JUnit, Logback) and poisoned the version map.
  - Optional dependencies are skipped for the project's own tree
    (Maven does not put them on the project classpath), but included
    for plugin realms: Maven resolves a plugin's optional dependencies
    into its realm (e.g. spring-boot-maven-plugin marks
    maven-shade-plugin optional, yet the repackage goal needs it).
  - Import-scope dependencyManagement entries (BOMs) are followed so
    managed versions resolve.
  - Every distinct (groupId, artifactId, version) encountered is
    downloaded: Maven resolves the project classpath and each plugin's
    realm separately, so different versions of one artifact can both be
    needed (e.g. asm 9.8 for the compiler plugin, asm 9.7.1 for the
    project's tests). First-seen-wins used to drop the second version
    and break the offline build.
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
    ("org.apache.maven.plugins", "maven-clean-plugin", "3.4.1"),
    ("org.apache.maven.plugins", "maven-resources-plugin", "3.3.1"),
    ("org.apache.maven.plugins", "maven-compiler-plugin", "3.14.1"),
    ("org.apache.maven.plugins", "maven-surefire-plugin", "3.5.6"),
    ("org.apache.maven.plugins", "maven-jar-plugin", "3.4.2"),
    # Surefire resolves its JUnit Platform provider dynamically at runtime
    # (it is not a dependency in the plugin POM), so seed it explicitly.
    ("org.apache.maven.surefire", "surefire-junit-platform", "3.5.6"),
    ("org.junit.jupiter", "junit-jupiter-api", "5.12.2"),
    ("org.junit.jupiter", "junit-jupiter-engine", "5.12.2"),
    # Spring Boot application (adapted from the reference project)
    ("org.springframework.boot", "spring-boot-starter-parent", "3.5.16"),
    ("org.springframework.boot", "spring-boot-starter-web", "3.5.16"),
    ("org.springframework.boot", "spring-boot-starter-thymeleaf", "3.5.16"),
    ("org.springframework.boot", "spring-boot-starter-test", "3.5.16"),
    ("org.springframework.boot", "spring-boot-maven-plugin", "3.5.16"),
    ("org.sonarsource.scanner.maven", "sonar-maven-plugin", "5.9.0.7382"),
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
    # Follow BOM imports for managed versions. Use effective_pom (not a
    # bare fetch+parse) so each imported BOM's own parent chain is also
    # downloaded: Maven builds the full model of an imported BOM, and a
    # missing parent POM (e.g. artemis-project for artemis-bom) fails the
    # build even though the BOM itself is present.
    for ig, ia, iv in imports:
        iv = substitute(iv, props) or iv
        bom = effective_pom(ig, ia, iv, depth + 1)
        if bom is None:
            continue
        for key, val in bom["mgmt"].items():
            mgmt.setdefault(key, val)
        props.update({k: v for k, v in bom["props"].items()
                      if k not in props})
    return {"props": props, "mgmt": mgmt, "deps": deps, "imports": imports}


def resolve(seeds, prefer_fallback, include_optional, fallback_mgmt,
            fallback_props, seen):
    """Resolve one BFS pass, downloading every distinct artifact version
    encountered. When prefer_fallback is true, the project's
    dependencyManagement wins over a transitive POM's declared version,
    matching Maven's nearest definition: e.g. Mockito declares
    byte-buddy 1.15.11, but Spring Boot manages 1.17.8, so Maven uses
    1.17.8 on the project classpath; and Maven likewise wants the
    Boot-managed junit-platform-launcher 1.12.2 for the surefire
    provider, not the 1.14.2 from surefire's own management. When
    prefer_fallback is false, the project's management is only a last
    resort for a version that is missing entirely."""
    queue = deque(seeds)
    fetched_jars = 0
    fetched_poms = 0
    while queue:
        g, a, v = queue.popleft()
        key = (g, a, v)
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
            if dep["optional"] and not include_optional:
                continue
            if dep["scope"] in ("provided", "system", "test"):
                continue
            dg, da = dep["groupId"], dep["artifactId"]
            if dg is None or da is None:
                continue
            dv = None
            if prefer_fallback:
                dv = fallback_mgmt.get((dg, da))
            if dv is None:
                dv = dep["version"]
            if dv is None:
                dv = pom["mgmt"].get((dg, da))
            if dv is None and not prefer_fallback:
                dv = fallback_mgmt.get((dg, da))
            if dv is None:
                print(f"  !! no version for {dg}:{da} (from {g}:{a})")
                continue
            merged_props = dict(fallback_props)
            merged_props.update(props)
            dv = substitute(dv, merged_props)
            if dv is None:
                print(f"  !! unresolvable version for {dg}:{da}")
                continue
            dg = substitute(dg, props) or dg
            da = substitute(da, props) or da
            if (dg, da, dv) not in seen:
                queue.append((dg, da, dv))
            # Also enqueue the project-managed version when it differs:
            # Maven resolves a plugin's own dependencies from the
            # plugin's POM, but artifacts resolved in the project
            # context (e.g. the surefire provider) use the project's
            # dependencyManagement instead. Downloading both versions
            # covers both realms.
            fb_raw = fallback_mgmt.get((dg, da))
            fb = substitute(fb_raw, merged_props) if fb_raw else None
            if fb and fb != dv and (dg, da, fb) not in seen:
                queue.append((dg, da, fb))
    return fetched_jars, fetched_poms


def main():
    # Fallback dependencyManagement for this project: Spring Boot 3.5.x
    # starter POMs are published flattened, with explicit versions and no
    # <parent> element, so a transitive dependency that carries no version
    # of its own cannot be resolved standalone the way Maven resolves it
    # under this project's own dependencyManagement. Resolve such
    # dependencies against the Boot parent's managed versions instead.
    root = effective_pom("org.springframework.boot",
                         "spring-boot-starter-parent", "3.5.16")
    fallback_mgmt = root["mgmt"] if root else {}
    fallback_props = root["props"] if root else {}
    seen = set()
    # Pass 1: the application's own tree (the starters and the JUnit
    # seeds). The project's dependencyManagement wins here, as Maven
    # resolves it. spring-boot-maven-plugin is a plugin, so it belongs
    # to pass 2 even though it shares the Boot groupId.
    project_seeds = [s for s in SEEDS
                     if s[1].startswith("spring-boot-starter")
                     or s[0] == "org.junit.jupiter"]
    jars, poms = resolve(project_seeds, True, False, fallback_mgmt,
                         fallback_props, seen)
    # Pass 2: the Maven plugins' own realms. Each plugin's POM wins
    # here: a plugin's own dependencies resolve from the plugin's
    # dependencyManagement, not the project's (e.g. the Boot plugin
    # needs maven-shade-plugin 3.6.0 even though Boot manages 3.5.0).
    # Artifacts the project also manages get both versions enqueued by
    # resolve(), so project-context resolution (e.g. the surefire
    # provider, which Maven wants at the Boot-managed 1.12.2, not the
    # 1.14.2 from surefire's own management) is covered too.
    plugin_seeds = [s for s in SEEDS if s not in project_seeds]
    jars2, poms2 = resolve(plugin_seeds, False, True, fallback_mgmt,
                           fallback_props, seen)
    print(f"\nDone: {len(seen)} artifacts, {jars + jars2} jars, "
          f"{poms + poms2} POMs resolved.")


if __name__ == "__main__":
    main()
