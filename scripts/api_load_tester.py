#!/usr/bin/env python3
"""
API Load Tester - Concurrent HTTP load testing with latency reporting.

Usage:
    python scripts/api_load_tester.py <url> [options]

Options:
    --method METHOD       HTTP method (default: GET)
    --requests N          Total requests to send (default: 100)
    --concurrency C       Concurrent workers (default: 10)
    --duration SEC        Run for this many seconds instead of --requests
    --headers KEY=VAL     Add request header (repeatable)
    --body JSON           Request body (JSON string)
    --token TOKEN         Bearer token for Authorization header
    --timeout SEC         Per-request timeout in seconds (default: 10)
    --output FORMAT       Output format: text | json | csv (default: text)
    --scenario FILE       Load a YAML scenario file with multiple endpoints
    -v, --verbose         Show individual request results

Examples:
    python scripts/api_load_tester.py http://localhost:3000/health
    python scripts/api_load_tester.py http://localhost:3000/api/v1/examples \\
        --requests 500 --concurrency 20 --token my_jwt
    python scripts/api_load_tester.py http://localhost:3000/api/v1/examples \\
        --method POST --body '{"name":"test"}' --requests 200
"""

import argparse
import csv
import io
import json
import math
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RequestResult:
    status:      int
    latency_ms:  float
    error:       Optional[str] = None
    worker_id:   int = 0
    timestamp:   float = field(default_factory=time.time)


@dataclass
class Stats:
    results:     List[RequestResult]
    duration_s:  float

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def success(self) -> int:
        return sum(1 for r in self.results if r.error is None and 200 <= r.status < 400)

    @property
    def errors(self) -> int:
        return self.total - self.success

    @property
    def error_rate(self) -> float:
        return self.errors / self.total if self.total else 0

    @property
    def rps(self) -> float:
        return self.total / self.duration_s if self.duration_s else 0

    def latencies(self) -> List[float]:
        return sorted(r.latency_ms for r in self.results if r.error is None)

    def percentile(self, p: float) -> float:
        lats = self.latencies()
        if not lats:
            return 0.0
        idx = math.ceil(p / 100 * len(lats)) - 1
        return lats[max(0, idx)]

    @property
    def mean_latency(self) -> float:
        lats = self.latencies()
        return sum(lats) / len(lats) if lats else 0.0

    @property
    def min_latency(self) -> float:
        lats = self.latencies()
        return min(lats) if lats else 0.0

    @property
    def max_latency(self) -> float:
        lats = self.latencies()
        return max(lats) if lats else 0.0

    def status_counts(self) -> dict:
        counts = {}
        for r in self.results:
            key = str(r.status) if r.error is None else f"ERR:{r.error[:30]}"
            counts[key] = counts.get(key, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def make_request(url: str, method: str, headers: dict, body: Optional[bytes],
                 timeout: float, worker_id: int) -> RequestResult:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read()
            elapsed = (time.perf_counter() - start) * 1000
            return RequestResult(status=resp.status, latency_ms=elapsed, worker_id=worker_id)
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return RequestResult(status=exc.code, latency_ms=elapsed, worker_id=worker_id)
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return RequestResult(status=0, latency_ms=elapsed, error=str(exc), worker_id=worker_id)


def worker(worker_id: int, task_queue: queue.Queue, results: list, lock: threading.Lock,
           url: str, method: str, headers: dict, body: Optional[bytes],
           timeout: float, verbose: bool) -> None:
    while True:
        try:
            task_queue.get_nowait()
        except queue.Empty:
            break
        result = make_request(url, method, headers, body, timeout, worker_id)
        with lock:
            results.append(result)
        if verbose:
            status_str = str(result.status) if not result.error else f"ERR({result.error[:20]})"
            print(f"  worker={worker_id} status={status_str} latency={result.latency_ms:.1f}ms")
        task_queue.task_done()


def worker_duration(worker_id: int, stop_event: threading.Event, results: list,
                    lock: threading.Lock, url: str, method: str, headers: dict,
                    body: Optional[bytes], timeout: float, verbose: bool) -> None:
    while not stop_event.is_set():
        result = make_request(url, method, headers, body, timeout, worker_id)
        with lock:
            results.append(result)
        if verbose:
            status_str = str(result.status) if not result.error else f"ERR({result.error[:20]})"
            print(f"  worker={worker_id} status={status_str} latency={result.latency_ms:.1f}ms")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_load_test(url: str, method: str, headers: dict, body: Optional[bytes],
                  n_requests: Optional[int], concurrency: int,
                  duration: Optional[float], timeout: float,
                  verbose: bool) -> Stats:
    results = []
    lock = threading.Lock()

    start = time.perf_counter()

    if duration:
        stop_event = threading.Event()
        threads = [
            threading.Thread(
                target=worker_duration,
                args=(i, stop_event, results, lock, url, method, headers, body, timeout, verbose),
                daemon=True,
            )
            for i in range(concurrency)
        ]
        for t in threads:
            t.start()
        time.sleep(duration)
        stop_event.set()
        for t in threads:
            t.join()
    else:
        task_q: queue.Queue = queue.Queue()
        for _ in range(n_requests):
            task_q.put(None)
        threads = [
            threading.Thread(
                target=worker,
                args=(i, task_q, results, lock, url, method, headers, body, timeout, verbose),
                daemon=True,
            )
            for i in range(concurrency)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    elapsed = time.perf_counter() - start
    return Stats(results=results, duration_s=elapsed)


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def print_text(stats: Stats) -> None:
    print("\n" + "=" * 56)
    print("  Load Test Results")
    print("=" * 56)
    print(f"  Total requests : {stats.total}")
    print(f"  Successful     : {stats.success}")
    print(f"  Errors         : {stats.errors}  ({stats.error_rate*100:.1f}%)")
    print(f"  Duration       : {stats.duration_s:.2f}s")
    print(f"  Throughput     : {stats.rps:.2f} req/s")
    print()
    print("  Latency (successful requests)")
    print(f"    min   : {stats.min_latency:>8.2f} ms")
    print(f"    mean  : {stats.mean_latency:>8.2f} ms")
    print(f"    p50   : {stats.percentile(50):>8.2f} ms")
    print(f"    p90   : {stats.percentile(90):>8.2f} ms")
    print(f"    p95   : {stats.percentile(95):>8.2f} ms")
    print(f"    p99   : {stats.percentile(99):>8.2f} ms")
    print(f"    max   : {stats.max_latency:>8.2f} ms")
    print()
    print("  Status codes")
    for code, count in sorted(stats.status_counts().items()):
        print(f"    {code:<12} {count}")
    print("=" * 56)


def print_json_output(stats: Stats) -> None:
    data = {
        "total":       stats.total,
        "success":     stats.success,
        "errors":      stats.errors,
        "error_rate":  round(stats.error_rate, 4),
        "duration_s":  round(stats.duration_s, 3),
        "rps":         round(stats.rps, 2),
        "latency_ms": {
            "min":  round(stats.min_latency, 2),
            "mean": round(stats.mean_latency, 2),
            "p50":  round(stats.percentile(50), 2),
            "p90":  round(stats.percentile(90), 2),
            "p95":  round(stats.percentile(95), 2),
            "p99":  round(stats.percentile(99), 2),
            "max":  round(stats.max_latency, 2),
        },
        "status_counts": stats.status_counts(),
    }
    print(json.dumps(data, indent=2))


def print_csv_output(stats: Stats) -> None:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp_ms", "status", "latency_ms", "error", "worker_id"])
    for r in stats.results:
        w.writerow([
            int(r.timestamp * 1000),
            r.status,
            round(r.latency_ms, 2),
            r.error or "",
            r.worker_id,
        ])
    print(buf.getvalue(), end="")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HTTP API load tester.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="Target URL")
    parser.add_argument("--method",      default="GET")
    parser.add_argument("--requests",    type=int, default=100, dest="n_requests")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--duration",    type=float, default=None,
                        help="Run for N seconds (overrides --requests)")
    parser.add_argument("--headers",     action="append", default=[], metavar="KEY=VAL")
    parser.add_argument("--body",        default=None)
    parser.add_argument("--token",       default=None)
    parser.add_argument("--timeout",     type=float, default=10.0)
    parser.add_argument("--output",      choices=["text", "json", "csv"], default="text")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    headers: dict = {"User-Agent": "api-load-tester/1.0"}
    for hdr in args.headers:
        if "=" not in hdr:
            print(f"Invalid header format (expected KEY=VAL): {hdr}", file=sys.stderr)
            return 1
        k, v = hdr.split("=", 1)
        headers[k.strip()] = v.strip()

    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    body: Optional[bytes] = None
    if args.body:
        headers.setdefault("Content-Type", "application/json")
        body = args.body.encode()

    label = f"{args.duration}s" if args.duration else f"{args.n_requests} requests"
    print(f"Load testing {args.url}  ({label}, concurrency={args.concurrency})")

    stats = run_load_test(
        url=args.url,
        method=args.method.upper(),
        headers=headers,
        body=body,
        n_requests=args.n_requests,
        concurrency=args.concurrency,
        duration=args.duration,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    if args.output == "json":
        print_json_output(stats)
    elif args.output == "csv":
        print_csv_output(stats)
    else:
        print_text(stats)

    return 1 if stats.error_rate > 0.05 else 0


if __name__ == "__main__":
    sys.exit(main())
