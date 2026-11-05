"""Signing up and in with a name and a password, the one claim of admin, and the switch for
users' own API keys."""

from dataclasses import replace
from pathlib import Path

from eidolon.config import Settings
from eidolon.passwords import ADMIN_SUFFIX
from tests.conftest import ClientFactory, agree_to_terms, store_in
from tests.fakes import FakeLLM
from tests.test_service_status import backend_of

PASSWORD = "correct horse battery"


def client_of(make_client: ClientFactory, settings: Settings, **changes):
    return make_client(FakeLLM(), user=None, settings=replace(settings, password_login=True, **changes))


async def register(client, username, password=PASSWORD, **body):
    return await client.post(
        "/api/auth/password-register", json={"username": username, "password": password, **body}
    )


async def account_of(client) -> dict:
    await agree_to_terms(client)
    return (await client.get("/api/account")).json()


async def test_is_opt_in(make_client: ClientFactory):
    client = make_client(FakeLLM(), user=None)
    assert not (await client.get("/api/auth/providers")).json()["password_login"]
    assert (await register(client, "alice")).status_code == 404


async def test_first_plain_user_is_no_admin_and_first_suffix_is(
    make_client: ClientFactory, settings: Settings
):
    client = client_of(make_client, settings)
    assert (await client.get("/api/auth/providers")).json()["password_login"]
    assert (await register(client, "plain")).status_code == 204
    assert not (await account_of(client))["is_admin"]
    await client.post("/api/auth/logout")

    assert (await register(client, "boss" + ADMIN_SUFFIX)).status_code == 204
    account = await account_of(client)
    assert account["is_admin"] and account["name"] == "boss"
    await client.post("/api/auth/logout")

    # The claim is gone, and the suffix is then as bad as any other `+`.
    assert (await register(client, "second" + ADMIN_SUFFIX)).status_code == 422
    assert (await client.post("/api/auth/password-login", json={
        "username": "second", "password": PASSWORD,
    })).status_code == 401


async def test_plain_user_is_not_promoted_when_the_server_restarts(tmp_path: Path):
    path = tmp_path / "users.db"
    async with store_in(path) as store:
        user = await store.create_password_user("plain", "plain", "hash", False, None)
        assert not user.is_admin
    async with store_in(path) as store:
        assert not (await store.get_user(user.id)).is_admin
        first_oauth = await store.create_user("oauth")
        assert first_oauth.is_admin


async def test_an_existing_first_admin_closes_the_claim(
    make_client: ClientFactory, settings: Settings
):
    client = client_of(make_client, settings)
    await backend_of(client).store.create_user("first")
    assert (await register(client, "late" + ADMIN_SUFFIX)).status_code == 422


async def test_names(make_client: ClientFactory, settings: Settings):
    client = client_of(make_client, settings)
    for bad in ("a", "a" * 21, "has space", "a+b", "a<b>", "a.b", "a​b", "a/b", "admin", "管理员"):
        assert (await register(client, bad)).status_code == 422, bad
    for good in ("星南_01", "花海咲季", "Alice"):
        assert (await register(client, good)).status_code == 204, good
        await client.post("/api/auth/logout")
    assert (await register(client, "alice")).status_code == 409  # case
    assert (await register(client, "ＡＬＩＣＥ")).status_code == 409  # width


async def test_passwords_and_signing_in(make_client: ClientFactory, settings: Settings):
    client = client_of(make_client, settings)
    assert (await register(client, "alice", "short")).status_code == 422
    assert (await register(client, "alice", "a" * 129)).status_code == 422
    assert (await register(client, "alicealice", "AliceAlice")).status_code == 422
    response = await register(client, "alice")
    assert response.status_code == 204
    assert "HttpOnly" in response.headers["set-cookie"]
    await client.post("/api/auth/logout")

    login = {"username": "alice", "password": PASSWORD}
    wrong = await client.post("/api/auth/password-login", json=login | {"password": "wrong-one"})
    unknown = await client.post("/api/auth/password-login", json=login | {"username": "nobody"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert PASSWORD not in str(wrong.json())
    assert (await client.post("/api/auth/password-login", json=login)).status_code == 204
    assert (await client.get("/api/account")).status_code == 428


async def test_repeated_failures_are_throttled(make_client: ClientFactory, settings: Settings):
    client = client_of(make_client, settings)
    await register(client, "alice")
    await client.post("/api/auth/logout")
    login = {"username": "alice", "password": "wrong-password"}
    for _ in range(5):
        assert (await client.post("/api/auth/password-login", json=login)).status_code == 401
    refused = await client.post("/api/auth/password-login", json=login | {"password": PASSWORD})
    assert refused.status_code == 429 and "retry-after" in refused.headers


async def test_sign_ups_are_throttled(make_client: ClientFactory, settings: Settings):
    client = client_of(make_client, settings)
    for _ in range(3):
        assert (await register(client, "a")).status_code == 422  # costs no hash, so no count
    for i in range(10):
        assert (await register(client, f"user{i}")).status_code == 204
    assert (await register(client, "alice")).status_code == 429


async def test_banned_and_deleted_user_cannot_come_back(
    make_client: ClientFactory, settings: Settings
):
    client = client_of(make_client, settings)
    await register(client, "alice")
    user_id = (await account_of(client))["id"]
    store = backend_of(client).store
    await client.post("/api/auth/logout")
    await store.set_banned(user_id, backend_of(client).clock(), "note")
    login = {"username": "alice", "password": PASSWORD}
    assert (await client.post("/api/auth/password-login", json=login)).status_code == 403
    await backend_of(client).accounts.delete(user_id)
    assert (await client.post("/api/auth/password-login", json=login)).status_code == 401
    assert (await register(client, "ALICE")).status_code == 403


async def test_deleting_frees_the_name(make_client: ClientFactory, settings: Settings):
    client = client_of(make_client, settings)
    await register(client, "alice")
    await agree_to_terms(client)
    assert (await client.post("/api/account/delete", json={"confirm": True})).status_code == 204
    assert (await register(client, "alice")).status_code == 204


async def test_invite_only_needs_a_link_but_the_claim_does_not(
    make_client: ClientFactory, settings: Settings
):
    client = client_of(make_client, settings, registration="invite")
    assert (await register(client, "boss" + ADMIN_SUFFIX)).status_code == 204
    await client.post("/api/auth/logout")
    assert (await register(client, "alice")).status_code == 403
    assert (await register(client, "alice", invite="nope")).status_code == 403


OWN_LLM = {
    "base_url": "https://llm.example.com/v1", "api_key": "sk-abcdefgh", "model": "m",
    "protocol": "chat-completions",
}


async def test_own_keys_off_refuses_tries_and_ignores_what_is_brought(
    make_client: ClientFactory, settings: Settings
):
    client = client_of(make_client, settings, own_keys=False)
    await register(client, "alice")
    account = await account_of(client)
    assert account["own_keys_allowed"] is False
    for path in ("llm/check", "memory-llm/check", "llm/models", "tts/check", "stt/check", "image/check"):
        body = {"api_key": "sk-abcdefgh", "provider": "soniox", "api_format": "openai"} | OWN_LLM
        response = await client.post(f"/api/account/keys/{path}", json=body)
        assert response.status_code == 403, path

    from eidolon.account_api import OwnKeysInput, brought_keys

    backend = backend_of(client)
    own = OwnKeysInput.model_validate({"llm": OWN_LLM})
    assert brought_keys(backend, own).llm is None


async def test_admin_switches_own_keys_at_once(make_client: ClientFactory, settings: Settings):
    client = client_of(make_client, settings)
    await register(client, "boss" + ADMIN_SUFFIX)
    assert (await account_of(client))["own_keys_allowed"] is True
    assert (await client.put("/api/admin/config/own_keys", json={"enabled": "no"})).status_code == 422
    assert (await client.put("/api/admin/config/own_keys", json={"enabled": False})).status_code == 200
    assert (await client.get("/api/account")).json()["own_keys_allowed"] is False
    assert (await client.delete("/api/admin/config/own_keys")).status_code == 200
    assert (await client.get("/api/account")).json()["own_keys_allowed"] is True


async def test_a_plain_user_cannot_flip_the_switch(make_client: ClientFactory, settings: Settings):
    client = client_of(make_client, settings)
    await register(client, "alice")
    await agree_to_terms(client)
    response = await client.put("/api/admin/config/own_keys", json={"enabled": False})
    assert response.status_code in (403, 404)


async def guest(make_client: ClientFactory, settings: Settings):
    client = make_client(FakeLLM(), user=None, settings=replace(settings, guest_login=True))
    assert (await client.post("/api/auth/guest-login")).status_code == 204
    await agree_to_terms(client)
    return client, (await client.get("/api/account")).json()["id"]


async def test_guests_have_their_own_limit_and_a_shared_one(
    make_client: ClientFactory, settings: Settings
):
    from eidolon.config import GuestLimits
    from eidolon.usage import OverLimit

    client, first = await guest(make_client, settings)
    backend = backend_of(client)
    second = (await backend.store.guest_user(None))[0].id
    await backend.config.save("guest_limits", {"turns_per_hour": 2, "calls_per_hour": 0, "all_guests_per_hour": 3})
    assert backend.config.guest_limits.turns_per_hour == 2
    assert GuestLimits().calls_per_hour == 0
    usage = backend.usage
    await usage.take(first, "turn")
    await usage.take(first, "turn")
    for refused, kind in ((first, "turn"), (first, "call")):
        try:
            await usage.take(refused, kind)
            raise AssertionError(kind)
        except OverLimit:
            pass
    await usage.take(second, "turn")  # the third of all guests'
    try:
        await usage.take(second, "turn")
        raise AssertionError("all guests")
    except OverLimit:
        pass
    await usage.take(second, "turn", exempt=True)  # on their own keys
    member = await backend.store.create_user("member")
    await usage.take(member.id, "turn")


async def test_new_guests_per_address_are_limited(make_client: ClientFactory, settings: Settings):
    client = make_client(FakeLLM(), user=None, settings=replace(settings, guest_login=True))
    for _ in range(3):
        client.cookies.clear()
        assert (await client.post("/api/auth/guest-login")).status_code == 204
    kept = dict(client.cookies)
    client.cookies.clear()
    refused = await client.post("/api/auth/guest-login")
    assert refused.status_code == 429 and "retry-after" in refused.headers
    client.cookies.update(kept)  # the same browser comes back
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.post("/api/auth/guest-login")).status_code == 204
    backend = backend_of(client)
    await backend.config.save("guest_limits", {"new_guests_per_address_per_hour": 0})
    client.cookies.clear()
    assert (await client.post("/api/auth/guest-login")).status_code == 403
