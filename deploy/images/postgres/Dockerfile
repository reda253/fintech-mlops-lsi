FROM postgres:17-alpine@sha256:eee6c6e1b0894fa4fe0075eb054af9fd1cf39a35321c2d4110626cfe506411fb

# Kubernetes runs the PostgreSQL account directly; the root-to-user Go helper
# is unnecessary and embeds a vulnerable Go TLS runtime (CVE-2025-68121).
USER root
RUN rm /usr/local/bin/gosu
USER 70:70
