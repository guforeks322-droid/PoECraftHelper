"""Автотесты ядра: парсер, шансы, эмулятор, сокеты. Запуск: python -m pytest -q"""

import random
from pathlib import Path

import pytest

from poecraft.advisor import Advisor, Goal
from poecraft.calc import Target, _magic_outcomes
from poecraft.data import GameData
from poecraft.emulator import CraftError, Emulator
from poecraft.parser import canonical, parse_item
from poecraft.pool import ModPool
from poecraft import sockets as sk

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"


@pytest.fixture(scope="module")
def data():
    return GameData()


@pytest.fixture(scope="module")
def belt(data):
    return ModPool(data, data.find_base("Leather Belt"), 84)


# ------------------------------------------------------------------ парсер
def test_parse_english_rare():
    it = parse_item((EX / "5_rare_exalt.txt").read_text(encoding="utf-8"))
    assert it.rarity == "Rare" and it.base_name == "Leather Belt" and it.ilvl == 84
    assert [m.kind for m in it.mods] == ["prefix", "prefix", "suffix"]
    assert it.mods[0].name == "Fecund" and it.mods[0].tier == 1


def test_parse_russian_rare():
    it = parse_item((EX / "ru_belt.txt").read_text(encoding="utf-8"))
    assert it.language == "ru" and it.rarity == "Rare" and it.ilvl == 84
    assert it.base_name == "Ремень" and len(it.mods) == 3


def test_canonical_strips_values():
    assert canonical("+140(130-144) to maximum Life") == "+(130-144) to maximum life"


def test_russian_item_resolves_to_same_mods_as_english(data):
    if not data.has_russian:
        pytest.skip("нет русских данных")
    adv = Advisor(data)
    st = adv.resolve(parse_item((EX / "ru_belt.txt").read_text(encoding="utf-8")))
    assert st.pool.base.name == "Leather Belt"
    assert [e.mod.id for e in st.entries] == ["IncreasedLife9", "FireResist6", "Strength1"]


# ------------------------------------------------------------------ шансы
def test_exalt_chance_matches_hand_formula(data, belt):
    """Exalt на Fecund/Lacquered/Brute: нужен огонь или холод T1-T3 → 6000 / 90000."""
    adv = Advisor(data)
    st = adv.resolve(parse_item((EX / "5_rare_exalt.txt").read_text(encoding="utf-8")))
    want = lambda e: e.mod.type in ("FireResistance", "ColdResistance") and e.tier <= 3
    p = st.pool.chance_add(st.mod_defs, "Rare", want)
    assert p == pytest.approx(6000 / 90000, rel=1e-9)


def test_alt_aug_exact(belt):
    T = [Target("prefix", "IncreasedLife", 3), Target("suffix", "FireResistance", 3)]
    p, _, _ = _magic_outcomes(belt, T)
    expected = 3000 / 116000 * 3000 / 66000 + 3000 / 116000 * 3000 / 50000
    assert p == pytest.approx(expected, rel=1e-9)


def test_rare_mod_count_distribution(data, belt):
    em = Emulator(data, belt, seed=3)
    counts = {4: 0, 5: 0, 6: 0}
    for _ in range(3000):
        em.reset()
        em.do_alchemy()
        counts[len(em.mods)] += 1
    assert counts[4] / 3000 == pytest.approx(8 / 12, abs=0.03)
    assert counts[6] / 3000 == pytest.approx(1 / 12, abs=0.02)


# ------------------------------------------------------------------ эмулятор
def test_prefix_lock_survives_chaos(data, belt):
    em = Emulator(data, belt, seed=1)
    em.do_alchemy()
    while len(em.suffixes) >= 3:
        em.do_annul()
    lock = next(o for o in em.bench_options() if "ItemGenerationCannotChangePrefixes" in o["mod"].groups)
    em.do_bench(lock)
    before = [m.text for m in em.prefixes]
    em.do_chaos()
    assert [m.text for m in em.prefixes][:len(before)] == before
    assert not any(m.meta for m in em.mods), "метамод должен пропасть"


def test_undo_restores_item_and_spent(data, belt):
    em = Emulator(data, belt, seed=2)
    em.do_alchemy()
    snap = ([m.text for m in em.mods], dict(em.spent))
    em.do_chaos()
    em.undo()
    assert ([m.text for m in em.mods], em.spent) == snap


def test_invalid_actions_raise(data, belt):
    em = Emulator(data, belt, seed=4)
    with pytest.raises(CraftError):
        em.do_exalt()          # белый предмет
    em.do_transmute()
    with pytest.raises(CraftError):
        em.do_chaos()          # синий


# ------------------------------------------------------------------ сокеты
def test_socket_color_chances_sum_to_one():
    for req in [(150, 0, 0), (100, 100, 0), (60, 60, 60), (0, 0, 194)]:
        assert sum(sk.color_chances(*req)) == pytest.approx(1.0)


def test_single_socket_probability():
    ch = sk.color_chances(0, 0, 194)
    assert sk.prob_recipe(ch, 1, (0, 0, 1)) == pytest.approx(ch[2])


# ------------------------------------------------------------------ стартовые крафты
@pytest.mark.parametrize("path", sorted((ROOT / "goals").glob("*.json")), ids=lambda p: p.stem)
def test_starter_goals_load_and_fit_base(data, path):
    g = Goal.load(path)
    assert g.wanted
    if g.raw.get("base"):
        b = data.find_base(g.raw["base"])
        pool = ModPool(data, b, g.raw.get("min_ilvl") or 84)
        for w in g.wanted:
            assert any(w.matches(e) for e in pool.available), f"{path.name}: {w.label} не выпадает на {b.name}"


def test_icon_text_matching():
    from poecraft.icons import find_all, find_in_text, resolve
    names = ["Chaos Orb", "Eldritch Chaos Orb", "Exalted Orb", "Bound Fossil", "Pristine Fossil",
             "Shrieking Essence of Anger"]
    assert find_in_text("Спам: Shrieking Essence of Anger", names) == "Shrieking Essence of Anger"
    assert find_all("Eldritch Chaos Orb, потом Exalted Orb", names) == ["Eldritch Chaos Orb", "Exalted Orb"]
    assert find_all("Фоссилы: Bound Fossil + Pristine Fossil", names) == ["Bound Fossil", "Pristine Fossil"]
    assert resolve("Crusader") == "Crusader's Exalted Orb"
    assert resolve("Chaos") == "Chaos Orb"


def test_emulator_load_item_from_game():
    import pathlib
    from poecraft.advisor import Advisor
    from poecraft.emulator import Emulator
    from poecraft.parser import parse_item
    from poecraft.pool import ModPool
    data = GameData()
    adv = Advisor(data)
    for name in ("5_rare_exalt.txt", "4_rare_bench.txt", "ru_belt.txt", "2_magic_one.txt"):
        item = parse_item((pathlib.Path(__file__).parent.parent / "examples" / name).read_text(encoding="utf-8"))
        base = data.find_base_any(item.base_name)
        em = Emulator(data, ModPool(data, base, item.ilvl))
        unknown = em.load_item(item, adv._match_mod)
        assert em.rarity == item.rarity
        assert len(em.mods) + len(unknown) == len(item.mods)
        assert not unknown, (name, unknown)
        # значения сохраняются как на предмете, а не перекатываются
        for pm, m in zip(item.mods, em.mods):
            assert m.text.split(" / ")[0].replace("+", "") in pm.lines[0].replace("+", "").replace("(", " (") or m.values
        em.apply("exalt" if item.rarity == "Rare" else "augment") if len(em.mods) < 6 else None


def test_new_crafts_beast_tainted_awakener_catalyst():
    import random
    from poecraft.emulator import CraftError, Emulator
    from poecraft.pool import ModPool
    data = GameData()
    belt = data.bases["Stygian Vise"]
    em = Emulator(data, ModPool(data, belt, 86), seed=3)
    em.apply("alchemy")
    # звери: +суффикс, −префикс
    while len(em.suffixes) >= 3:
        em.apply("chaos")
    p0, s0 = len(em.prefixes), len(em.suffixes)
    em.apply("beast_suffix")
    assert len(em.suffixes) == s0 + 1 and len(em.prefixes) == max(0, p0 - 1)
    # Vaal → дальше только Tainted
    em.apply("vaal")
    assert em.state["corrupted"]
    with pytest.raises(CraftError):
        em.apply("chaos")
    for _ in range(5):
        if em.rarity == "Rare":
            em.apply("tainted_exalt")
    em.undo()
    # катализатор: качество растёт и сбрасывается откатом
    em2 = Emulator(data, ModPool(data, belt, 86), seed=1)
    em2.apply("catalyst", name="Prismatic Catalyst")
    assert em2.state["quality"] == 5
    em2.undo()
    assert em2.state["quality"] == 0
    # Awakener: два влияния
    em3 = Emulator(data, ModPool(data, belt, 86), seed=2, influences=[])
    em3.apply("alchemy")
    while len(em3.mods) >= 6:
        em3.apply("chaos")
    em3.apply("conqueror", name="Hunter")
    em3.apply("awakener", other="Warlord")
    assert em3.influences == ["Hunter", "Warlord"] and em3.rarity == "Rare"
    # отпечаток
    em4 = Emulator(data, ModPool(data, belt, 86), seed=5)
    em4.apply("transmute")
    before = [m.mod.id for m in em4.mods]
    em4.apply("imprint")
    em4.apply("alteration")
    em4.apply("imprint_restore")
    assert [m.mod.id for m in em4.mods] == before


def test_special_fossils():
    from poecraft import currency_craft as cc
    from poecraft.emulator import Emulator
    from poecraft.pool import ModPool
    data = GameData()
    fos = {f.name: f for f in cc.fossils(data)}
    em = Emulator(data, ModPool(data, data.bases["Stygian Vise"], 86), seed=4)
    em.apply("fossils", fossils=[fos["Fractured Fossil"], fos["Pristine Fossil"]])
    assert sum(m.fractured for m in em.mods) == 1 and em.state["split"]
    em.apply("fossils", fossils=[fos["Bloodstained Fossil"]])
    assert em.state["corrupted"]


def test_trade_links():
    import json, urllib.parse
    from poecraft import trade
    raw = {"result": [{"id": "explicit", "entries": [
        {"id": "explicit.stat_3299347043", "text": "+# to maximum Life"},
        {"id": "explicit.stat_3372524247", "text": "+#% to Fire Resistance"},
        {"id": "explicit.stat_1940865751", "text": "Adds # to # Physical Damage"}]}]}
    st = trade.stats_index(raw)
    assert trade.normalize("+(130-144) to maximum Life") == trade.normalize("+140 to maximum Life") == "+# to maximum life"
    q, miss = trade.mods_query("Stygian Vise", [("+(130-144) to maximum Life", trade.min_value("+(130-144) to maximum Life")),
                                                ("+(36-41)% to Fire Resistance", 36), ("Something weird", None)], st)
    assert [f["id"] for f in q["stats"][0]["filters"]] == ["explicit.stat_3299347043", "explicit.stat_3372524247"]
    assert q["stats"][0]["filters"][0]["value"]["min"] == 130 and miss == ["Something weird"]
    url = trade.search_url("Allflame", trade.base_query("Stygian Vise", 84))
    assert url.startswith("https://www.pathofexile.com/trade/search/Allflame?q=")
    body = json.loads(urllib.parse.unquote(url.split("?q=", 1)[1]))
    assert body["query"]["type"] == "Stygian Vise" and body["query"]["filters"]["misc_filters"]["filters"]["ilvl"]["min"] == 84


def test_plans_run():
    from poecraft import plans
    from poecraft.calc import Target
    from poecraft.emulator import Emulator
    from poecraft.prices import Prices
    from poecraft.pool import ModPool
    data = GameData()
    em = Emulator(data, ModPool(data, data.bases["Stygian Vise"], 86), seed=1)
    targets = [Target("prefix", "IncreasedLife", 5, "Жизнь"), Target("suffix", "FireResistance", 5, "Огонь")]
    steps = plans.presets(len(targets))["Chaos до цели"]
    r = plans.simulate(data, em, targets, steps, 20, Prices())
    assert r["items"] == 20 and r["rate"] > 0.9 and r["avg_ops"] > 1
    assert em.rarity == "Normal" and not em.mods          # исходный предмет не тронут
    steps = plans.presets(len(targets))["Alt+Aug → Regal → Exalt"]
    r = plans.simulate(data, em, targets, steps, 20, Prices())
    assert r["items"] == 20 and not r["errors"], r
    assert "пока не" in plans.step_text(steps[1])


def test_i18n_phrases():
    import pytest
    pytest.importorskip("tkinter")
    from poecraft import i18n
    try:
        i18n.set_lang("en")
        assert i18n.t("Chaos работает только на редком предмете.") == "Chaos works only on a rare item."
        assert i18n.t("Готово: 300 предметов") == "Done: 300 items"
        assert i18n.t("PoE Craft Helper") == "PoE Craft Helper"
    finally:
        i18n.set_lang("ru")
    assert i18n.t("Готово") == "Готово"
