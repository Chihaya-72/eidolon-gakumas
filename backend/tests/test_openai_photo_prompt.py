"""The sentences a photo is sent as in the `openai-compatible` image format."""

from eidolon.openai_photo_prompt import KEPT_SAFE, openai_photo_prompt
from eidolon.photo_prompt import (
    CANDID_NEGATIVE,
    NEGATIVE_PROMPT,
    NO_HUMANS_NEGATIVE,
    ImagePrompt,
    check_prompt,
)


def test_a_photo_leaves_out_what_only_novelai_reads_and_says_her_framing_in_words():
    prompt = check_prompt("0.7::artist:someone::, 1.2::watercolor::, flat color")

    text = openai_photo_prompt(prompt)

    assert "One girl, alone in the picture." in text
    assert "Described in tags: watercolor, flat color, upper-body shot, indoors, smile, looking at viewer." in text
    for novelai in ("::", "artist", "1girl", "solo", "masterpiece", "rating:general", "very aesthetic"):
        assert novelai not in text
    assert text.endswith(KEPT_SAFE)


def test_the_negative_prompt_is_not_sent_but_a_candid_photo_says_where_she_looks():
    candid = ImagePrompt("1girl, solo, sakuragi mano, cafe, depth of field", CANDID_NEGATIVE)
    posed = ImagePrompt("1girl, solo, sakuragi mano, cafe, looking at viewer", NEGATIVE_PROMPT)

    for text in (openai_photo_prompt(candid), openai_photo_prompt(posed)):
        assert "nsfw" not in text and "nipples" not in text and "lowres" not in text
    assert "She is not looking at the camera." in openai_photo_prompt(candid)
    assert "not looking" not in openai_photo_prompt(posed)


def test_a_picture_no_one_is_in_says_so():
    prompt = ImagePrompt("no humans, scenery, japan, outdoors, street, masterpiece", NO_HUMANS_NEGATIVE)

    text = openai_photo_prompt(prompt)

    assert "No people anywhere in the picture." in text
    assert "Described in tags: scenery, japan, outdoors, street." in text


def test_a_group_photo_draws_each_girl_in_a_line_of_her_own():
    prompt = ImagePrompt(
        "2girls, idolmaster shiny colors, side-by-side, cowboy shot, park, looking at viewer",
        NEGATIVE_PROMPT,
        characters=("girl, sakuragi mano, pink hair", "girl, kazano hiori, black hair"),
    )

    text = openai_photo_prompt(prompt)

    assert "2 girls together, each drawn distinctly:" in text
    assert "Girl 1: sakuragi mano, pink hair" in text
    assert "Girl 2: kazano hiori, black hair" in text
    assert "standing side by side, shot from the thighs up" in text
    assert "2girls" not in text
