FROM alpine:3.21

ARG OMNILIT_APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="OmniLit Backup Worker" \
      org.opencontainers.image.version="${OMNILIT_APP_VERSION}"

RUN apk add --no-cache bash coreutils postgresql16-client restic
COPY deploy/backup.sh /usr/local/bin/omnilit-backup
RUN chmod 0755 /usr/local/bin/omnilit-backup

ENTRYPOINT ["/usr/local/bin/omnilit-backup"]
