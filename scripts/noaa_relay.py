#!/usr/bin/env python3
"""SNI relay: lets a client that ignores HTTPS_PROXY reach NOAA hosts through the agent proxy.

For testing in Home Assistant from a Claude Code on the web session (see CLAUDE.md). Home
Assistant's HTTP client doesn't use a proxy, and the session reaches the internet only through
one. Point the NOAA host names at 127.0.0.1. The relay reads the TLS ClientHello, takes the SNI
host, opens an HTTP CONNECT tunnel to <host>:443 through $HTTPS_PROXY, forwards the ClientHello
and pipes bytes both ways. TLS stays end to end between the client and the proxy, so the client
must trust the proxy's CA. Hosts outside ALLOWED are refused. Standard library only.

Usage:
    python3 -I scripts/noaa_relay.py [listen_port]     # default 443, binds 127.0.0.1
    python3 -I scripts/noaa_relay.py --add-host-args   # print docker run --add-host options
"""

import argparse
import asyncio
import functools
import os
import time
from urllib.parse import urlsplit

# The NOAA hosts the integration uses. tests/test_noaa_relay.py checks this against its code.
ALLOWED = {
    "api.weather.gov",
    "services.swpc.noaa.gov",
    "api.tidesandcurrents.noaa.gov",
    "tidesandcurrents.noaa.gov",
    "www.ndbc.noaa.gov",
    "www.nhc.noaa.gov",
    "radar.weather.gov",
    "forecast.weather.gov",
    "cdn.star.nesdis.noaa.gov",
}


def proxy_address():
    proxy = urlsplit(os.environ["HTTPS_PROXY"])
    return proxy.hostname, proxy.port or 80


def log(host, status):
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} host={host} connect={status}", flush=True)


async def read_client_hello(reader):
    """Return (raw bytes read, SNI host or None). Handles a handshake split over records."""
    raw = b""
    hs = b""
    while True:
        header = await reader.readexactly(5)
        if header[0] != 0x16:  # not a TLS handshake record
            return raw + header, None
        body = await reader.readexactly(int.from_bytes(header[3:5], "big"))
        raw += header + body
        hs += body
        if len(hs) >= 4 and len(hs) >= 4 + int.from_bytes(hs[1:4], "big"):
            break
    return raw, parse_sni(hs)


def parse_sni(hs):
    if hs[0] != 0x01:  # ClientHello
        return None
    p = 4 + 2 + 32  # handshake header, client_version, random
    p += 1 + hs[p]  # session_id
    p += 2 + int.from_bytes(hs[p:p + 2], "big")  # cipher_suites
    p += 1 + hs[p]  # compression_methods
    end = p + 2 + int.from_bytes(hs[p:p + 2], "big")
    p += 2
    while p + 4 <= end:
        ext_type = int.from_bytes(hs[p:p + 2], "big")
        ext_len = int.from_bytes(hs[p + 2:p + 4], "big")
        p += 4
        if ext_type == 0:  # server_name: list_len(2) name_type(1) name_len(2) name
            if hs[p + 2] == 0:
                name_len = int.from_bytes(hs[p + 3:p + 5], "big")
                return hs[p + 5:p + 5 + name_len].decode("ascii").lower()
            return None
        p += ext_len
    return None


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            if writer.can_write_eof():
                writer.write_eof()
        except OSError:
            pass


async def handle(c_reader, c_writer, proxy):
    host = "-"
    u_writer = None
    try:
        hello, host = await asyncio.wait_for(read_client_hello(c_reader), 15)
        if host not in ALLOWED:
            log(host or "-", "refused-sni")
            return
        u_reader, u_writer = await asyncio.open_connection(*proxy)
        u_writer.write(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode())
        await u_writer.drain()
        head = await asyncio.wait_for(u_reader.readuntil(b"\r\n\r\n"), 30)
        status = head.split(b" ", 2)[1].decode()
        log(host, status)
        if status != "200":
            return
        u_writer.write(hello)
        await u_writer.drain()
        await asyncio.gather(pipe(c_reader, u_writer), pipe(u_reader, c_writer))
    except Exception as err:  # one line, no payload
        log(host or "-", f"error:{type(err).__name__}")
    finally:
        for w in (c_writer, u_writer):
            if w is not None:
                w.close()


async def serve(port):
    proxy = proxy_address()
    server = await asyncio.start_server(functools.partial(handle, proxy=proxy), "127.0.0.1", port)
    print(f"relay listening on 127.0.0.1:{port}, proxy {proxy[0]}:{proxy[1]}", flush=True)
    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("port", nargs="?", type=int, default=443)
    parser.add_argument("--add-host-args", action="store_true",
                        help="print a docker run --add-host option for each host, then exit")
    args = parser.parse_args()
    if args.add_host_args:
        print(" ".join(f"--add-host {host}:127.0.0.1" for host in sorted(ALLOWED)))
        return
    asyncio.run(serve(args.port))


if __name__ == "__main__":
    main()
