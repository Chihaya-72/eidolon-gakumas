"""Admission setup failures may neither consume a queue use nor keep the service slot."""

import asyncio
from pathlib import Path

import pytest

from eidolon.bar import BarClosed
from eidolon.own_keys import BroughtKeys
from tests.conftest import CharacterConfig, ClientFactory
from tests.fakes import FakeLLM, FakeRandom
from tests.test_bar_visit import COMING_IN, enter, mano_alone
from tests.test_live_config_services import backend_of


@pytest.fixture
def characters(tmp_path: Path) -> CharacterConfig:
    return mano_alone(tmp_path / "characters")


@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_replacement_setup_failure_settles_the_new_admission_and_releases_its_slot(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch, failure: str,
):
    client = make_client(FakeLLM(COMING_IN), random=FakeRandom(*([0] * 30)))
    await enter(client)
    backend = backend_of(client)
    user = (await client.get("/api/account")).json()["id"]
    original = backend.bar._cut_short

    async def fail_replacement(visit):
        await original(visit)
        if failure == "cancel":
            raise asyncio.CancelledError()
        raise RuntimeError("could not finish replacing the visit")

    monkeypatch.setattr(backend.bar, "_cut_short", fail_replacement)
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else RuntimeError):
        await backend.bar.enter(user, BroughtKeys())
    await backend.bar.aclose()  # finishes cancellation-safe settlement
    assert await backend.queue.counts() == {user: 1}  # only the completed first reply
    visits = await backend.database.read(lambda db: db.execute(
        "SELECT COUNT(*) FROM usage WHERE user_id = ? AND kind = 'visit'", (user,)
    ).fetchone()[0])
    assert visits == 1
    assert not backend.bar._visits
    assert (await backend.queue.enqueue(user, "turn", "/api/next"))["state"] == "ready"


async def test_bar_disabled_during_wait_does_not_count_or_keep_a_service_slot(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch,
):
    client = make_client(FakeLLM(), random=FakeRandom(*([0] * 20)))
    backend = backend_of(client)
    user = (await client.get("/api/account")).json()["id"]
    held = await backend.queue.acquire(user, "call", resource="existing-call")
    entering = asyncio.create_task(backend.bar.enter(user, BroughtKeys()))
    await asyncio.sleep(0.02)
    monkeypatch.setattr(backend.bar, "_is_on", lambda: False)
    await held.release()
    with pytest.raises(BarClosed):
        await asyncio.wait_for(entering, timeout=2)
    assert await backend.queue.counts() == {}
    visits = await backend.database.read(lambda db: db.execute(
        "SELECT COUNT(*) FROM usage WHERE user_id = ? AND kind = 'visit'", (user,)
    ).fetchone()[0])
    assert visits == 0
    assert (await backend.queue.enqueue(user, "turn", "/api/next"))["state"] == "ready"
