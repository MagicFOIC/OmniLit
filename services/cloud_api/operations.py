from __future__ import annotations

import hashlib
import hmac
import threading
from collections import Counter
from typing import Callable


HISTOGRAM_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class OperationsMetrics:
    """Bounded, process-local Prometheus metrics without tenant or resource identifiers."""

    def __init__(self, token: str | None = None) -> None:
        self._token_hash = hashlib.sha256(token.encode("utf-8")).digest() if token else None
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._duration_count: Counter[tuple[str, str]] = Counter()
        self._duration_sum: Counter[tuple[str, str]] = Counter()
        self._duration_buckets: Counter[tuple[str, str, float]] = Counter()
        self._in_flight = 0
        self._collaboration_streams = 0
        self._collaboration_stream_capacity = 0
        self._backup_snapshot: Callable[[], dict[str, float | int]] | None = None

    @property
    def configured(self) -> bool:
        return self._token_hash is not None

    def authorized(self, token: str) -> bool:
        if self._token_hash is None:
            return False
        return hmac.compare_digest(self._token_hash, hashlib.sha256(token.encode("utf-8")).digest())

    def request_started(self) -> None:
        with self._lock:
            self._in_flight += 1

    def request_completed(self, method: str, route: str, status: int, duration_seconds: float) -> None:
        key = (method, route)
        duration = max(0.0, float(duration_seconds))
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._requests[(method, route, int(status))] += 1
            self._duration_count[key] += 1
            self._duration_sum[key] += duration
            for bucket in HISTOGRAM_BUCKETS:
                if duration <= bucket:
                    self._duration_buckets[(method, route, bucket)] += 1

    def set_collaboration_streams(self, active: int, capacity: int) -> None:
        with self._lock:
            self._collaboration_streams = max(0, int(active))
            self._collaboration_stream_capacity = max(0, int(capacity))

    def set_backup_snapshot(self, snapshot: Callable[[], dict[str, float | int]]) -> None:
        self._backup_snapshot = snapshot

    def render(self, readiness: dict) -> str:
        with self._lock:
            requests = dict(self._requests)
            counts = dict(self._duration_count)
            sums = dict(self._duration_sum)
            buckets = dict(self._duration_buckets)
            in_flight = self._in_flight
            streams = self._collaboration_streams
            stream_capacity = self._collaboration_stream_capacity
        lines = [
            "# HELP omnilit_cloud_ready Whether the Cloud API is ready to serve traffic.",
            "# TYPE omnilit_cloud_ready gauge",
            f"omnilit_cloud_ready {1 if readiness.get('status') == 'ready' else 0}",
            "# HELP omnilit_cloud_http_requests_in_flight Current HTTP requests being handled.",
            "# TYPE omnilit_cloud_http_requests_in_flight gauge",
            f"omnilit_cloud_http_requests_in_flight {in_flight}",
            "# HELP omnilit_cloud_http_requests_total Completed HTTP requests by templated route and status.",
            "# TYPE omnilit_cloud_http_requests_total counter",
        ]
        for (method, route, status), value in sorted(requests.items()):
            lines.append(f'omnilit_cloud_http_requests_total{{method="{_label(method)}",route="{_label(route)}",status="{status}"}} {value}')
        lines.extend([
            "# HELP omnilit_cloud_http_request_duration_seconds HTTP request duration by templated route.",
            "# TYPE omnilit_cloud_http_request_duration_seconds histogram",
        ])
        for method, route in sorted(counts):
            cumulative = 0
            for bucket in HISTOGRAM_BUCKETS:
                cumulative = buckets.get((method, route, bucket), cumulative)
                lines.append(f'omnilit_cloud_http_request_duration_seconds_bucket{{method="{_label(method)}",route="{_label(route)}",le="{bucket:g}"}} {cumulative}')
            lines.append(f'omnilit_cloud_http_request_duration_seconds_bucket{{method="{_label(method)}",route="{_label(route)}",le="+Inf"}} {counts[(method, route)]}')
            lines.append(f'omnilit_cloud_http_request_duration_seconds_sum{{method="{_label(method)}",route="{_label(route)}"}} {sums[(method, route)]:.9f}')
            lines.append(f'omnilit_cloud_http_request_duration_seconds_count{{method="{_label(method)}",route="{_label(route)}"}} {counts[(method, route)]}')
        lines.extend([
            "# HELP omnilit_cloud_collaboration_streams Active collaboration streams.",
            "# TYPE omnilit_cloud_collaboration_streams gauge",
            f"omnilit_cloud_collaboration_streams {streams}",
            "# HELP omnilit_cloud_collaboration_stream_capacity Configured collaboration stream capacity.",
            "# TYPE omnilit_cloud_collaboration_stream_capacity gauge",
            f"omnilit_cloud_collaboration_stream_capacity {stream_capacity}",
        ])
        backup = self._backup_snapshot() if self._backup_snapshot else {}
        lines.extend([
            "# HELP omnilit_cloud_backups_enabled Whether automatic encrypted backups are enabled.",
            "# TYPE omnilit_cloud_backups_enabled gauge",
            f"omnilit_cloud_backups_enabled {1 if self._backup_snapshot else 0}",
            "# HELP omnilit_cloud_backup_last_success_unixtime Last successful backup Unix timestamp.",
            "# TYPE omnilit_cloud_backup_last_success_unixtime gauge",
            f"omnilit_cloud_backup_last_success_unixtime {float(backup.get('lastSuccessUnixTime', 0)):.3f}",
            "# HELP omnilit_cloud_backup_last_failure_unixtime Last failed backup Unix timestamp.",
            "# TYPE omnilit_cloud_backup_last_failure_unixtime gauge",
            f"omnilit_cloud_backup_last_failure_unixtime {float(backup.get('lastFailureUnixTime', 0)):.3f}",
            "# HELP omnilit_cloud_backup_consecutive_failures Consecutive automatic backup failures.",
            "# TYPE omnilit_cloud_backup_consecutive_failures gauge",
            f"omnilit_cloud_backup_consecutive_failures {int(backup.get('consecutiveFailures', 0))}",
        ])
        return "\n".join(lines) + "\n"
