"""Reading her words aloud on the deployer's Irodori-TTS server (`irodori`): her Japanese
only, cues as Irodori's emoji, names as their readings, long segments split, the parts
voiced one request after another (made again while the server is busy) and joined into
one WAV; failing, only that it failed.

Irodori faked at its transport."""

import io
import json
import wave
from pathlib import Path

import httpx
import pytest

from eidolon.config import IrodoriSettings
from eidolon.irodori import MAX_CHARS, IrodoriReadAloud, irodori_text, joined, parts
from eidolon.read_aloud import ReadAloudFailed
from eidolon.readings import Reading
from eidolon.reply_format import Segment
from tests.conftest import activity_in

SETTINGS = IrodoriSettings(base_url="http://100.96.0.4:18086/v1", api_key="k")
RATE = 24000


def clip(seconds: float) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"\1\0" * int(RATE * seconds))
    return out.getvalue()


def frames(wav: bytes) -> int:
    with wave.open(io.BytesIO(wav), "rb") as r:
        return r.getnframes()


def test_cues_become_emoji_and_unknown_ones_are_dropped() -> None:
    assert irodori_text("[shyly] え、えっと……ありがとう。") == "🫣え、えっと……ありがとう。"
    assert irodori_text("[laughing nervously] あはは") == "🤭😰あはは"
    assert irodori_text("[looking at the sky] 晴れたね") == "晴れたね"
    assert irodori_text("<whisper>内緒だよ</whisper>") == "👂内緒だよ"


def test_names_are_said_as_their_readings() -> None:
    readings = [Reading("藤田琴音", "ふじた ことね", ""), Reading("琴音", "ことね", "")]
    assert irodori_text("藤田琴音です！琴音って呼んで", readings) == "ふじたことねです！ことねって呼んで"


def test_long_text_is_split_at_its_sentences() -> None:
    sentence = "あ" * 99 + "。"
    split = parts(sentence * 5)
    assert all(len(p) <= MAX_CHARS for p in split)
    assert "".join(split) == sentence * 5
    assert parts("い" * (MAX_CHARS + 10)) == ["い" * MAX_CHARS, "い" * 10]


def test_clips_are_joined_with_a_pause() -> None:
    assert frames(joined([clip(1), clip(0.5)], 0.25)) == int(RATE * 1.75)


async def test_each_segment_is_voiced_and_busy_is_waited_out(tmp_path: Path) -> None:
    asked: list[dict] = []
    busy = [True]

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://100.96.0.4:18086/v1/audio/speech"
        assert request.headers["Authorization"] == "Bearer k"
        if busy.pop() if busy else False:
            return httpx.Response(429, headers={"Retry-After": "0"})
        asked.append(json.loads(request.content))
        return httpx.Response(200, content=clip(1), headers={"Content-Type": "audio/wav"})

    async with activity_in(tmp_path / "db.sqlite") as activity:
        irodori = IrodoriReadAloud(SETTINGS, activity, transport=httpx.MockTransport(handle))
        audio = await irodori.voice(
            "kotone", [Segment("[happily] やった！", "太好了！"), Segment("がんばるね", "我会加油的")]
        )
    assert [a["input"] for a in asked] == ["😊やった！", "がんばるね"]
    assert {a["voice"] for a in asked} == {"kotone"}
    assert {a["model"] for a in asked} == {"irodori-v4-large-int8"}
    assert frames(audio) == int(RATE * 2.25)


async def test_a_failure_says_only_that_it_failed(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Synthesis failed"})

    async with activity_in(tmp_path / "db.sqlite") as activity:
        irodori = IrodoriReadAloud(SETTINGS, activity, transport=httpx.MockTransport(handle))
        with pytest.raises(ReadAloudFailed):
            await irodori.voice("kotone", [Segment("やった", "")])
