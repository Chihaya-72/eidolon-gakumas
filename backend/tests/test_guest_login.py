from dataclasses import replace
import hashlib
from pathlib import Path

from eidolon.config import Settings
from tests.conftest import ClientFactory, agree_to_terms, store_in
from tests.fakes import FakeLLM
from tests.test_service_status import backend_of


async def test_guest_login_is_opt_in(make_client: ClientFactory):
    client = make_client(FakeLLM(), user=None)
    assert not (await client.get('/api/auth/providers')).json()['guest_login']
    assert (await client.post('/api/auth/guest-login')).status_code == 404


async def test_guest_needs_consent_and_cannot_become_admin(make_client: ClientFactory, settings: Settings):
    client = make_client(FakeLLM(), user=None, settings=replace(settings, guest_login=True))
    response = await client.post('/api/auth/guest-login')
    assert response.status_code == 204
    assert 'HttpOnly' in response.headers['set-cookie']
    assert (await client.get('/api/account')).status_code == 428
    await agree_to_terms(client)
    account = (await client.get('/api/account')).json()
    assert account['name'] == '游客' and not account['is_admin']
    assert (await client.get('/api/admin')).status_code == 404


async def test_browsers_are_isolated_and_logout_preserves_guest_identity(make_client: ClientFactory, settings: Settings):
    enabled = replace(settings, guest_login=True)
    first = make_client(FakeLLM(), user=None, settings=enabled)
    second = make_client(FakeLLM(), user=None, settings=enabled)
    ids = []
    for client in (first, second):
        assert (await client.post('/api/auth/guest-login')).status_code == 204
        await agree_to_terms(client)
        ids.append((await client.get('/api/account')).json()['id'])
    assert ids[0] != ids[1]
    await first.post('/api/auth/logout')
    assert (await first.post('/api/auth/guest-login')).status_code == 204
    assert (await first.get('/api/account')).json()['id'] == ids[0]
    backend = backend_of(first)
    user = await backend.store.get_user(ids[0])
    assert user.is_guest and not user.is_admin


async def test_guest_cannot_claim_bootstrap_even_after_restart(tmp_path: Path):
    path = tmp_path / 'guests.db'
    async with store_in(path) as store:
        guest, token = await store.guest_user(None)
        assert guest.is_guest and not guest.is_admin
        stored = await store._db.read(lambda db: db.execute('SELECT token_hash FROM guest_browsers').fetchone()[0])
        assert stored == hashlib.sha256(token.encode()).hexdigest()
    async with store_in(path) as store:
        assert not (await store.get_user(guest.id)).is_admin
        assert (await store.guest_user(token))[0].id == guest.id
        owner = await store.create_user('owner')
        assert owner.is_admin


async def test_existing_session_is_not_replaced_by_guest_login(make_client: ClientFactory, settings: Settings):
    client = make_client(FakeLLM(), settings=replace(settings, guest_login=True))
    before = (await client.get('/api/account')).json()['id']
    assert (await client.post('/api/auth/guest-login')).status_code == 204
    assert (await client.get('/api/account')).json()['id'] == before


async def test_deleting_guest_removes_browser_binding(tmp_path: Path):
    async with store_in(tmp_path / 'delete.db') as store:
        guest, token = await store.guest_user(None)
        await store.delete_user(guest.id, [])
        replacement, _ = await store.guest_user(token)
        assert replacement.id != guest.id and not replacement.is_admin


async def test_access_password_protects_guest_creation(make_client: ClientFactory, settings: Settings):
    client = make_client(FakeLLM(), user=None, settings=replace(settings, guest_login=True))
    backend = backend_of(client)
    await backend.access.save(True, 'eight888', 'administrator')
    assert (await client.post('/api/auth/guest-login')).status_code == 403
    assert await backend.store.list_users() == []
    assert (await client.post('/api/access/verify', json={'password': 'eight888'})).status_code == 200
    assert (await client.post('/api/auth/guest-login')).status_code == 204
