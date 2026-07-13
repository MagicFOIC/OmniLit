FROM python:3.12-slim-bookworm

ARG OMNILIT_APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="OmniLit Cloud API" \
      org.opencontainers.image.version="${OMNILIT_APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    OMNILIT_CLOUD_DATABASE=/var/lib/omnilit/cloud.sqlite3

WORKDIR /app

COPY services/cloud_api/requirements.in /tmp/requirements.in
COPY services/cloud_api/requirements.txt /tmp/cloud-requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/cloud-requirements.txt \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin omnilit \
    && install -d -o omnilit -g omnilit /var/lib/omnilit

COPY omnilit_qt ./omnilit_qt
COPY packages/shared-schema/schemas ./packages/shared-schema/schemas
COPY services ./services

USER 10001:10001
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/v1/health/ready', timeout=3).read()"]

CMD ["python", "-m", "services.cloud_api", "serve"]
