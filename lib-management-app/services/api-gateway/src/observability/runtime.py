"""In-memory runtime telemetry for API gateway observability."""
from __future__ import annotations

import asyncio
from collections import deque
import os
import resource
import sys
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EndpointStat:
    method: str
    path: str
    requests: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        avg = self.total_latency_ms / self.requests if self.requests > 0 else 0.0
        return {
            "method": self.method,
            "path": self.path,
            "requests": self.requests,
            "errors": self.errors,
            "avg_latency_ms": round(avg, 2),
        }


@dataclass
class RuntimeTelemetry:
    started_at: float = field(default_factory=time.time)
    total_requests: int = 0
    total_errors: int = 0
    total_latency_ms: float = 0.0
    by_status: dict[str, int] = field(default_factory=dict)
    by_endpoint: dict[str, EndpointStat] = field(default_factory=dict)
    history: deque[tuple[float, float, bool]] = field(default_factory=lambda: deque(maxlen=20000))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _pid: int = field(default_factory=os.getpid)

    async def record(self, method: str, path: str, status_code: int, latency_ms: float) -> None:
        key = f"{method} {path}"
        async with self._lock:
            self.total_requests += 1
            self.total_latency_ms += latency_ms
            if status_code >= 400:
                self.total_errors += 1
            status_key = str(status_code)
            self.by_status[status_key] = self.by_status.get(status_key, 0) + 1

            endpoint = self.by_endpoint.get(key)
            if endpoint is None:
                endpoint = EndpointStat(method=method, path=path)
                self.by_endpoint[key] = endpoint
            endpoint.requests += 1
            endpoint.total_latency_ms += latency_ms
            if status_code >= 400:
                endpoint.errors += 1
            self.history.append((time.time(), latency_ms, status_code >= 400))

    def _window_metrics(self, now_ts: float, seconds: int) -> dict[str, float]:
        cutoff = now_ts - seconds
        sample = [x for x in self.history if x[0] >= cutoff]
        req = len(sample)
        err = sum(1 for _, _, is_err in sample if is_err)
        avg = (sum(lat for _, lat, _ in sample) / req) if req > 0 else 0.0
        rpm = (req / seconds * 60.0) if seconds > 0 else 0.0
        err_pct = (err / req * 100.0) if req > 0 else 0.0
        return {
            "requests": req,
            "errors": err,
            "avg_latency_ms": round(avg, 2),
            "error_rate_pct": round(err_pct, 2),
            "requests_per_minute_est": round(rpm, 2),
        }

    def _trend_points(self, now_ts: float, minutes: int, bucket_seconds: int = 60) -> list[dict[str, float]]:
        points: list[dict[str, float]] = []
        total_buckets = max(int((minutes * 60) / bucket_seconds), 1)
        for i in range(total_buckets):
            end_ts = now_ts - (total_buckets - i - 1) * bucket_seconds
            start_ts = end_ts - bucket_seconds
            sample = [x for x in self.history if start_ts <= x[0] < end_ts]
            req = len(sample)
            err = sum(1 for _, _, is_err in sample if is_err)
            avg = (sum(lat for _, lat, _ in sample) / req) if req > 0 else 0.0
            points.append({
                "bucket": i + 1,
                "requests": req,
                "errors": err,
                "avg_latency_ms": round(avg, 2),
            })
        return points

    async def snapshot(self, top_n: int = 8) -> dict[str, Any]:
        async with self._lock:
            total_requests = self.total_requests
            total_errors = self.total_errors
            total_latency_ms = self.total_latency_ms
            by_status = dict(self.by_status)
            endpoint_stats = sorted(
                (v.to_dict() for v in self.by_endpoint.values()),
                key=lambda x: x["requests"],
                reverse=True,
            )[:top_n]
            now_ts = time.time()
            window_5m = self._window_metrics(now_ts, 5 * 60)
            window_1h = self._window_metrics(now_ts, 60 * 60)
            trend_5m = self._trend_points(now_ts, minutes=5, bucket_seconds=60)
            trend_1h = self._trend_points(now_ts, minutes=60, bucket_seconds=300)

        uptime_seconds = max(time.time() - self.started_at, 0.0)
        avg_latency_ms = total_latency_ms / total_requests if total_requests > 0 else 0.0
        errors_pct = (total_errors / total_requests * 100.0) if total_requests > 0 else 0.0
        rpm = (total_requests / uptime_seconds * 60.0) if uptime_seconds > 0 else 0.0

        rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            # macOS reports bytes
            memory_rss_mb = rss_raw / (1024 * 1024)
        else:
            # Linux reports kilobytes
            memory_rss_mb = rss_raw / 1024

        cpu_time = sum(os.times()[:2])
        cpu_pct_est = (cpu_time / uptime_seconds * 100.0) if uptime_seconds > 0 else 0.0

        return {
            "gateway": {
                "pid": self._pid,
                "uptime_seconds": round(uptime_seconds, 1),
                "uptime_minutes": round(uptime_seconds / 60.0, 2),
                "uptime_hours": round(uptime_seconds / 3600.0, 2),
            },
            "requests": {
                "total": total_requests,
                "errors": total_errors,
                "error_rate_pct": round(errors_pct, 2),
                "avg_latency_ms": round(avg_latency_ms, 2),
                "requests_per_minute_est": round(rpm, 2),
                "status_breakdown": by_status,
                "top_endpoints": endpoint_stats,
                "windows": {
                    "last_5m": window_5m,
                    "last_1h": window_1h,
                },
                "trends": {
                    "last_5m": trend_5m,
                    "last_1h": trend_1h,
                },
            },
            "resources": {
                "memory_rss_mb": round(memory_rss_mb, 2),
                "memory_percent": None,
                "system_memory_used_pct": None,
                "cpu_percent": round(cpu_pct_est, 2),
            },
        }
