"""Tests for scripts/noaa_relay.py, the relay CLAUDE.md uses to test in Home Assistant in the cloud.

No network: the proxy is a fake on 127.0.0.1, and ClientHellos come from ssl.MemoryBIO.
"""

import asyncio
import importlib.util
import re
import ssl
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("noaa_relay", ROOT / "scripts" / "noaa_relay.py")
relay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(relay)


def _run(coro):
    """Run a coroutine on a private loop, leaving the ambient one intact.

    Mirrors the helper in test_image.py: ``asyncio.run()`` clears the thread's
    current event loop on return, which breaks other test modules.
    """
    previous = None
    try:
        previous = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        pass
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(previous)


def client_hello(host):
    """The first bytes a TLS client sends to host."""
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    tls = ssl.create_default_context().wrap_bio(incoming, outgoing, server_hostname=host)
    with pytest.raises(ssl.SSLWantReadError):
        tls.do_handshake()
    return outgoing.read()


def read_hello(data):
    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        return await relay.read_client_hello(reader)
    return _run(run())


class TestClientHello:
    def test_reads_the_sni_host(self):
        hello = client_hello("api.weather.gov")
        assert read_hello(hello + b"rest") == (hello, "api.weather.gov")

    def test_handshake_split_over_two_records(self):
        hello = client_hello("www.nhc.noaa.gov")
        body = hello[5:]
        half = len(body) // 2
        records = b"".join(hello[:3] + len(part).to_bytes(2, "big") + part
                           for part in (body[:half], body[half:]))
        assert read_hello(records) == (records, "www.nhc.noaa.gov")

    def test_not_tls(self):
        assert read_hello(b"GET / HTTP/1.1\r\n\r\n") == (b"GET /", None)


class TestAllowedHosts:
    def test_matches_the_noaa_hosts_the_integration_uses(self):
        source = ROOT / "custom_components" / "noaa_it_all"
        hosts = set()
        for path in source.rglob("*.py"):
            hosts |= set(re.findall(r"https://([a-z0-9.-]+\.(?:noaa|weather)\.gov)", path.read_text()))
        assert hosts == relay.ALLOWED

    def test_add_host_args(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["noaa_relay.py", "--add-host-args"])
        relay.main()
        args = capsys.readouterr().out.split()
        assert args[0::2] == ["--add-host"] * len(relay.ALLOWED)
        assert set(args[1::2]) == {f"{host}:127.0.0.1" for host in relay.ALLOWED}


async def through_relay(host, proxy_status):
    """Send a ClientHello for host through the relay to a fake proxy.

    Returns what the proxy was asked to CONNECT to (None if never contacted), the ClientHello sent
    and what came back to the client. After a 200, the fake proxy echoes the tunnel.
    """
    asked = []

    async def fake_proxy(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        asked.append(head.split(b" ")[1].decode())
        writer.write(f"HTTP/1.1 {proxy_status} x\r\n\r\n".encode())
        if proxy_status == 200:
            while data := await reader.read(65536):
                writer.write(data)
        writer.close()

    proxy = await asyncio.start_server(fake_proxy, "127.0.0.1", 0)
    proxy_addr = proxy.sockets[0].getsockname()[:2]
    server = await asyncio.start_server(
        lambda r, w: relay.handle(r, w, proxy=proxy_addr), "127.0.0.1", 0)
    reader, writer = await asyncio.open_connection(*server.sockets[0].getsockname()[:2])
    hello = client_hello(host)
    writer.write(hello + b"ping")
    writer.write_eof()
    back = await asyncio.wait_for(reader.read(), 10)
    writer.close()
    server.close()
    proxy.close()
    return (asked[0] if asked else None), hello, back


class TestRelay:
    def test_tunnels_an_allowed_host_through_the_proxy(self, capsys):
        asked, hello, back = _run(through_relay("api.weather.gov", 200))
        assert asked == "api.weather.gov:443"
        assert back == hello + b"ping"
        assert "host=api.weather.gov connect=200" in capsys.readouterr().out

    def test_refuses_other_hosts_without_asking_the_proxy(self, capsys):
        asked, _, back = _run(through_relay("example.com", 200))
        assert asked is None
        assert back == b""
        assert "host=example.com connect=refused-sni" in capsys.readouterr().out

    def test_stops_when_the_proxy_denies(self, capsys):
        asked, _, back = _run(through_relay("api.weather.gov", 403))
        assert asked == "api.weather.gov:443"
        assert back == b""
        assert "host=api.weather.gov connect=403" in capsys.readouterr().out
