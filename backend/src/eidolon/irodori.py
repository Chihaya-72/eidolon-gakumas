"""Reading her words aloud on the deployer's own Irodori-TTS server (GLOSSARY.md「朗读」), for
the characters the configuration gives an `irodori_voice`: Kotone's, voiced by a LoRA of hers
on Irodori-TTS v4 Large, on a home GPU the backend reaches over Cloudflare Mesh.

As on Fish Audio (`read_aloud`), only her Japanese is said, a segment at a time. Irodori is
told how each is to be said by emoji in the text (its「絵文字による感情制御」): the delivery
cues she writes in English, `[shyly] え、えっと……`, become the emoji Irodori learnt for them,
`🫣え、えっと……` (`irodori_text`); a cue with no emoji for it is dropped, not read out. Names
are said as the readings have them (`readings`), written in kana, as Irodori has no
pronunciation dictionary.

The server voices one request at a time and up to 300 characters, so a longer segment is
split at its sentences, the parts voiced one after another (`_ONE_AT_A_TIME`, retried while
it answers 429) and joined with a short pause between, as one WAV. It costs nothing but the
deployer's GPU, so counts towards no limit; each request is a service call recorded on its
own (`activity.timed`). Failing, it says only that it failed (`read_aloud.ReadAloudFailed`)."""

import asyncio
import io
import logging
import re
import wave
from collections.abc import Sequence

import httpx

from eidolon.activity import ActivityLog, Origin, host, timed
from eidolon.config import IrodoriSettings
from eidolon.delivery_cues import voiced
from eidolon.read_aloud import ReadAloudFailed
from eidolon.readings import Reading
from eidolon.reply_format import Segment

log = logging.getLogger(__name__)

MAX_CHARS = 300
"""The most the server voices in one request."""
PAUSE_SECONDS = 0.25
"""Between her segments, and between the parts of a long one."""
_RETRIES = 6
"""How many times a request the server is too busy for is made again."""
_TIMEOUT = httpx.Timeout(90, connect=10)
"""A segment is voiced in some seconds on the home GPU; the first after a restart waits on
the model loading."""

# Each cue word, lower case, and the emoji Irodori reads it as (its Gradio palette).
CUE_EMOJI: dict[str, str] = {
    **dict.fromkeys(("happily", "happy", "cheerfully", "cheerful", "smiling", "brightly",
                     "warmly", "delighted", "joyfully", "sweetly"), "😊"),
    **dict.fromkeys(("excitedly", "excited", "energetically", "eagerly", "enthusiastically",
                     "thrilled"), "😆"),
    **dict.fromkeys(("shyly", "shy", "embarrassed", "bashfully", "bashful", "blushing",
                     "sheepishly"), "🫣"),
    **dict.fromkeys(("sadly", "sad", "disappointed", "dejected", "lonely", "hesitantly",
                     "timidly", "meekly"), "🥺"),
    **dict.fromkeys(("crying", "sobbing", "tearfully", "tearful", "weeping"), "😭"),
    **dict.fromkeys(("sulking", "sulkily", "pouting", "angrily", "angry", "annoyed",
                     "grumpily", "irritated", "huffily", "indignantly"), "😠"),
    **dict.fromkeys(("worried", "worriedly", "anxiously", "anxious", "uneasily", "concerned"),
                    "😟"),
    **dict.fromkeys(("surprised", "startled", "amazed", "astonished", "impressed"), "😲"),
    **dict.fromkeys(("gasping", "gasp", "gasps"), "😮"),
    **dict.fromkeys(("gently", "softly", "tenderly", "kindly", "soothingly", "affectionately"),
                    "🫶"),
    **dict.fromkeys(("teasing", "teasingly", "playfully", "mischievously", "slyly", "coyly"),
                    "😏"),
    **dict.fromkeys(("whispering", "whispers", "whisper", "quietly", "murmuring"), "👂"),
    **dict.fromkeys(("laughing", "laughs", "giggling", "giggles", "chuckling", "chuckles"),
                    "🤭"),
    **dict.fromkeys(("sleepy", "sleepily", "drowsily", "drowsy", "tired", "wearily"), "😪"),
    **dict.fromkeys(("yawning", "yawns"), "🥱"),
    **dict.fromkeys(("nervously", "nervous", "flustered", "panicked", "panicking",
                     "stammering", "stuttering", "frantically"), "😰"),
    **dict.fromkeys(("sighing", "sighs", "sigh"), "😮‍💨"),
    **dict.fromkeys(("proudly", "proud", "smugly", "smug", "confidently", "confident",
                     "triumphantly", "boastfully"), "😎"),
    **dict.fromkeys(("pleading", "begging", "pleadingly", "imploring"), "🙏"),
    **dict.fromkeys(("relieved", "contentedly", "content", "satisfied", "calmly"), "😌"),
    **dict.fromkeys(("exasperated", "exasperatedly", "dryly", "unimpressed"), "🙄"),
    **dict.fromkeys(("curiously", "curious", "puzzled", "questioningly", "wondering",
                     "thoughtfully", "confused"), "🤔"),
    **dict.fromkeys(("quickly", "hurriedly", "rapidly", "fast"), "⏩"),
    **dict.fromkeys(("slowly", "slow"), "🐢"),
    **dict.fromkeys(("firmly", "forcefully", "determined", "emphatically", "resolutely",
                     "strongly"), "💪"),
    **dict.fromkeys(("shouting", "yelling", "loudly", "energetic"), "💥"),
    **dict.fromkeys(("screaming", "shrieking"), "😱"),
    **dict.fromkeys(("humming", "singing"), "🎵"),
    **dict.fromkeys(("pause", "pausing", "silence"), "⏸️"),
}
TAG_EMOJI = {"whisper": "👂", "soft": "🫶", "fast": "⏩", "slow": "🐢", "emphasis": "💪",
             "stress": "💪", "forceful": "💥"}
"""Drama 3's paired tags, which the replies may hold, as Irodori's emoji at their opening."""
MOST_EMOJI = 2
"""Of one cue, `[laughing nervously]`: Irodori is given its first two."""

_CUE = re.compile(r"\[([A-Za-z][A-Za-z ,'\-]*)\]\s*")
_TAG = re.compile(r"<(/?)([a-z]+)>")
_SENTENCE_END = re.compile(r"(?<=[。！？!?…♪～])")
_SPACES = re.compile(r"[ \t]{2,}")


def _cue_emoji(cue: str) -> str:
    found: list[str] = []
    for word in re.split(r"[ ,]+", cue.lower()):
        emoji = CUE_EMOJI.get(word.strip("'-"))
        if emoji is not None and emoji not in found:
            found.append(emoji)
    return "".join(found[:MOST_EMOJI])


def irodori_text(ja: str, readings: Sequence[Reading] = ()) -> str:
    """What Irodori is told to say of her Japanese `ja`: its delivery cues as emoji, the
    names as their readings in kana, what people see otherwise."""
    text = voiced(ja)
    text = _CUE.sub(lambda m: _cue_emoji(m[1]), text)
    text = _TAG.sub(lambda m: "" if m[1] else TAG_EMOJI.get(m[2], ""), text)
    for reading in sorted(readings, key=lambda r: len(r.written), reverse=True):
        text = text.replace(reading.written, reading.kana.replace(" ", ""))
    return _SPACES.sub(" ", text).strip()


def parts(text: str) -> list[str]:
    """`text` in parts of at most `MAX_CHARS`, split at its sentences where it must be."""
    if len(text) <= MAX_CHARS:
        return [text] if text else []
    out: list[str] = []
    current = ""
    for sentence in (s for s in _SENTENCE_END.split(text) if s):
        while len(sentence) > MAX_CHARS:  # one sentence too long: cut where it must be
            if current:
                out.append(current)
                current = ""
            out.append(sentence[:MAX_CHARS])
            sentence = sentence[MAX_CHARS:]
        if len(current) + len(sentence) > MAX_CHARS:
            out.append(current)
            current = ""
        current += sentence
    if current:
        out.append(current)
    return [p.strip() for p in out if p.strip()]


class _NotVoiced(Exception):
    """The server answered with no audio, or could not be reached; says how."""


class IrodoriReadAloud:
    """Has her words read aloud in her voice on the deployer's Irodori-TTS server `settings`
    describe, recorded in `activity`; on `transport` instead, in tests."""

    def __init__(
        self,
        settings: IrodoriSettings,
        activity: ActivityLog,
        readings: Sequence[Reading] = (),
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._activity = activity
        self._readings = tuple(readings)
        self._transport = transport
        self._one_at_a_time = asyncio.Lock()
        """The server voices one request at a time: this backend's wait here, not on its 429s."""

    async def voice(self, voice: str, segments: Sequence[Segment]) -> bytes:
        """Her `segments` said in her voice `voice`, as one WAV. Raises ReadAloudFailed if
        there is nothing to say or the server fails."""
        texts = [p for s in segments for p in parts(irodori_text(s.ja, self._readings))]
        if not texts:
            raise ReadAloudFailed()
        origin = Origin("tts", host(self._settings.base_url), self._settings.model)
        clips: list[bytes] = []
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT, trust_env=False
            ) as client:
                for text in texts:
                    clips.append(
                        await timed(self._activity, origin, self._request(client, voice, text))
                    )
            return joined(clips, PAUSE_SECONDS)
        except (_NotVoiced, wave.Error, EOFError) as e:
            log.warning("reading aloud on Irodori failed: %s", e)
            raise ReadAloudFailed() from None

    async def _request(self, client: httpx.AsyncClient, voice: str, text: str) -> bytes:
        body = {"model": self._settings.model, "voice": voice, "input": text,
                "response_format": "wav"}
        headers = {"Authorization": f"Bearer {self._settings.api_key}"}
        for attempt in range(_RETRIES + 1):
            try:
                async with self._one_at_a_time:
                    response = await client.post(
                        f"{self._settings.base_url}/audio/speech", headers=headers, json=body
                    )
            except httpx.HTTPError as e:
                raise _NotVoiced(f"连不上 Irodori：{e!r}") from e
            if response.status_code in (429, 503) and attempt < _RETRIES:
                await asyncio.sleep(_retry_after(response))
                continue
            if response.is_error:
                raise _NotVoiced(f"Irodori 返回 {response.status_code}：{response.text[:200]}")
            if not response.content:
                raise _NotVoiced("Irodori 没有返回音频")
            return response.content
        raise AssertionError("unreachable")


def _retry_after(response: httpx.Response) -> float:
    try:
        return min(10.0, max(0.5, float(response.headers.get("Retry-After", "2"))))
    except ValueError:
        return 2.0


def joined(clips: Sequence[bytes], pause: float) -> bytes:
    """The WAV `clips`, all of one format, one after another with `pause` seconds of
    silence between, as one WAV."""
    out = io.BytesIO()
    writer: wave.Wave_write | None = None
    for i, clip in enumerate(clips):
        with wave.open(io.BytesIO(clip), "rb") as reader:
            if writer is None:
                writer = wave.open(out, "wb")
                writer.setparams(reader.getparams())
            elif i:
                frames = int(writer.getframerate() * pause)
                writer.writeframes(b"\0" * frames * writer.getsampwidth() * writer.getnchannels())
            writer.writeframes(reader.readframes(reader.getnframes()))
    if writer is None:
        raise wave.Error("no audio")
    writer.close()
    return out.getvalue()
