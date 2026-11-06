"""The deployer's image service (GLOSSARY.md「生图」) as it is configured: in NovelAI's own
format or OpenAI's image format, at whatever address, with its key and model, so many
photos at a time, in the deployment's art style. `.env` sets it; the admin console's
「生图」 card overrides it, a change tried before it is kept by generating one picture
with a fixed prompt in the art style, which is neither billed nor recorded.

Driven through the backend's external API, the judge model faked and the image service
faked at its transport, where every request it is sent is seen."""

import asyncio
import io
from dataclasses import replace

import httpx
import pytest
from PIL import Image

from eidolon.config import ImageSettings, Settings
from tests.conftest import ClientFactory
from tests.fakes import (
    FakeIdentityProvider,
    FakeImageService,
    FakeLLM,
    FakeLLMService,
    FakeServiceClients,
    OpenAIAnswer,
)
from tests.test_live_config import CONFIG, admin_client, recorded
from tests.test_own_llm import LLM
from tests.test_photo_failures import tagged
from tests.test_photos import (  # noqa: F401  (`settings`, with the deployer's image generation)
    IMAGE,
    REPLY,
    asking,
    photo_events,
    settings,
    settled,
)
from tests.test_text_turn import send_turn, start_conversation

ASKED = "发张自拍给我看看"
IMAGE_CARD = "/api/admin/config/image"
RELAY_KEY = "relay-key-1234"
CARD = {
    "api_format": "openai",
    "base_url": "https://relay.image.test/v1",
    "model": "nai-diffusion-4-5-full",
    "concurrency": 2,
    "style": "0.7::artist:example::",
    "api_key": RELAY_KEY,
}
OPENAI = ImageSettings(
    "relay-key", "https://relay.image.test/v1", "nai-diffusion-4-5-full", api_format="openai"
)
COMPATIBLE = replace(OPENAI, model="gpt-image-1.5", api_format="openai-compatible")


@pytest.mark.parametrize("answer", ["b64_json", "data_url", "url"])
async def test_in_openais_image_format_the_picture_is_asked_for_at_the_top_level(
    make_client: ClientFactory, settings: Settings, answer: OpenAIAnswer
):
    image = FakeImageService()
    image.openai_answer = answer
    client = make_client(
        FakeLLM(REPLY), clients=asking(), settings=replace(settings, image=OPENAI),
        image_transport=image.transport(),
    )
    conversation = await start_conversation(client)

    [photo] = photo_events(await send_turn(client, conversation, ASKED))
    came_out = await settled(client, photo["id"])
    picture = await client.get(f"/api/photos/{photo['id']}/image")

    assert came_out == {"status": "ready", "reason": None}, answer
    assert picture.headers["content-type"] == "image/webp"
    [request] = image.requests
    assert request["url"] == "https://relay.image.test/v1/images/generations"
    assert request["key"] == "relay-key"
    body = request["body"]
    assert body["prompt"].startswith("1girl, solo, sakuragi mano, idolmaster shiny colors")
    assert body["negative_prompt"].startswith("nsfw, lowres")
    assert {k: v for k, v in body.items() if k not in ("prompt", "negative_prompt")} == {
        "model": "nai-diffusion-4-5-full", "size": "832x1216", "n": 1,
        "response_format": "b64_json",
    }
    assert image.downloads == ([FakeImageService.DOWNLOAD] if answer == "url" else [])


@pytest.mark.parametrize("answer", ["b64_json", "data_url", "url"])
async def test_openai_compatible_photos_use_standard_parameters_and_fit_the_answer(
    make_client: ClientFactory, settings: Settings, answer: OpenAIAnswer
):
    image = FakeImageService()
    image.openai_answer = answer
    image.size = (1024, 1024)  # Relays may answer at a different size.
    client = make_client(
        FakeLLM(REPLY), clients=asking(), settings=replace(settings, image=COMPATIBLE),
        image_transport=image.transport(),
    )
    conversation = await start_conversation(client)

    [photo] = photo_events(await send_turn(client, conversation, ASKED))

    assert await settled(client, photo["id"]) == {"status": "ready", "reason": None}
    picture = await client.get(f"/api/photos/{photo['id']}/image")
    with Image.open(io.BytesIO(picture.content)) as webp:
        assert (webp.format, webp.size) == ("WEBP", (832, 1216))
    assert FakeImageService.METADATA.encode() not in picture.content
    [request] = image.requests
    assert request["url"] == "https://relay.image.test/v1/images/generations"
    assert request["key"] == COMPATIBLE.api_key
    body = request["body"]
    assert {k: v for k, v in body.items() if k != "prompt"} == {
        "model": "gpt-image-1.5", "size": "1024x1536", "n": 1,
    }
    assert "sakuragi mano, idolmaster shiny colors" in body["prompt"]
    assert "masterpiece" not in body["prompt"]
    assert "nsfw" not in body["prompt"]
    assert image.downloads == ([FakeImageService.DOWNLOAD] if answer == "url" else [])


@pytest.mark.parametrize("service", [OPENAI, COMPATIBLE])
async def test_in_openais_image_format_a_chat_shaped_answer_is_not_a_picture(
    make_client: ClientFactory, settings: Settings, service: ImageSettings
):
    image = FakeImageService()
    image.openai_answer = "chat"
    client = make_client(
        FakeLLM(REPLY), clients=asking(), settings=replace(settings, image=service),
        image_transport=image.transport(),
    )
    conversation = await start_conversation(client)

    [photo] = photo_events(await send_turn(client, conversation, ASKED))

    assert await settled(client, photo["id"]) == {"status": "failed", "reason": "bad_image"}


async def test_the_art_style_goes_as_written_after_the_works_tag_before_her_looks(
    make_client: ClientFactory, settings: Settings
):
    image = FakeImageService()
    styled = replace(IMAGE, style=" 0.7::artist:example::, {artist:another example} ")
    client = make_client(
        FakeLLM(REPLY), clients=asking(), settings=replace(settings, image=styled),
        image_transport=image.transport(),
    )
    conversation = await start_conversation(client)

    [photo] = photo_events(await send_turn(client, conversation, ASKED))
    await settled(client, photo["id"])

    [request] = image.requests
    assert request["body"]["input"].startswith(
        "1girl, solo, sakuragi mano, idolmaster shiny colors,"
        " 0.7::artist:example::, {artist:another example}, brown hair, medium hair, brown eyes,"
    )


@pytest.mark.parametrize("api_format", ["openai", "openai-compatible"])
def test_env_sets_the_format_how_many_at_a_time_and_the_art_style(
    monkeypatch: pytest.MonkeyPatch, api_format,
):
    monkeypatch.setenv("NOVELAI_API_KEY", "pst-key")
    for name in ("NOVELAI_API_FORMAT", "NOVELAI_CONCURRENCY", "NOVELAI_STYLE"):
        monkeypatch.delenv(name, raising=False)
    by_default = ImageSettings.from_env()
    monkeypatch.setenv("NOVELAI_API_FORMAT", api_format)
    monkeypatch.setenv("NOVELAI_CONCURRENCY", "3")
    monkeypatch.setenv("NOVELAI_STYLE", " 0.7::artist:example:: ")
    set_so = ImageSettings.from_env()

    assert by_default is not None
    assert (by_default.api_format, by_default.concurrency, by_default.style) == ("novelai", 1, "")
    assert set_so == ImageSettings(
        "pst-key", api_format=api_format, concurrency=3, style="0.7::artist:example::"
    )


@pytest.mark.parametrize(
    ("name", "value", "says"),
    [("NOVELAI_API_FORMAT", "chat", "NOVELAI_API_FORMAT"),
     ("NOVELAI_CONCURRENCY", "11", "1 到 10 之间的整数")],
)
def test_env_refuses_a_format_not_known_or_too_many_at_a_time(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, says: str
):
    monkeypatch.setenv("NOVELAI_API_KEY", "pst-key")
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=says):
        ImageSettings.from_env()


async def test_shared_photos_are_serial_even_with_higher_image_concurrency(
    make_client: ClientFactory, settings: Settings, own_llm: FakeLLMService
):
    image = FakeImageService()
    image.gate = asyncio.Event()
    outfits = ["red dress", "school uniform", "hoodie"]
    own_llm.llm = FakeLLM(*(tagged(o) for o in outfits))
    client = make_client(
        FakeLLM(), clients=asking(),
        settings=replace(settings, image=replace(IMAGE, concurrency=2)),
        image_transport=image.transport(),
    )
    conversation = await start_conversation(client)

    photos = [
        photo_events(await send_turn(client, conversation, ASKED, own_llm=LLM))[0]
        for _ in outfits
    ]
    await asyncio.sleep(0.05)
    at_once = len(image.requests)
    image.gate.set()
    came_out = [await settled(client, p["id"]) for p in photos]

    assert at_once == 1
    assert came_out == [{"status": "ready", "reason": None}] * 3


@pytest.fixture
def admins(settings: Settings) -> Settings:
    """With the admin, and no image generation in `.env`."""
    return replace(settings, admins=frozenset({("github", "1001")}), image=None)


async def image_admin(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider,
    image: FakeImageService, clients: FakeServiceClients | None = None,
) -> httpx.AsyncClient:
    """A client signed in as the admin, the image service `image`."""
    def factory(*args, **kwargs) -> httpx.AsyncClient:
        return make_client(*args, image_transport=image.transport(), **kwargs)

    return await admin_client(factory, settings, github, clients or asking())


async def test_an_image_card_saved_is_tried_on_one_picture_then_photos_are_on_it_until_restored(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    image = FakeImageService()
    clients = asking()
    clients.llm = FakeLLM(REPLY, REPLY)
    client = await image_admin(make_client, admins, github, image, clients)
    conversation = await start_conversation(client)
    before = (await client.get(CONFIG)).json()["image"]

    saved = await client.put(IMAGE_CARD, json=CARD)
    assert saved.status_code == 200, saved.text
    tried = list(image.requests)
    recorded_by_the_try = recorded(client, "image")
    [photo] = photo_events(await send_turn(client, conversation, ASKED))
    await settled(client, photo["id"])
    restored = await client.delete(IMAGE_CARD)
    assert restored.status_code == 200, restored.text
    after = await send_turn(client, conversation, ASKED)

    assert before["status"] == "env"
    assert before["effective"] == {
        "api_format": "novelai", "base_url": "https://image.novelai.net",
        "api_key_last4": None, "model": "nai-diffusion-5-curated", "concurrency": 1,
        "style": "",
    }
    shown = saved.json()["image"]
    assert shown["status"] == "overridden"
    assert shown["effective"] == {k: v for k, v in CARD.items() if k != "api_key"} | {
        "api_key_last4": "1234",
    }
    assert RELAY_KEY not in saved.text
    [check] = tried
    assert check["url"] == "https://relay.image.test/v1/images/generations"
    assert check["key"] == RELAY_KEY
    assert check["body"]["size"] == "832x1216"
    assert check["body"]["model"] == "nai-diffusion-4-5-full"
    assert check["body"]["prompt"].startswith("1girl, solo, 0.7::artist:example::, ")
    assert check["body"]["negative_prompt"].startswith("nsfw, ")
    assert recorded_by_the_try == []
    [_, turns] = image.requests
    assert turns["key"] == RELAY_KEY
    assert "0.7::artist:example::" in turns["body"]["prompt"]
    assert recorded(client, "image") == [("relay.image.test", "nai-diffusion-4-5-full", False)]
    assert restored.json()["image"] == before
    assert photo_events(after) == []


async def test_openai_compatible_card_is_tried_saved_and_used_for_the_next_photo(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    image = FakeImageService()
    clients = asking()
    clients.llm = FakeLLM(REPLY)
    client = await image_admin(make_client, admins, github, image, clients)
    card = CARD | {"api_format": "openai-compatible", "model": "gpt-image-1.5"}

    saved = await client.put(IMAGE_CARD, json=card)

    assert saved.status_code == 200, saved.text
    assert saved.json()["image"]["effective"]["api_format"] == "openai-compatible"
    assert RELAY_KEY not in saved.text
    assert (await client.get(CONFIG)).json()["image"] == saved.json()["image"]
    assert recorded(client, "image") == []
    conversation = await start_conversation(client)
    [photo] = photo_events(await send_turn(client, conversation, ASKED))
    assert (await settled(client, photo["id"]))["status"] == "ready"
    assert len(image.requests) == 2
    for request in image.requests:
        assert request["body"].keys() == {"model", "prompt", "size", "n"}
        assert request["body"]["model"] == "gpt-image-1.5"
        assert request["body"]["size"] == "1024x1536"
        assert "artist" not in request["body"]["prompt"]
        assert "Described in tags:" in request["body"]["prompt"]
    assert recorded(client, "image") == [("relay.image.test", "gpt-image-1.5", False)]


@pytest.mark.parametrize("api_format", ["openai", "openai-compatible"])
async def test_openai_error_during_try_leaves_the_image_card_unsaved(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider, api_format
):
    image = FakeImageService()
    image.status = 400
    image.error = "unsupported image parameter"
    client = await image_admin(make_client, admins, github, image)

    refused = await client.put(IMAGE_CARD, json=CARD | {"api_format": api_format})

    assert refused.status_code == 422
    assert "生图服务返回 400" in refused.json()["detail"]
    assert (await client.get(CONFIG)).json()["image"]["status"] == "env"


@pytest.mark.parametrize("wrong", ["key", "size"])
async def test_an_image_card_whose_try_fails_is_not_saved_saying_why(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider, wrong: str
):
    image = FakeImageService()
    if wrong == "key":
        image.status = 401
    else:
        image.size = (1024, 1024)
    client = await image_admin(make_client, admins, github, image)

    refused = await client.put(IMAGE_CARD, json=CARD)

    assert refused.status_code == 422, wrong
    detail = refused.json()["detail"]
    assert detail.startswith("试调失败，没有保存："), wrong
    assert ("401" if wrong == "key" else "1024×1024，不是 832×1216") in detail, wrong
    assert (await client.get(CONFIG)).json()["image"]["status"] == "env", wrong


async def test_an_image_card_saved_again_as_it_is_is_not_tried_again(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    image = FakeImageService()
    client = await image_admin(make_client, admins, github, image)
    assert (await client.put(IMAGE_CARD, json=CARD)).status_code == 200

    again = await client.put(IMAGE_CARD, json={k: v for k, v in CARD.items() if k != "api_key"})

    assert again.status_code == 200, again.text
    assert len(image.requests) == 1


REFUSED_MODEL = (
    '{"error":{"code":"model_not_found","message":'
    '"Model \\"gpt-image-2.5\\" is not available for this group"}}'
)
REFUSED_NEGATIVE = '{"error":{"message":"unsupported image parameter: negative_prompt"}}'


@pytest.mark.parametrize(
    ("status", "error", "advice"),
    [(404, REFUSED_MODEL, "分组没开通"), (400, REFUSED_NEGATIVE, "OpenAI 图像生成兼容")],
)
async def test_a_refusal_of_the_model_or_negative_prompt_says_what_to_do_keeping_its_words(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider,
    status: int, error: str, advice: str,
):
    image = FakeImageService()
    image.status, image.error = status, error
    client = await image_admin(make_client, admins, github, image)

    refused = await client.put(IMAGE_CARD, json=CARD | {"api_format": "openai"})

    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert advice in detail
    assert f"生图服务返回 {status}" in detail


async def test_an_image_card_whose_try_fails_can_be_kept_untried_on_the_admins_say(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    image = FakeImageService()
    image.status = 404
    client = await image_admin(make_client, admins, github, image)
    tried = len(image.requests)

    kept = await client.put(f"{IMAGE_CARD}?untried=true", json=CARD)

    assert kept.status_code == 200
    assert kept.json()["image"]["status"] == "overridden"
    assert len(image.requests) == tried


async def test_an_image_card_without_a_key_is_not_kept_even_untried(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    client = await image_admin(make_client, admins, github, FakeImageService())

    refused = await client.put(f"{IMAGE_CARD}?untried=true", json=CARD | {"api_key": None})

    assert refused.status_code == 422
    assert "还没有生图的 key" in refused.json()["detail"]


async def test_only_image_cards_can_be_kept_untried(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    client = await image_admin(make_client, admins, github, FakeImageService())
    judge_free = (await client.get(CONFIG)).json()["chat_llm"]["effective"]
    change = {f: judge_free[f] for f in ("protocol", "base_url", "model")}

    refused = await client.put("/api/admin/config/chat_llm?untried=true", json=change)

    assert refused.status_code == 422


async def test_the_image_card_lists_the_models_the_relay_offers_its_key(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    image = FakeImageService()
    client = await image_admin(make_client, admins, github, image)
    at = {
        "protocol": "chat-completions", "base_url": "https://relay.test/v1",
        "api_key": "sk-relay-key",
    }

    listed = await client.post(f"{IMAGE_CARD}/models", json=at)
    elsewhere = await client.post(f"{IMAGE_CARD}/models", json=at | {"api_key": None})

    assert listed.json() == {"models": ["gpt-image-2", "chat-model"]}
    assert image.listed_with == [("https://relay.test/v1/models", "sk-relay-key")]
    assert elsewhere.status_code == 422
    assert "API key" in elsewhere.json()["detail"]
