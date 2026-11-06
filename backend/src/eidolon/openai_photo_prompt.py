"""The prompt a photo or a moment's picture is sent with in the `openai-compatible` image
format (`image_generation`): written out of the NovelAI prompts it would otherwise be
generated from (`photo_prompt.ImagePrompt`), for a model that reads sentences, as GPT Image
does, not NovelAI's tags.

What only NovelAI reads is left out: its quality tags, `1girl`/`solo` and the count of
girls (said in words instead), weights and their `::`, and artists (`artist:…`), which
GPT Image may refuse to imitate. How much of her a picture shows is said in words. The rest
of the tags go as they are, her character tag and her looks among them. The negative prompt
is not sent: its list of what must not show, nudity among it, is what moderation stops on.
A short fixed line asks for all ages, no text and sound hands instead; one taken of her
unawares says she does not look at the camera, one no one is in that no one is in it.
"""

import re

from eidolon.photo_prompt import (
    LOOKING_AT_VIEWER,
    NO_HUMANS,
    QUALITY_TAGS,
    ImagePrompt,
)

_WEIGHT = re.compile(r"-?\d+(\.\d+)?::|::")
_COUNT = re.compile(r"^(\d+)girls$")
_LEFT_OUT = frozenset({*QUALITY_TAGS, "1girl", "solo", NO_HUMANS})
_IN_WORDS = {
    "portrait": "close-up portrait",
    "upper body": "upper-body shot",
    "cowboy shot": "shot from the thighs up",
    "full body": "full-body shot",
    "side-by-side": "standing side by side",
    "group picture": "group photo",
}
OPENING = "An all-ages anime illustration in the style of a photo taken on a phone."
KEPT_SAFE = (
    "Keep it all-ages: everyone fully clothed, nothing suggestive. No text, captions, "
    "watermarks or logos. Natural anatomy and hands."
)


def openai_photo_prompt(prompt: ImagePrompt) -> str:
    """The sentences `prompt` is sent as, to a model that reads them."""
    written = [t.strip() for t in _WEIGHT.sub("", prompt.positive).split(",")]
    tags: list[str] = []
    count = 0
    for tag in written:
        if counted := _COUNT.match(tag):
            count = int(counted[1])
            continue
        if not tag or tag in _LEFT_OUT or tag.startswith("artist:"):
            continue
        tag = _IN_WORDS.get(tag, tag)
        if tag not in tags:
            tags.append(tag)
    lines = [OPENING]
    if NO_HUMANS in written:
        lines.append("No people anywhere in the picture.")
    elif count and prompt.characters:
        lines.append(f"{count} girls together, each drawn distinctly:")
        for number, each in enumerate(prompt.characters, 1):
            lines.append(f"Girl {number}: {each.removeprefix('girl, ')}")
    elif "1girl" in written:
        lines.append("One girl, alone in the picture.")
    lines.append(f"Described in tags: {', '.join(tags)}.")
    if LOOKING_AT_VIEWER in prompt.negative and LOOKING_AT_VIEWER not in written:
        lines.append("She is not looking at the camera.")
    lines.append(KEPT_SAFE)
    return "\n".join(lines)
