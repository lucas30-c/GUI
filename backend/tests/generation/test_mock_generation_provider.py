"""Mock Generation Provider 单元测试 — 意图映射、优先级、克隆隔离、模板合法性"""

import asyncio
import copy
import json
from pathlib import Path

import pytest

from genui_api.contracts.validation import validate_dsl_document
from tests.doubles.generation import MockGenerationProvider
from tests.doubles.templates import (
    TEMPLATE_COFFEE_SHOP,
    TEMPLATE_EVENT_SIGNUP,
    TEMPLATE_PRODUCT_INTRO,
)


def _run(coro):
    return asyncio.run(coro)


def _draft(prompt: str) -> dict:
    return _run(MockGenerationProvider().generate_draft(prompt))


def _find(node: dict, node_id: str) -> dict | None:
    if node.get("id") == node_id:
        return node
    for child in node.get("children", []):
        found = _find(child, node_id)
        if found is not None:
            return found
    return None


def _collect_ids(node: dict, acc: list[str] | None = None) -> list[str]:
    ids = acc if acc is not None else []
    ids.append(node["id"])
    for child in node.get("children", []):
        _collect_ids(child, ids)
    return ids


@pytest.fixture
def gold_case_json():
    path = (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "dsl"
        / "coffee-shop-landing.json"
    )
    return json.loads(path.read_text())


# ============================================================
# 意图映射正向
# ============================================================


@pytest.mark.parametrize(
    "prompt",
    ["我要一个咖啡店的落地页", "帮我做个 coffee shop 页面", "咖啡"],
)
def test_coffee_keywords_map_to_coffee_template(prompt):
    assert _draft(prompt) == TEMPLATE_COFFEE_SHOP


@pytest.mark.parametrize(
    "prompt",
    [
        "做一个报名页",
        "我需要一个表单页面",
        "线下活动页",
        "build a signup page",
        "a form page",
        "event page please",
    ],
)
def test_event_keywords_map_to_event_template(prompt):
    assert _draft(prompt) == TEMPLATE_EVENT_SIGNUP


@pytest.mark.parametrize(
    "prompt",
    [
        "我要一个产品页",
        "给我做个介绍页",
        "来个落地页",
        "a product page",
        "landing page for us",
    ],
)
def test_product_keywords_map_to_product_template(prompt):
    assert _draft(prompt) == TEMPLATE_PRODUCT_INTRO


# ============================================================
# 大小写不敏感与优先级
# ============================================================


@pytest.mark.parametrize("prompt", ["COFFEE SHOP", "Coffee Bar", "CoFFeE"])
def test_keyword_match_is_case_insensitive_for_coffee(prompt):
    assert _draft(prompt) == TEMPLATE_COFFEE_SHOP


@pytest.mark.parametrize("prompt", ["Signup Form", "EVENT SIGNUP", "A FORM"])
def test_keyword_match_is_case_insensitive_for_event(prompt):
    assert _draft(prompt) == TEMPLATE_EVENT_SIGNUP


def test_prompt_is_stripped_before_matching():
    assert _draft("   咖啡店落地页   \n") == TEMPLATE_COFFEE_SHOP


def test_priority_coffee_beats_product():
    # 命中优先级 1（咖啡）与 3（产品/介绍/落地页），取先者
    assert _draft("咖啡产品介绍落地页") == TEMPLATE_COFFEE_SHOP


def test_priority_coffee_beats_event():
    # 命中优先级 1（咖啡）与 2（报名/活动），取先者
    assert _draft("咖啡品鉴活动报名") == TEMPLATE_COFFEE_SHOP


def test_priority_event_beats_product():
    # 命中优先级 2（报名）与 3（介绍），取先者
    assert _draft("产品发布会报名介绍") == TEMPLATE_EVENT_SIGNUP


# ============================================================
# 无命中：确定性回退（「意图无法识别」概念已从产品移除）
# ============================================================


@pytest.mark.parametrize(
    "prompt",
    ["随便来点什么", "hello world", "帮我写首诗", "做个后台管理系统"],
)
def test_unmatched_prompt_falls_back_to_default_template(prompt):
    # Real-Provider-only：测试替身不再抛「意图无法识别」，
    # 无关键词命中时确定性回退到默认模板（仍是合法 DSL 文档）。
    result = _draft(prompt)
    assert result == TEMPLATE_PRODUCT_INTRO
    validate_dsl_document(result)


def test_unmatched_prompt_fallback_is_deterministic():
    for prompt in ("随便来点什么", "xyz"):
        assert _draft(prompt) == _draft(prompt)


# ============================================================
# 确定性与深拷贝隔离
# ============================================================


@pytest.mark.parametrize(
    "prompt", ["咖啡店落地页", "活动报名页", "产品介绍页"]
)
def test_same_prompt_is_deterministic_across_calls(prompt):
    first = _draft(prompt)
    second = _draft(prompt)
    third = _draft(prompt)
    assert first == second == third


def test_returned_document_is_not_the_template_constant():
    result = _draft("咖啡")
    assert result is not TEMPLATE_COFFEE_SHOP
    assert result["root"] is not TEMPLATE_COFFEE_SHOP["root"]
    assert result["root"]["children"] is not TEMPLATE_COFFEE_SHOP["root"]["children"]
    assert (
        result["root"]["children"][0]
        is not TEMPLATE_COFFEE_SHOP["root"]["children"][0]
    )


def test_two_calls_return_independent_objects():
    first = _draft("咖啡")
    second = _draft("咖啡")
    assert first is not second
    assert first["root"] is not second["root"]


def test_mutating_returned_document_does_not_affect_later_generations():
    baseline = copy.deepcopy(TEMPLATE_COFFEE_SHOP)

    first = _draft("咖啡")
    hero_title = _find(first["root"], "hero.title")
    assert hero_title is not None
    hero_title["props"]["text"] = "被篡改的标题"
    first["root"]["children"].clear()
    first["version"] = "9.9"

    second = _draft("咖啡")
    assert second == baseline
    assert TEMPLATE_COFFEE_SHOP == baseline


def test_mutating_returned_document_does_not_affect_other_templates():
    event_baseline = copy.deepcopy(TEMPLATE_EVENT_SIGNUP)
    draft = _draft("活动报名")
    draft["root"]["props"]["title"] = "篡改"
    assert _draft("活动报名") == event_baseline


# ============================================================
# 模板合法性与锚点节点
# ============================================================


@pytest.mark.parametrize(
    "template",
    [TEMPLATE_COFFEE_SHOP, TEMPLATE_EVENT_SIGNUP, TEMPLATE_PRODUCT_INTRO],
)
def test_each_template_passes_dsl_validation(template):
    doc = validate_dsl_document(template)
    assert doc.version == "0.1"
    assert doc.root.type == "Page"
    assert doc.root.id == "page"


@pytest.mark.parametrize(
    "template",
    [TEMPLATE_COFFEE_SHOP, TEMPLATE_EVENT_SIGNUP, TEMPLATE_PRODUCT_INTRO],
)
def test_each_template_has_globally_unique_ids(template):
    ids = _collect_ids(template["root"])
    assert len(ids) == len(set(ids))


def test_coffee_template_anchor_nodes_exist():
    root = TEMPLATE_COFFEE_SHOP["root"]
    title = _find(root, "hero.title")
    subtitle = _find(root, "hero.subtitle")
    assert title is not None and title["type"] == "Heading"
    assert subtitle is not None and subtitle["type"] == "Text"
    sections = [c for c in root["children"] if c["type"] == "Section"]
    assert len(sections) >= 2


def test_event_template_anchor_nodes_exist():
    root = TEMPLATE_EVENT_SIGNUP["root"]
    intro_title = _find(root, "intro.title")
    form = _find(root, "signup.form")
    name = _find(root, "signup.form.name")
    email = _find(root, "signup.form.email")
    submit = _find(root, "signup.form.submit")
    assert intro_title is not None and intro_title["type"] == "Heading"
    assert form is not None and form["type"] == "Form"
    assert name is not None and name["type"] == "Input"
    assert email is not None and email["type"] == "Input"
    assert submit is not None and submit["type"] == "Button"
    inputs_in_form = [c for c in form["children"] if c["type"] == "Input"]
    assert len(inputs_in_form) >= 2


def test_product_template_anchor_nodes_exist():
    root = TEMPLATE_PRODUCT_INTRO["root"]
    title = _find(root, "hero.title")
    tagline = _find(root, "hero.tagline")
    assert title is not None and title["type"] == "Heading"
    assert tagline is not None and tagline["type"] == "Text"
    sections = [c for c in root["children"] if c["type"] == "Section"]
    assert len(sections) >= 2
    features = _find(root, "features")
    assert features is not None
    cards = [c for c in features["children"] if c["type"] == "Card"]
    assert len(cards) >= 2


@pytest.mark.parametrize(
    "template",
    [TEMPLATE_COFFEE_SHOP, TEMPLATE_EVENT_SIGNUP, TEMPLATE_PRODUCT_INTRO],
)
def test_each_template_has_refinable_text_node(template):
    def walk(node):
        yield node
        for child in node.get("children", []):
            yield from walk(child)

    refinable = [
        n for n in walk(template["root"]) if n["type"] in ("Heading", "Text", "Button")
    ]
    assert len(refinable) >= 1


def test_coffee_template_hero_title_differs_from_gold_case(gold_case_json):
    gold_title = _find(gold_case_json["root"], "hero.title")
    template_title = _find(TEMPLATE_COFFEE_SHOP["root"], "hero.title")
    assert gold_title is not None and template_title is not None
    assert template_title["props"]["text"] != gold_title["props"]["text"]


def test_coffee_template_is_not_a_copy_of_gold_case(gold_case_json):
    assert TEMPLATE_COFFEE_SHOP != gold_case_json
    assert TEMPLATE_COFFEE_SHOP["root"]["props"] != gold_case_json["root"]["props"]
