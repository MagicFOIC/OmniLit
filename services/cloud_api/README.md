# OmniLit Cloud API reference service

This service establishes the Phase 2 account, tenant, encrypted library-sync, sharing, audit, export, and deletion boundary. It is a deployable reference implementation, not a claim that production hosting, backups, disaster recovery, email verification, or external monitoring are already configured.

Team invitations and resource ACLs use the model documented in
`docs/architecture/cloud-permission-model.md`. Tenant roles do not implicitly expose research data;
non-owner access also requires an explicit resource ACL and the owner's `allowTeamAccess` control.

Cloud graphs use encrypted revisioned snapshots and the existing GraphData/GraphViewState contracts. The
service supports graph list/read/sync, bounded neighbor and literature queries, saved-view CRUD/restore,
and graph or graph-view sharing. It also provides a persistent, tenant-isolated, cancellable `graph.audit`
task, encrypted task results, restart-to-explicit-failure recovery, tenant admin metrics, and structured
redacted request logs. Cloud LOD projection, timelines, arbitrary compute, external monitoring, and
off-site disaster recovery are not part of this slice. See
`docs/architecture/cloud-observability.md` for the exact operational boundary.

Graph collaboration supports encrypted graph/node/edge annotations, graph ACLs, explicit annotation-sync
consent, optimistic revisions, idempotent mutations, bounded recovery logs, and authenticated SSE long
polling. It is not a character-level CRDT or presence system. See `docs/architecture/graph-collaboration.md`.

Optional encrypted database backups use SQLite's online backup API, an independent AES-GCM backup key,
atomic files, bounded retention, integrity verification, and an offline restore command. This is a local
backup/recovery primitive; operators still need off-site immutable storage and restore drills. See
`docs/architecture/cloud-backup-recovery.md`.

Required configuration:

- `OMNILIT_CLOUD_ENCRYPTION_KEY_B64`: URL-safe base64 for exactly 32 random bytes. There is no fallback key.
- `OMNILIT_CLOUD_ALLOWED_ORIGINS`: comma-separated exact HTTPS web origins.
- `OMNILIT_CLOUD_TLS_TERMINATED=1`: required when binding outside loopback; TLS must terminate at the trusted reverse proxy.

Optional configuration:

- `OMNILIT_CLOUD_HOST` (default `127.0.0.1`)
- `OMNILIT_CLOUD_PORT` (default `8787`)
- `OMNILIT_CLOUD_DATABASE`
- `OMNILIT_CLOUD_PUBLIC_BASE_URL`
- `OMNILIT_CLOUD_BACKUP_KEY_B64` (32-byte URL-safe base64 key distinct from the data key; enables backups)
- `OMNILIT_CLOUD_BACKUP_DIR` (default: `backups` next to the database)
- `OMNILIT_CLOUD_BACKUP_INTERVAL_SECONDS` (default `86400`, minimum `60` in service mode)
- `OMNILIT_CLOUD_BACKUP_RETENTION` (default `14`)
- `OMNILIT_CLOUD_MAX_COLLABORATION_STREAMS` (default `64`)
- `OMNILIT_CLOUD_LOG_LEVEL` (default `INFO`)
- `OMNILIT_CLOUD_METRICS_TOKEN` (at least 32 characters; enables protected `/internal/metrics`)

Encryption-key and metrics-token variables also support a mutually exclusive `_FILE` suffix for container secret
mounts. The deployment reference, readiness/liveness contracts, schema compatibility rules, and
graceful shutdown behavior are documented in `docs/architecture/production-deployment.md`.

Run with `python -m services.cloud_api`. Configure the web app with `VITE_CLOUD_API_URL`; Local Agent and Cloud API tokens remain separate.

Management-only backup commands are `python -m services.cloud_api backup`, `verify <backup-path>`, and
`restore <backup-path> --target <database-path> [--force]`. Restore requires the service to be stopped and
refuses targets with SQLite WAL/SHM sidecars.
