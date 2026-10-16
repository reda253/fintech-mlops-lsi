FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd -g 10002 simgroup && \
    useradd -u 10002 -g simgroup -s /sbin/nologin -d /app simuser

COPY --from=builder /install /usr/local
COPY app /app/app

USER simuser

ENTRYPOINT ["python", "-m", "app.main"]
CMD ["--dry-run"]
