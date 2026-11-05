"""The actual HTTP operation must consume its own ticket and release its service slot."""

import asyncio

import httpx

from eidolon.usage import UserLimits
from tests.conftest import ClientFactory
from tests.fakes import FakeLLM, FakeLLMService
from tests.test_live_config_services import backend_of
from tests.test_own_llm import LLM, REPLY
from tests.test_text_turn import start_conversation


async def ticket(client: httpx.AsyncClient, resource: str, **extra) -> dict:
    response = await client.post("/api/queue", json={"kind": "turn", "resource": resource} | extra)
    assert response.status_code == 200, response.text
    return response.json()


async def user_id(client: httpx.AsyncClient) -> str:
    return (await client.get("/api/account")).json()["id"]


async def test_a_turn_consumes_its_ticket_and_releases_after_streaming(make_client: ClientFactory):
    client = make_client(FakeLLM(REPLY))
    backend = backend_of(client)
    user = await user_id(client)
    conversation = await start_conversation(client)
    path = f"/api/conversations/{conversation}/turns"
    waiting = await ticket(client, path)
    assert waiting["state"] == "ready"
    assert await backend.queue.counts() == {}
    response = await client.post(
        path, json={"text": "在吗"}, headers={"X-Queue-Ticket": waiting["id"]}
    )
    assert response.status_code == 200, response.text
    assert '"type": "done"' in response.text
    assert await backend.queue.counts() == {user: 1}
    assert (await ticket(client, path))["state"] == "ready"
    replayed = await client.post(
        path, json={"text": "再问一次"}, headers={"X-Queue-Ticket": waiting["id"]}
    )
    assert replayed.status_code == 410


async def test_direct_requests_cannot_bypass_the_same_queue(make_client: ClientFactory):
    llm = FakeLLM(REPLY)
    client = make_client(llm)
    backend = backend_of(client)
    user = await user_id(client)
    conversation = await start_conversation(client)
    held = await backend.queue.acquire(user, "call", resource="existing-call")
    pending = asyncio.create_task(client.post(
        f"/api/conversations/{conversation}/turns", json={"text": "在吗"}
    ))
    try:
        await asyncio.sleep(0.05)
        assert not pending.done() and not llm.prompts
        assert await backend.queue.counts() == {}
    finally:
        await held.release()
    response = await asyncio.wait_for(pending, timeout=3)
    assert response.status_code == 200, response.text
    assert await backend.queue.counts() == {user: 1}


async def test_real_own_keys_bypass_but_false_browser_hints_do_not(
    make_client: ClientFactory, own_llm: FakeLLMService,
):
    own_llm.llm = FakeLLM(REPLY)
    client = make_client(FakeLLM())
    backend = backend_of(client)
    user = await user_id(client)
    conversation = await start_conversation(client)
    path = f"/api/conversations/{conversation}/turns"
    held = await backend.queue.acquire(user, "call", resource="existing-call")
    try:
        own = await asyncio.wait_for(client.post(
            path, json={"text": "在吗", "own_keys": {"llm": LLM}}
        ), timeout=3)
        assert own.status_code == 200, own.text
        assert await backend.queue.counts() == {}
        # Supplying exemption-looking JSON without actual keys has no effect.
        hinted = await ticket(client, path, own=True, own_services=["llm"])
        assert hinted["state"] == "waiting"
        assert (await client.delete(f"/api/queue/{hinted['id']}")).status_code == 204
    finally:
        await held.release()


async def test_quota_refusal_does_not_count_and_releases_the_ready_reservation(
    make_client: ClientFactory,
):
    client = make_client(FakeLLM())
    backend = backend_of(client)
    await backend.usage.set_user_limits(
        await user_id(client), UserLimits(turns_per_hour=0, calls_per_hour=None)
    )
    conversation = await start_conversation(client)
    path = f"/api/conversations/{conversation}/turns"
    waiting = await ticket(client, path)
    response = await client.post(
        path, json={"text": "在吗"}, headers={"X-Queue-Ticket": waiting["id"]}
    )
    assert response.status_code == 429, response.text
    assert await backend.queue.counts() == {}
    assert (await ticket(client, path))["state"] == "ready"


async def test_queue_ticket_must_match_operation_and_conversation(make_client: ClientFactory):
    client = make_client(FakeLLM())
    first = await start_conversation(client, "mano")
    second = await start_conversation(client, "kogane")
    waiting = await ticket(client, f"/api/conversations/{first}/turns")
    response = await client.post(
        f"/api/conversations/{second}/turns", json={"text": "在吗"},
        headers={"X-Queue-Ticket": waiting["id"]},
    )
    assert response.status_code == 409, response.text
    # The mismatched ticket had reached the slot, so giving it up this way counts as a use.
    assert await backend_of(client).queue.counts() == {await user_id(client): 1}
    assert (await client.post("/api/queue", json={"kind": "call", "resource": "/api/offer"})).status_code == 422
    response = await client.post("/api/queue", json={
        "kind": "call", "resource": "/api/offer", "target": first,
    })
    assert response.status_code == 200, response.text


async def test_call_and_turn_tickets_cannot_name_another_users_conversation(make_client: ClientFactory):
    owner = make_client(FakeLLM(), user="owner")
    conversation = await start_conversation(owner)
    other = make_client(FakeLLM(), user="other")
    response = await other.post("/api/queue", json={
        "kind": "turn", "resource": f"/api/conversations/{conversation}/turns",
    })
    assert response.status_code == 404
    response = await other.post("/api/queue", json={
        "kind": "call", "resource": "/api/offer", "target": conversation,
    })
    assert response.status_code == 404


async def test_logout_while_waiting_cannot_later_start_an_api_operation(make_client: ClientFactory):
    llm = FakeLLM(REPLY)
    client = make_client(llm)
    backend = backend_of(client)
    user = await user_id(client)
    conversation = await start_conversation(client)
    held = await backend.queue.acquire(user, "call", resource="existing-call")
    pending = asyncio.create_task(client.post(
        f"/api/conversations/{conversation}/turns", json={"text": "在吗"}
    ))
    await asyncio.sleep(0.05)
    assert (await client.post("/api/auth/logout")).status_code == 204
    await held.release()
    response = await asyncio.wait_for(pending, timeout=3)
    assert response.status_code == 403, response.text
    assert not llm.prompts and await backend.queue.counts() == {}
