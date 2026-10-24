# Multi-stage Dockerfile for ML Training Pipeline (§5.1, §5.6)

FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock.txt


FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MLFLOW_TRACKING_URI=http://mlflow.ml.svc.cluster.local:5000

# Create unprivileged runner user
RUN groupadd -g 10002 mlgroup && \
    useradd -u 10002 -g mlgroup -s /sbin/nologin -d /app mlrunner

COPY --from=builder /install /usr/local
COPY . /app/ml

RUN chown -R mlrunner:mlgroup /app

USER mlrunner

ENTRYPOINT ["python", "-m", "ml.src.pipeline.run"]
CMD ["--mode=full", "--test-mode"]
