# syntax=docker/dockerfile:1
# Multi-stage build: Maven builds the jar, then a slim JRE image runs it.
# Build with: docker build -t docker.io/vinodg/gitops-demo:1.0.0 .

FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY app/pom.xml app/pom.xml
COPY app/src app/src
RUN mvn -f app/pom.xml -q clean package -DskipTests

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app
COPY --from=build /src/app/target/gitops-demo-1.0.0.jar app.jar
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8080/health || exit 1
ENTRYPOINT ["java", "-jar", "app.jar"]
