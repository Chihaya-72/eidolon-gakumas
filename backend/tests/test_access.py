"""Password gate, persistent block lists and recovery without live external services."""

import asyncio
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from starlette.requests import Request

from eidolon.access import ACCESS_COOKIE, BROWSER_COOKIE, AccessGate, client_ip
from eidolon.config import Settings
from eidolon.data_access import Database
from tests.conftest import ClientFactory
from tests.fakes import FakeClock, FakeLLM


@pytest.fixture
async def gate(tmp_path: Path):
    db = Database(tmp_path / "gate.db")
    clock = FakeClock()
    gate = AccessGate(db, clock, "test-secret")
    yield gate, clock
    await db.close()


async def test_disabled_by_default_and_password_required_to_enable(gate):
    access, _ = gate
    assert (await access.state("browser", "192.0.2.1", None))["passed"]
    with pytest.raises(ValueError, match="先设置密码"):
        await access.save(True, None, "admin")
    with pytest.raises(ValueError, match="8 至 128"):
        await access.save(True, "short", "admin")


async def test_grants_are_browser_bound_expire_and_change_with_password(gate):
    access, clock = gate
    await access.save(True, "password-one", "admin")
    state, token = await access.verify("password-one", "a", "192.0.2.1")
    assert state["passed"] and token
    assert (await access.state("a", "192.0.2.1", token))["passed"]
    assert not (await access.state("b", "192.0.2.1", token))["passed"]
    clock.advance(days=30)
    assert not (await access.state("a", "192.0.2.1", token))["passed"]
    _, token = await access.verify("password-one", "a", "192.0.2.1")
    await access.save(True, "password-two", "admin")
    assert not (await access.state("a", "192.0.2.1", token))["passed"]
    await access.disable()
    assert (await access.state("a", "192.0.2.1", None))["passed"]


async def test_three_concurrent_failures_ban_browser_and_ip_and_survive_restart(gate):
    access, clock = gate
    await access.save(True, "password-one", "admin")
    values = await asyncio.gather(*(access.verify("wrong", "a", "192.0.2.1") for _ in range(3)))
    assert sorted(value[0]["remaining"] for value in values) == [0, 1, 2]
    assert (await access.state("a", "192.0.2.2", None))["banned"]
    assert (await access.state("b", "192.0.2.1", None))["banned"]
    restarted = AccessGate(access._db, clock, "test-secret")
    assert (await restarted.verify("password-one", "a", "192.0.2.1"))[0]["banned"]
    [ban] = await restarted.bans()
    await restarted.unban(ban["id"])
    assert (await restarted.verify("password-one", "a", "192.0.2.1"))[0]["passed"]


async def test_ip_failure_count_cannot_be_reset_by_changing_browser(gate):
    access, _ = gate
    await access.save(True, "password-one", "admin")
    for browser in ("a", "b", "c"):
        await access.verify("wrong", browser, "192.0.2.1")
    assert (await access.state("fresh-browser", "192.0.2.1", None))["banned"]


async def test_success_resets_failures_and_block_overrides_existing_grant(gate):
    access, _ = gate
    await access.save(True, "password-one", "admin")
    await access.verify("wrong", "a", "192.0.2.1")
    await access.verify("wrong", "a", "192.0.2.1")
    _, token = await access.verify("password-one", "a", "192.0.2.1")
    for attempt in range(3):
        state, _ = await access.verify("wrong", "a", "192.0.2.1")
        assert state["banned"] == (attempt == 2)
    assert not (await access.state("a", "192.0.2.1", token))["passed"]


def test_forwarded_ip_only_from_trusted_proxy_on_public_deployment(settings: Settings):
    def request(peer: str, forwarded: str) -> Request:
        return Request({"type": "http", "client": (peer, 8000), "headers": [(b"x-eidolon-client-ip", forwarded.encode())]})
    public = replace(settings, dev_login=False, domain="example.com")
    assert client_ip(request("127.0.0.1", "192.0.2.1"), public) == "192.0.2.1"
    assert client_ip(request("192.0.2.2", "192.0.2.1"), public) == "192.0.2.2"
    assert client_ip(request("127.0.0.1", "192.0.2.1, 192.0.2.2"), public) == "127.0.0.1"
    assert client_ip(request("127.0.0.1", "192.0.2.1"), settings) == "127.0.0.1"


async def test_gate_protects_business_and_admin_api_while_health_and_entry_work(make_client: ClientFactory):
    admin = make_client(FakeLLM())
    saved = await admin.put("/api/admin/access", json={"enabled": True, "password": "password-one"})
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"enabled": True, "password_set": True}
    assert ACCESS_COOKIE in admin.cookies and BROWSER_COOKIE in admin.cookies
    assert (await admin.get("/api/admin")).status_code == 200
    async with httpx.AsyncClient(transport=admin._transport, base_url="http://test", headers=admin.headers) as visitor:
        for path in ("/api/characters", "/api/admin", "/api/account"):
            response = await visitor.get(path)
            assert response.status_code == 403 and response.json()["code"] == "access_required"
        assert (await visitor.get("/api/health")).status_code == 200
        assert not (await visitor.get("/api/access/status")).json()["passed"]
        response = await visitor.post("/api/access/verify", json={"password": "password-one"})
        assert response.status_code == 200 and response.json()["passed"]
        assert (await visitor.get("/api/characters")).status_code == 200
        response = await visitor.put("/api/admin/access", json={"enabled": False})
        assert response.status_code == 404
        for _ in range(3):
            response = await visitor.post("/api/access/verify", json={"password": "wrong"})
        assert response.status_code == 403 and response.json()["banned"]
        assert (await visitor.get("/api/characters")).json()["code"] == "access_banned"


async def test_anonymous_verification_requires_own_origin(make_client: ClientFactory):
    admin = make_client(FakeLLM())
    await admin.put("/api/admin/access", json={"enabled": True, "password": "password-one"})
    response = await admin.post("/api/access/verify", json={"password": "wrong"}, headers={"origin": "https://other.example"})
    assert response.status_code == 403
    assert (await admin.get("/api/admin/access/bans")).json() == []


async def test_server_recovery_commands_work_without_model_configuration(make_client: ClientFactory, admin):
    client = make_client(FakeLLM())
    await client.put("/api/admin/access", json={"enabled": True, "password": "password-one"})
    for _ in range(3):
        await client.post("/api/access/verify", json={"password": "wrong"})
    assert (await client.get("/api/characters")).status_code == 403
    admin.run("access", "unban")
    assert (await client.post("/api/access/verify", json={"password": "password-one"})).status_code == 200
    admin.run("access", "disable")
    client.cookies.clear()
    assert (await client.get("/api/characters")).status_code == 200


async def test_password_hashing_is_bounded_and_rechecks_ban_after_waiting(gate, monkeypatch):
    import threading
    import time
    import eidolon.access

    access, _ = gate
    await access.save(True, "password-one", "admin")
    calls = 0
    running = 0
    peak = 0
    lock = threading.Lock()

    def matches(password, encoded):
        nonlocal calls, running, peak
        with lock:
            calls += 1
            running += 1
            peak = max(peak, running)
        time.sleep(0.01)
        with lock:
            running -= 1
        return False

    monkeypatch.setattr(eidolon.access, "_matches", matches)
    await asyncio.gather(*(access.verify("wrong", "a", "192.0.2.1") for _ in range(20)))
    assert peak == 1
    assert calls == 3
    assert (await access.state("new-browser", "192.0.2.1", None))["banned"]
