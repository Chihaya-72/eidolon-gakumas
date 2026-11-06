"""The active pack can start with all 24 roles, including unpublished profile fields.

Can also run without the application's integration fixtures:
PYTHONPATH=src pytest --confcutdir=tests/gakumas tests/gakumas
"""

import re
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from eidolon.bar_lines import check_bar_lines, load_bar_lines
from eidolon.bar_visits import check_bar_visits, load_bar_visits
from eidolon.characters import CharacterConfigError, load_characters
from eidolon.drink_catalog import check_bar_tastes, load_drink_catalog
from eidolon.gift_catalog import check_liked_gifts, load_gift_catalog
from eidolon.job_list import WORK, load_job_list
from eidolon.place_pool import check_job_places, check_place_likes, load_place_pool
from eidolon.producer import Birthday, ProducerProfile, is_birthday, producer_prompt
from eidolon.schedule import FIRST_WEEK, draw_week, idols_of
from eidolon.today import always_known
from eidolon.world import World, WorldError, load_world

PACK = Path(__file__).resolve().parents[3] / "characters/gakumas"
EXPECTED_NAMES = set(
    "花海咲季 月村手毬 藤田琴音 有村麻央 葛城莉莉娅 仓本千奈 紫云清夏 篠泽广 姬崎莉波 "
    "花海佑芽 十王星南 秦谷美铃 雨夜燕 贺阳燐羽 白草四音 白草月花 蓝井抚子 根绪亚纱里 "
    "冰渡香名江 十王邦夫 十王龙正 贺阳继 姬崎汐莉 黑井崇男".split()
)


def test_all_24_roles_have_complete_matching_sheets_and_facts():
    characters = load_characters(PACK / "characters.toml")
    assert len(characters) == 24
    assert {c.name for c in characters.values()} == EXPECTED_NAMES
    for c in characters.values():
        assert c.sheet.startswith(f"# 人设：{c.name}\n")
        assert "## 硬性规则" in c.sheet
        assert len(c.facts) == 7
        assert c.voice_id == ""  # No unrelated SC voice is silently reused.


def test_all_startup_catalogs_accept_the_new_roster():
    characters = load_characters(PACK / "characters.toml")
    check_liked_gifts(characters, load_gift_catalog(PACK / "gifts.toml"))
    drinks = load_drink_catalog(PACK / "drinks.toml")
    check_bar_tastes(characters, drinks)
    check_bar_visits(characters, load_bar_visits(PACK / "bar_visits.toml"))
    check_bar_lines(load_bar_lines(PACK / "bar_lines.toml"), drinks)
    check_job_places(load_job_list(PACK / "jobs.toml"))
    check_place_likes(characters)
    assert load_place_pool(PACK / "places.toml", characters)


def test_non_idols_are_kept_distinct_and_setting_survives_roundtrip():
    characters = load_characters(PACK / "characters.toml")
    world = load_world(PACK / "world.json")
    assert world is not None
    world.check_characters(characters, PACK / "world.json")
    assert World.from_json(world.to_json()) == world
    for id in ["asari", "kanae", "kunio", "ryusho", "tsugu", "shiri", "kuroi"]:
        assert world.is_staff(characters[id].name)
        assert not characters[id].cycles_enabled
    for c in characters.values():
        prompt = world.prompt(c.name, date(2026, 11, 4))
        assert "用户与当前角色的具体关系以该角色的人设为准" in prompt
        assert "你所在的283" not in prompt


def test_unknown_birthday_never_creates_an_event_or_a_fabricated_date():
    child = load_characters(PACK / "characters.toml")["shiri"]
    assert child.age is None
    assert child.birthday is None
    assert not is_birthday(child.birthday, date(2026, 1, 1))
    assert "原作没有公开你的生日" in "\n".join(always_known(child, None))
    saki = load_characters(PACK / "characters.toml")["saki"]
    assert saki.birthday == Birthday(4, 2)
    assert is_birthday(saki.birthday, date(2026, 4, 2))


def test_calendar_birthdays_match_the_dates_explicitly_given_in_each_sheet():
    for c in load_characters(PACK / "characters.toml").values():
        dates = {
            Birthday(int(month), int(day))
            for month, day in re.findall(r"生日\s*[：:]?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", c.sheet)
        }
        assert dates == ({c.birthday} if c.birthday else set()), c.name


def test_seventeen_idols_get_valid_schedules_for_ten_years_and_each_has_a_week_per_round():
    characters = load_characters(PACK / "characters.toml")
    idols = idols_of(characters, load_world(PACK / "world.json"))
    jobs = load_job_list(PACK / "jobs.toml")
    assert len(idols) == 17
    for start in range(0, 520, 4):
        appearances: Counter[str] = Counter()
        for offset in range(4):
            week = FIRST_WEEK + timedelta(weeks=start + offset)
            drawn = draw_week(week, idols, jobs)
            by_idol: dict[str, list] = {}
            for idol, job in drawn:
                by_idol.setdefault(idol, []).append(job)
            assert len(by_idol) in (4, 5), week
            appearances.update(by_idol.keys())
            assert all(2 <= len(given) <= 3 for given in by_idol.values()), week
            assert all(any(j.category in WORK for j in given) for given in by_idol.values()), week
            assert all(sum(j.category == "private" for j in given) <= 1 for given in by_idol.values()), week
            assert len({j.id for _, j in drawn}) == len(drawn), week
            least, most = (13, 16) if len(by_idol) == 4 else (17, 20)
            assert least <= sum(j.length for _, j in drawn) <= most, week
        assert appearances == Counter(idols)


@pytest.mark.parametrize("field,value", [("birthday", '"02-30"'), ("age", "0"), ("cycles_enabled", '"false"')])
def test_unknown_support_does_not_accept_invalid_profile_values(tmp_path, field, value):
    config = (PACK / "characters.toml").read_text(encoding="utf-8")
    first = config.split("[[characters]]")[1]
    lines = [f"{field} = {value}" if line.startswith(f"{field} =") else line for line in first.splitlines()]
    lines = [line.replace('"sheets/saki.md"', f'"{PACK}/sheets/saki.md"') for line in lines]
    path = tmp_path / "characters.toml"
    path.write_text("[[characters]]\n" + "\n".join(lines), encoding="utf-8")
    with pytest.raises(CharacterConfigError, match=field):
        load_characters(path)


@pytest.mark.parametrize("bad_setting", ["", [], 42])
def test_world_setting_must_be_nonempty_text(tmp_path, bad_setting):
    import json

    data = json.loads((PACK / "world.json").read_text(encoding="utf-8"))
    data["setting"] = bad_setting
    path = tmp_path / "world.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(WorldError, match="setting"):
        load_world(path)


def test_producer_prompt_defers_to_each_roles_actual_relationship():
    prompt = producer_prompt(ProducerProfile(form_of_address="老师"))
    assert "283" not in prompt
    assert "身份、称呼和关系以你的人设为准" in prompt
    assert "不改变人设中你与对方的关系" in prompt
    assert "仍然是你的制作人" not in prompt


def test_legacy_roster_remains_loadable():
    legacy = load_characters(PACK.parent / "characters.toml")
    assert legacy["mano"].birthday == Birthday(4, 25)
    unknown = replace(legacy["mano"], birthday=None)
    assert "原作没有公开你的生日" in "\n".join(always_known(unknown, None))


def test_avatars_stay_small_and_signatures_are_webp():
    # The size rule test_characters holds the Shiny Colors pack to (characters.toml).
    characters = load_characters(PACK / "characters.toml")
    avatars = [c.avatar for c in characters.values() if c.avatar]
    signatures = [c.signature for c in characters.values() if c.signature]
    assert len(avatars) == 14 and len(signatures) == 13
    assert all(path.suffix == ".jpg" and path.stat().st_size <= 32 * 1024 for path in avatars)
    assert all(path.suffix == ".webp" for path in signatures)


def test_jobs_do_not_mention_the_agency_of_another_game():
    assert "事务所" not in (PACK / "jobs.toml").read_text(encoding="utf-8")
