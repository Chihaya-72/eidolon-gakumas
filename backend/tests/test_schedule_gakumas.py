"""The calendar can read and keep the active pack's weekly jobs over HTTP."""

from dataclasses import replace
from datetime import UTC, datetime

from eidolon.config import Settings
from tests.conftest import ClientFactory
from tests.fakes import FakeClock, FakeLLM
from tests.gakumas.test_pack import PACK


async def test_active_pack_calendar_reads_the_previously_failing_week_and_keeps_it(
    make_client: ClientFactory, settings: Settings,
):
    client = make_client(
        FakeLLM(),
        settings=replace(settings, characters_path=PACK / "characters.toml"),
        clock=FakeClock(datetime(2026, 11, 6, tzinfo=UTC)),
    )

    response = await client.get("/api/schedule", headers={"X-Timezone": "Asia/Singapore"})

    assert response.status_code == 200, response.text
    schedule = response.json()
    assert schedule["enabled"] is True
    assert schedule["this_week"]["id"] == "2026-11-02"
    assert schedule["timezone"] == "Asia/Singapore"
    assert {j["character_id"] for j in schedule["this_week"]["jobs"]} == {
        "misuzu", "temari", "hiro", "lilja",
    }
    assert 13 <= sum(j["length"] for j in schedule["this_week"]["jobs"]) <= 16
    assert (await client.get("/api/schedule", headers={"X-Timezone": "Asia/Singapore"})).json() == schedule
