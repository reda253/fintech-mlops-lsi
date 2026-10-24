"""Check a Java image contract without opening ports or connecting to dependencies."""

import argparse
import json
import re
import subprocess


def verify_config(config, port):
    if config.get("User") != "10001:10001":
        raise AssertionError("Expected image USER 10001:10001")
    if config.get("WorkingDir") != "/app":
        raise AssertionError("Expected working directory /app")
    if config.get("Entrypoint") != ["java", "-jar", "application.jar"]:
        raise AssertionError("Unexpected Spring Boot entrypoint")
    if f"{port}/tcp" not in (config.get("ExposedPorts") or {}):
        raise AssertionError(f"Expected internal port {port}/tcp")
    environment = dict(item.split("=", 1) for item in config.get("Env", []) if "=" in item)
    if environment.get("JAVA_TOOL_OPTIONS") != "-XX:MaxRAMPercentage=70":
        raise AssertionError("Expected container heap sizing")
    for name in ("DB_PASSWORD", "FLYWAY_PASSWORD", "RABBITMQ_PASSWORD", "JWT_PRIVATE_KEY"):
        if name in environment:
            raise AssertionError(f"Runtime secret {name} must not be baked into the image")


def verify_identity(output):
    if not re.search(r"\buid=10001(?:\(|\s|$)", output) or not re.search(r"\bgid=10001(?:\(|\s|$)", output):
        raise AssertionError("Runtime must execute with UID/GID 10001")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    result = subprocess.run(
        ["docker", "image", "inspect", args.image, "--format", "{{json .Config}}"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    verify_config(json.loads(result.stdout), args.port)
    command = ["docker", "run", "--rm", "--network", "none", "--read-only",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
               "--memory", "128m", "--entrypoint"]
    identity = subprocess.run(
        command + ["id", args.image], capture_output=True, text=True, check=True, timeout=30,
    )
    verify_identity(identity.stdout)
    java = subprocess.run(
        command + ["java", args.image, "-version"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    if not re.search(r'version "21\.', java.stdout + java.stderr):
        raise AssertionError("Expected a Java 21 runtime")
    print(f"Image contract passed: {args.image}, port {args.port}, UID/GID 10001, Java 21")


if __name__ == "__main__":
    main()
