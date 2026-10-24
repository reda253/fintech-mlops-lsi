# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jdk-alpine AS build
WORKDIR /workspace
RUN apk add --no-cache curl
COPY . .
RUN sed -i 's/\r$//' mvnw
RUN --mount=type=cache,target=/root/.m2 \
    sh ./mvnw -B -pl auth-service -am verify
RUN cp auth-service/target/auth-service-*.jar application.jar \
    && java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:21-jre-alpine AS runtime
RUN addgroup -S -g 10001 fintech \
    && adduser -S -D -H -u 10001 -G fintech fintech
WORKDIR /app
COPY --from=build --chown=10001:10001 /workspace/extracted/dependencies/ ./
COPY --from=build --chown=10001:10001 /workspace/extracted/spring-boot-loader/ ./
COPY --from=build --chown=10001:10001 /workspace/extracted/snapshot-dependencies/ ./
COPY --from=build --chown=10001:10001 /workspace/extracted/application/ ./
USER 10001:10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70"
EXPOSE 8081
ENTRYPOINT ["java", "-jar", "application.jar"]
