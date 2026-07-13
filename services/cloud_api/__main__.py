from __future__ import annotations

import argparse
import base64
import binascii
import json
import logging
import os
import signal
import threading
from pathlib import Path
from urllib.parse import quote

from .backup import CloudBackupError, CloudBackupManager, CloudBackupScheduler
from .http_server import make_server
from .service import CloudApiService


LOGGER = logging.getLogger("omnilit.cloud_api.runtime")


def _environment_secret(name: str, *, required: bool = True) -> str:
    value = os.environ.get(name, "")
    key_file = os.environ.get(f"{name}_FILE", "")
    if value and key_file:
        raise SystemExit(f"Set only one of {name} or {name}_FILE")
    if key_file:
        try:
            value = Path(key_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit(f"Unable to read {name}_FILE") from exc
    if required and not value:
        raise SystemExit(f"{name} or {name}_FILE is required; no development default is provided")
    return value


def _environment_key(name: str) -> bytes:
    encoded_key = _environment_secret(name)
    try:
        key = base64.urlsafe_b64decode(encoded_key)
    except (ValueError, binascii.Error) as exc:
        raise SystemExit(f"{name} must be valid URL-safe base64") from exc
    if len(key) != 32:
        raise SystemExit(f"{name} must decode to exactly 32 bytes")
    return key


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OmniLit Cloud API reference service and offline backup tools")
    parser.add_argument("command", nargs="?", choices=("serve", "backup", "verify", "restore", "bootstrap-admin"), default="serve")
    parser.add_argument("backup_path", nargs="?")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--email")
    parser.add_argument("--force", action="store_true")
    return parser


def _serve_until_stopped(server, scheduler: CloudBackupScheduler | None = None) -> None:
    """Serve until Ctrl+C or a service-manager termination signal requests shutdown."""
    stop_requested = threading.Event()
    installed_handlers: dict[signal.Signals, object] = {}

    def request_stop(signum: int, _frame: object) -> None:
        LOGGER.info(json.dumps({"event": "cloud_shutdown_requested", "signal": signal.Signals(signum).name}, separators=(",", ":")))
        stop_requested.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            installed_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)

    def shutdown_server() -> None:
        stop_requested.wait()
        server.shutdown()

    shutdown_thread = threading.Thread(target=shutdown_server, name="omnilit-cloud-shutdown", daemon=True)
    shutdown_thread.start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        stop_requested.set()
    finally:
        stop_requested.set()
        if scheduler is not None:
            scheduler.stop()
        server.server_close()
        shutdown_thread.join(timeout=2)
        for signum, handler in installed_handlers.items():
            signal.signal(signum, handler)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("OMNILIT_CLOUD_LOG_LEVEL", "INFO").upper(), format="%(message)s")
    args = _parser().parse_args(argv)
    database_url = os.environ.get("OMNILIT_DATABASE_URL", "").strip()
    postgres_host = os.environ.get("OMNILIT_POSTGRES_HOST", "").strip()
    if not database_url and postgres_host:
        password_file = os.environ.get("OMNILIT_POSTGRES_PASSWORD_FILE", "")
        if not password_file:
            raise SystemExit("OMNILIT_POSTGRES_PASSWORD_FILE is required with OMNILIT_POSTGRES_HOST")
        try:
            password = Path(password_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit("Unable to read OMNILIT_POSTGRES_PASSWORD_FILE") from exc
        user = quote(os.environ.get("OMNILIT_POSTGRES_USER", "omnilit"), safe="")
        database_name = quote(os.environ.get("OMNILIT_POSTGRES_DATABASE", "omnilit"), safe="")
        port = int(os.environ.get("OMNILIT_POSTGRES_PORT", "5432"))
        database_url = f"postgresql://{user}:{quote(password, safe='')}@{postgres_host}:{port}/{database_name}"
    database = Path(os.environ.get("OMNILIT_CLOUD_DATABASE", "runtime/cloud-api/cloud.sqlite3"))
    backup_directory = Path(os.environ.get("OMNILIT_CLOUD_BACKUP_DIR", str(database.parent / "backups")))
    if args.command == "bootstrap-admin":
        if not args.email:
            raise SystemExit("bootstrap-admin requires --email")
        service = CloudApiService(database_url or database, _environment_key("OMNILIT_CLOUD_ENCRYPTION_KEY_B64"))
        try:
            result = service.bootstrap_system_admin(args.email)
        finally:
            service.shutdown(wait=True)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    if args.command != "serve":
        manager = CloudBackupManager(_environment_key("OMNILIT_CLOUD_BACKUP_KEY_B64"))
        try:
            if args.command == "backup":
                result = manager.create_backup(database, backup_directory, retention=int(os.environ.get("OMNILIT_CLOUD_BACKUP_RETENTION", "14")))
            elif args.command == "verify":
                if not args.backup_path:
                    raise SystemExit("verify requires a backup_path")
                result = manager.verify_backup(Path(args.backup_path))
            else:
                if not args.backup_path:
                    raise SystemExit("restore requires a backup_path")
                result = manager.restore_backup(Path(args.backup_path), args.target or database, force=args.force)
        except CloudBackupError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0

    key = _environment_key("OMNILIT_CLOUD_ENCRYPTION_KEY_B64")
    host = os.environ.get("OMNILIT_CLOUD_HOST", "127.0.0.1")
    port = int(os.environ.get("OMNILIT_CLOUD_PORT", "8787"))
    origins = {value.strip() for value in os.environ.get("OMNILIT_CLOUD_ALLOWED_ORIGINS", "").split(",") if value.strip()}
    tls_terminated = os.environ.get("OMNILIT_CLOUD_TLS_TERMINATED", "0") == "1"
    public_base_url = os.environ.get("OMNILIT_CLOUD_PUBLIC_BASE_URL", "https://app.omnilit.invalid")
    backup_key_configured = bool(os.environ.get("OMNILIT_CLOUD_BACKUP_KEY_B64") or os.environ.get("OMNILIT_CLOUD_BACKUP_KEY_B64_FILE"))
    backup_key = _environment_key("OMNILIT_CLOUD_BACKUP_KEY_B64") if backup_key_configured else None
    metrics_token = _environment_secret("OMNILIT_CLOUD_METRICS_TOKEN", required=False) or None
    if metrics_token is not None and len(metrics_token) < 32:
        raise SystemExit("OMNILIT_CLOUD_METRICS_TOKEN must contain at least 32 characters")
    if backup_key == key:
        raise SystemExit("OMNILIT_CLOUD_BACKUP_KEY_B64 must be distinct from the Cloud data encryption key")
    service = CloudApiService(database_url or database, key, public_base_url=public_base_url)
    server = make_server(host, port, service=service, allowed_origins=origins, tls_terminated=tls_terminated, max_collaboration_streams=max(1, int(os.environ.get("OMNILIT_CLOUD_MAX_COLLABORATION_STREAMS", "64"))), metrics_token=metrics_token)
    scheduler: CloudBackupScheduler | None = None
    if backup_key is not None and not database_url:
        scheduler = CloudBackupScheduler(
            CloudBackupManager(backup_key), database, backup_directory,
            interval_seconds=max(60, int(os.environ.get("OMNILIT_CLOUD_BACKUP_INTERVAL_SECONDS", "86400"))),
            retention=max(1, int(os.environ.get("OMNILIT_CLOUD_BACKUP_RETENTION", "14"))),
        )
        server.set_backup_status(scheduler.status_snapshot)
        scheduler.start()
    elif backup_key is not None and database_url:
        LOGGER.info(json.dumps({"event": "cloud_embedded_backup_disabled", "reason": "postgresql_uses_dedicated_backup_worker"}, separators=(",", ":")))
    LOGGER.info(json.dumps({"event": "cloud_service_started", "host": host, "port": server.server_address[1], "schemaVersion": service.operational_health()["schemaVersion"], "backupsEnabled": scheduler is not None}, separators=(",", ":")))
    _serve_until_stopped(server, scheduler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
