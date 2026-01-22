#!/usr/bin/env python3
"""
LongPort / Longbridge OpenAPI latency tester (CentOS/Linux)

What it measures (per target):
- DNS resolve time
- TCP connect time (443)
- TLS handshake time (443)
- WebSocket upgrade+handshake time + WebSocket ping RTT (if target is wss://...)
- Optional: plain TCP connect time to Socket Feed port 2020

Why you got HTTP 400 before:
Your current script uses /v2 without the required WS handshake query parameters
(version/codec/platform), so the server rejects the WS upgrade with 400.
See: https://open.longbridge.com/docs/socket/protocol/handshake
"""

import argparse
import asyncio
import csv
import math
import socket
import ssl
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import websockets


DEFAULT_WS_QUERY = {"version": "1", "codec": "1", "platform": "9"}  # OpenAPI: v=1, protobuf=1, platform=9


def ms(x: float) -> float:
    return x * 1000.0


def percentile(data: List[float], p: float) -> float:
    """Linear interpolation percentile (p in [0, 100])."""
    if not data:
        return float("nan")
    xs = sorted(data)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def summarize(label: str, data: List[float]) -> str:
    if not data:
        return f"{label}: (no data)"
    med = statistics.median(data)
    p95 = percentile(data, 95)
    p99 = percentile(data, 99)
    mn = min(data)
    mx = max(data)
    sd = statistics.pstdev(data) if len(data) > 1 else 0.0
    return f"{label}: median {med:.2f} ms | p95 {p95:.2f} | p99 {p99:.2f} | min {mn:.2f} | max {mx:.2f} | jitter(sd) {sd:.2f}"


def resolve_once(host: str, port: int, prefer_ipv4: bool = True) -> Tuple[float, str]:
    t0 = time.perf_counter()
    family = socket.AF_INET if prefer_ipv4 else 0
    infos = socket.getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
    t1 = time.perf_counter()
    ip = infos[0][4][0]
    return ms(t1 - t0), ip


def tcp_connect(ip: str, port: int, timeout: int) -> Tuple[float, socket.socket]:
    t0 = time.perf_counter()
    sock = socket.create_connection((ip, port), timeout=timeout)
    t1 = time.perf_counter()
    return ms(t1 - t0), sock


def tls_handshake(sock: socket.socket, server_hostname: str) -> Tuple[float, ssl.SSLSocket]:
    ctx = ssl.create_default_context()
    t0 = time.perf_counter()
    ssock = ctx.wrap_socket(sock, server_hostname=server_hostname)
    ssock.do_handshake()
    t1 = time.perf_counter()
    return ms(t1 - t0), ssock


def ensure_ws_query(url: str, required: Dict[str, str] = DEFAULT_WS_QUERY) -> str:
    """Ensure wss:// URL includes required handshake query params."""
    p = urlparse(url)
    if p.scheme != "wss":
        return url
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    changed = False
    for k, v in required.items():
        if q.get(k) != v:
            q.setdefault(k, v)
            changed = True
    if not changed and p.query:
        return url
    new_p = p._replace(query=urlencode(q))
    return urlunparse(new_p)


def gen_ws_candidates(url: str) -> List[str]:
    """
    Generate candidate WS URLs to try:
    - as provided (with required query ensured)
    - if path has/doesn't have /v2, try both
    """
    p = urlparse(url)
    if p.scheme != "wss":
        return [url]
    candidates = []

    def add(u: str):
        u = ensure_ws_query(u)
        if u not in candidates:
            candidates.append(u)

    add(url)

    # Toggle /v2 in path as fallback
    path = p.path or "/"
    if path.endswith("/v2"):
        p2 = p._replace(path=path[:-3] or "/")
        add(urlunparse(p2))
    elif path == "/" or path == "":
        p2 = p._replace(path="/v2")
        add(urlunparse(p2))
    else:
        # if some other path, also try appending /v2
        p2 = p._replace(path=path.rstrip("/") + "/v2")
        add(urlunparse(p2))

    return candidates


@dataclass
class TargetResult:
    url: str
    ip: Optional[str]
    dns_ms: List[float]
    tcp_ms: List[float]
    tls_ms: List[float]
    tcp2020_ms: List[float]
    ws_ok_url: Optional[str]
    ws_handshake_ms: List[float]
    ws_ping_ms: List[float]
    ws_fail: List[str]


async def ws_handshake_and_ping(url: str, timeout: int, pings_per_conn: int) -> Tuple[float, List[float]]:
    """
    Measure:
    - WS connect+upgrade handshake time (connect returns after handshake)
    - N ping RTTs on the same connection
    """
    t0 = time.perf_counter()
    async with websockets.connect(
        url,
        ping_interval=None,
        open_timeout=timeout,
        close_timeout=timeout,
        max_size=None,
    ) as ws:
        t1 = time.perf_counter()
        handshake_ms = ms(t1 - t0)

        ping_rtts = []
        for _ in range(pings_per_conn):
            t2 = time.perf_counter()
            pong_waiter = ws.ping()
            await asyncio.wait_for(pong_waiter, timeout=timeout)
            t3 = time.perf_counter()
            ping_rtts.append(ms(t3 - t2))

    return handshake_ms, ping_rtts


async def test_target(
    url: str,
    runs: int,
    timeout: int,
    pings_per_conn: int,
    test_tcp2020: bool,
    prefer_ipv4: bool,
) -> TargetResult:
    p = urlparse(url)
    host = p.hostname
    if not host:
        raise ValueError(f"Bad URL: {url}")

    dns_list: List[float] = []
    tcp_list: List[float] = []
    tls_list: List[float] = []
    tcp2020_list: List[float] = []
    ip_last: Optional[str] = None

    # TCP/TLS to 443
    for _ in range(runs):
        try:
            dns_ms, ip = resolve_once(host, 443, prefer_ipv4=prefer_ipv4)
            ip_last = ip
            dns_list.append(dns_ms)

            tcp_ms, sock = tcp_connect(ip, 443, timeout=timeout)
            tcp_list.append(tcp_ms)

            tls_ms, ssock = tls_handshake(sock, server_hostname=host)
            tls_list.append(tls_ms)
            ssock.close()
        except Exception as e:
            # record partial and stop
            break

    # Optional TCP connect to 2020
    if test_tcp2020:
        for _ in range(runs):
            try:
                _, ip = resolve_once(host, 2020, prefer_ipv4=prefer_ipv4)
                ip_last = ip_last or ip
                tcp_ms, sock = tcp_connect(ip, 2020, timeout=timeout)
                tcp2020_list.append(tcp_ms)
                sock.close()
            except Exception:
                break

    # WebSocket
    ws_handshake_list: List[float] = []
    ws_ping_list: List[float] = []
    ws_fail: List[str] = []
    ws_ok_url: Optional[str] = None

    if p.scheme == "wss":
        # try a few candidate URLs (e.g., add required query, try /v2 or not)
        candidates = gen_ws_candidates(url)
        last_exc = None
        for cand in candidates:
            # warm test
            try:
                hs, ping_rtts = await ws_handshake_and_ping(cand, timeout=timeout, pings_per_conn=pings_per_conn)
                ws_ok_url = cand
                ws_handshake_list.append(hs)
                ws_ping_list.extend(ping_rtts)
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                ws_fail.append(f"{cand} -> {type(e).__name__}: {e}")

        if ws_ok_url:
            # run remaining times against the working URL
            remaining = runs - 1  # we already did one
            for _ in range(max(0, remaining)):
                try:
                    hs, ping_rtts = await ws_handshake_and_ping(ws_ok_url, timeout=timeout, pings_per_conn=pings_per_conn)
                    ws_handshake_list.append(hs)
                    ws_ping_list.extend(ping_rtts)
                except Exception as e:
                    ws_fail.append(f"{ws_ok_url} -> {type(e).__name__}: {e}")
                    break
        elif last_exc is not None:
            # nothing worked; keep failures
            pass

    return TargetResult(
        url=url,
        ip=ip_last,
        dns_ms=dns_list,
        tcp_ms=tcp_list,
        tls_ms=tls_list,
        tcp2020_ms=tcp2020_list,
        ws_ok_url=ws_ok_url,
        ws_handshake_ms=ws_handshake_list,
        ws_ping_ms=ws_ping_list,
        ws_fail=ws_fail,
    )


def default_targets() -> List[str]:
    # Official Socket Feed WS handshake uses URL query version/codec/platform (OpenAPI = 9)
    # Endpoints list shows base hosts for WSS and port 2020 for TCP.
    return [
        "https://openapi.longportapp.com",
        "wss://openapi-quote.longportapp.com",
        "wss://openapi-trade.longportapp.com",
    ]


def write_csv(path: str, results: List[TargetResult]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "ip", "metric", "count", "median_ms", "p95_ms", "p99_ms", "min_ms", "max_ms", "jitter_sd_ms", "ws_ok_url"])
        for r in results:
            for metric, data in [
                ("dns_ms", r.dns_ms),
                ("tcp_ms", r.tcp_ms),
                ("tls_ms", r.tls_ms),
                ("tcp2020_ms", r.tcp2020_ms),
                ("ws_handshake_ms", r.ws_handshake_ms),
                ("ws_ping_ms", r.ws_ping_ms),
            ]:
                if not data:
                    continue
                w.writerow([
                    r.url,
                    r.ip or "",
                    metric,
                    len(data),
                    f"{statistics.median(data):.3f}",
                    f"{percentile(data,95):.3f}",
                    f"{percentile(data,99):.3f}",
                    f"{min(data):.3f}",
                    f"{max(data):.3f}",
                    f"{(statistics.pstdev(data) if len(data)>1 else 0.0):.3f}",
                    r.ws_ok_url or "",
                ])


async def amain() -> int:
    ap = argparse.ArgumentParser(description="LongPort/Longbridge OpenAPI latency tester")
    ap.add_argument("--runs", type=int, default=10, help="Number of runs per target (default: 10)")
    ap.add_argument("--timeout", type=int, default=5, help="Timeout seconds (default: 5)")
    ap.add_argument("--pings", type=int, default=3, help="WebSocket pings per connection (default: 3)")
    ap.add_argument("--tcp2020", action="store_true", help="Also test plain TCP connect to port 2020")
    ap.add_argument("--ipv6", action="store_true", help="Allow IPv6 (default prefers IPv4)")
    ap.add_argument("--csv", type=str, default="", help="Write results to CSV file")
    ap.add_argument("targets", nargs="*", help="Targets (https://... or wss://...)")
    args = ap.parse_args()

    targets = args.targets or default_targets()

    print(f"runs={args.runs}, timeout={args.timeout}s, pings/conn={args.pings}, tcp2020={args.tcp2020}\n")

    results: List[TargetResult] = []
    for t in targets:
        print(f"== {t}")
        r = await test_target(
            t,
            runs=args.runs,
            timeout=args.timeout,
            pings_per_conn=args.pings,
            test_tcp2020=args.tcp2020,
            prefer_ipv4=not args.ipv6,
        )
        results.append(r)

        if r.ip:
            print(f"  ip: {r.ip}")
        print("  " + summarize("DNS", r.dns_ms))
        print("  " + summarize("TCP", r.tcp_ms))
        print("  " + summarize("TLS", r.tls_ms))
        if args.tcp2020:
            print("  " + summarize("TCP:2020", r.tcp2020_ms))

        if urlparse(t).scheme == "wss":
            if r.ws_ok_url:
                print(f"  WS url used: {r.ws_ok_url}")
                print("  " + summarize("WS handshake", r.ws_handshake_ms))
                print("  " + summarize("WS ping RTT", r.ws_ping_ms))
            else:
                print("  WS: failed")
                for line in r.ws_fail[:5]:
                    print(f"    - {line}")
                if len(r.ws_fail) > 5:
                    print(f"    ... ({len(r.ws_fail)-5} more)")

        print()

    if args.csv:
        write_csv(args.csv, results)
        print(f"Wrote CSV: {args.csv}")

    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(amain()))
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
