"""三层收敛机制测试 — 无损规范化（第二层）+ 精准 repair（第三层）。

覆盖 Owner 验收要求：
- 首次合法 / 首次含 margin:'0 auto' / 首次含 marginTop → 直接通过；
- 可无损规范化的候选（大小写枚举、数字字重、首尾空白）→ 规范化后通过且被记录；
- 首次非法但 repair 成功 → 最终成功、repair_used=True、恰好两次调用；
- repair 后仍失败 → fail-closed、不超过一次 retry（恰好两次调用）；
- repair prompt 机器可读：含错误路径、收到的值、允许字段与值域；
- 错误不会覆盖有效页面是前端/提交层性质，此处以「失败不返回文档」侧面覆盖。
"""

import asyncio
import copy
import json

import pytest

from genui_api.contracts.dsl import DslDocument
from genui_api.generation.pipeline import (
    MAX_GENERATION_RETRIES,
    GenerationError,
    _normalize_document,
    build_repair_user_prompt,
    generate_document,
)
from tests.doubles.templates import TEMPLATE_COFFEE_SHOP


def _run(coro):
    return asyncio.run(coro)


def _valid_doc() -> dict:
    return copy.deepcopy(TEMPLATE_COFFEE_SHOP)


class ScriptedProvider:
    """按脚本顺序返回候选并记录每次收到的 prompt。"""

    def __init__(self, candidates: list):
        self._candidates = list(candidates)
        self.calls: list[str] = []

    async def generate_draft(self, prompt: str) -> dict:
        self.calls.append(prompt)
        if not self._candidates:
            raise AssertionError("provider called more times than scripted")
        candidate = self._candidates.pop(0)
        if isinstance(candidate, Exception):
            raise candidate
        return candidate


def _doc_with_style(style: dict) -> dict:
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {"title": "T"},
            "style": style,
            "children": [
                {"id": "s", "type": "Section", "children": [
                    {"id": "s.h", "type": "Heading", "props": {"text": "H", "level": 1}}
                ]}
            ],
        },
    }


# ============================================================
# 直接通过场景
# ============================================================


def test_first_attempt_valid_passes_without_repair():
    provider = ScriptedProvider([_valid_doc()])
    outcome = _run(generate_document("咖啡店", provider))
    assert isinstance(outcome.document, DslDocument)
    assert outcome.attempts == 1
    assert outcome.repair_used is False
    assert len(provider.calls) == 1


def test_first_attempt_with_margin_zero_auto_passes():
    """Owner 复现值 margin:'0 auto' 首次即通过（Schema 原生接受）。"""
    provider = ScriptedProvider([_doc_with_style({"margin": "0 auto"})])
    outcome = _run(generate_document("落地页", provider))
    assert outcome.document.root.style.margin == "0 auto"
    assert outcome.attempts == 1
    assert outcome.repair_used is False


def test_first_attempt_with_margin_top_passes():
    provider = ScriptedProvider([_doc_with_style({"marginTop": "2rem"})])
    outcome = _run(generate_document("落地页", provider))
    assert outcome.document.root.style.marginTop == "2rem"
    assert outcome.attempts == 1


def test_first_attempt_with_box_model_combo_passes():
    provider = ScriptedProvider(
        [
            _doc_with_style(
                {
                    "margin": "0 auto",
                    "padding": "1rem 2rem",
                    "gap": "16px",
                    "display": "flex",
                    "maxWidth": "960px",
                }
            )
        ]
    )
    outcome = _run(generate_document("落地页", provider))
    assert outcome.attempts == 1


# ============================================================
# 第二层：无损规范化
# ============================================================


def test_normalization_enum_case_is_lossless_and_recorded():
    candidate = _doc_with_style({"textAlign": "CENTER", "display": "Flex"})
    normalized, records = _normalize_document(candidate)
    assert normalized["root"]["style"]["textAlign"] == "center"
    assert normalized["root"]["style"]["display"] == "flex"
    kinds = {r.kind for r in records}
    assert kinds == {"enum_case"}
    for record in records:
        assert record.path.startswith("root.style.")
        assert record.before.lower() == record.after


def test_normalization_numeric_font_weight_is_exact_equivalence():
    candidate = _doc_with_style({"fontWeight": "700"})
    normalized, records = _normalize_document(candidate)
    assert normalized["root"]["style"]["fontWeight"] == "bold"
    assert records[0].kind == "font_weight_numeric"
    assert records[0].before == "700"
    assert records[0].after == "bold"


@pytest.mark.parametrize(
    "numeric,keyword", [("400", "normal"), ("500", "medium"), ("600", "semibold"), ("700", "bold")]
)
def test_normalization_numeric_font_weight_full_map(numeric, keyword):
    candidate = _doc_with_style({"fontWeight": numeric})
    normalized, _ = _normalize_document(candidate)
    assert normalized["root"]["style"]["fontWeight"] == keyword


def test_normalization_whitespace_strip_is_lossless():
    candidate = _doc_with_style({"margin": "  0 auto  "})
    normalized, records = _normalize_document(candidate)
    assert normalized["root"]["style"]["margin"] == "0 auto"
    assert records[0].kind == "whitespace"


def test_normalization_does_not_alter_semantically_valid_values():
    style = {"margin": "0 auto", "padding": "1rem", "color": "#123456"}
    candidate = _doc_with_style(dict(style))
    normalized, records = _normalize_document(candidate)
    assert normalized["root"]["style"] == style
    assert records == []


def test_normalization_never_drops_fields_or_truncates_values():
    """有损操作禁令：未知字段与非法值原样保留，交给校验层拒绝。"""
    candidate = _doc_with_style({"margin": "0 auto", "boxShadow": "0 0 4px red"})
    normalized, records = _normalize_document(candidate)
    assert normalized["root"]["style"]["boxShadow"] == "0 0 4px red"
    assert records == []


def test_normalization_records_nested_paths():
    candidate = _valid_doc()
    candidate["root"]["children"][0]["style"] = {"textAlign": "CENTER"}
    normalized, records = _normalize_document(candidate)
    assert normalized["root"]["children"][0]["style"]["textAlign"] == "center"
    assert records[0].path == "root.children.0.style.textAlign"


def test_normalized_candidate_passes_full_validation():
    candidate = _doc_with_style({"fontWeight": "700", "textAlign": "CENTER"})
    provider = ScriptedProvider([candidate])
    outcome = _run(generate_document("落地页", provider))
    assert outcome.attempts == 1
    assert outcome.repair_used is False
    assert len(outcome.normalization) == 2
    assert outcome.document.root.style.fontWeight == "bold"
    assert outcome.document.root.style.textAlign == "center"


# ============================================================
# 第三层：精准 repair
# ============================================================


def _invalid_unknown_field_doc() -> dict:
    return _doc_with_style({"objectFit": "cover", "color": "#111111"})


def _invalid_margin_value_doc() -> dict:
    return _doc_with_style({"margin": "center"})


def test_repair_succeeds_on_second_attempt():
    fixed = _doc_with_style({"color": "#111111"})
    provider = ScriptedProvider([_invalid_unknown_field_doc(), fixed])
    outcome = _run(generate_document("落地页", provider))
    assert isinstance(outcome.document, DslDocument)
    assert outcome.attempts == 2
    assert outcome.repair_used is True
    assert len(provider.calls) == 2


def test_repair_failure_fails_closed_after_exactly_two_calls():
    provider = ScriptedProvider(
        [_invalid_unknown_field_doc(), _invalid_margin_value_doc()]
    )
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("落地页", provider))
    assert exc.value.code == "invalid_generated_document"
    assert exc.value.attempts == 2
    assert exc.value.repair_used is True
    assert len(provider.calls) == 2  # 最多一次 repair，绝不无限重试


def test_max_retries_constant_is_one():
    assert MAX_GENERATION_RETRIES == 1


def test_repair_prompt_is_machine_readable_and_precise():
    """repair 输入必须包含：原始需求、错误路径、收到的值、允许字段与值域。"""
    from genui_api.contracts.style_registry import style_field_names
    from genui_api.generation.pipeline import GenerationIssue

    candidate = _invalid_unknown_field_doc()
    candidate["root"]["style"]["margin"] = "center"
    error = GenerationError(
        code="invalid_generated_document",
        message="m",
        issues=[
            GenerationIssue(
                path="root.style.objectFit",
                code="schema_error",
                message="Extra inputs are not permitted",
            ),
            GenerationIssue(
                path="root.style.margin",
                code="schema_error",
                message="margin 值非法",
            ),
        ],
    )
    prompt_text = build_repair_user_prompt("做一个落地页", error, candidate)
    payload = json.loads(prompt_text)

    # 原始需求保留（repair 必须保持页面目标）
    assert payload["originalRequest"] == "做一个落地页"
    assert payload["task"] == "repair_dsl_document"

    # 逐条错误：path / code / 收到的值 / 处置约束
    errors = payload["errors"]
    assert [e["path"] for e in errors] == ["root.style.objectFit", "root.style.margin"]
    assert errors[0]["receivedValue"] == "cover"
    assert errors[1]["receivedValue"] == "center"
    assert "objectFit" in errors[0]["constraint"]
    assert "不在 style 白名单中" in errors[0]["constraint"]
    assert "margin" in errors[1]["constraint"]
    assert "auto" in errors[1]["constraint"]  # 值域文法来自 registry

    # 完整 style 契约（机器可读）随 repair 一起下发
    contract = payload["styleContract"]
    assert set(contract) == set(style_field_names())
    assert contract["margin"]["valueType"] == "margin_shorthand"
    assert "grammar" in contract["margin"]
    assert contract["fontWeight"]["allowedValues"] == [
        "normal",
        "medium",
        "semibold",
        "bold",
    ]


def test_repair_prompt_resolves_received_value_for_nested_paths():
    from genui_api.generation.pipeline import GenerationIssue, _resolve_value_at_path

    candidate = {
        "root": {
            "children": [
                {"style": {"margin": "0 auto"}},
                {"children": [{"props": {"text": "x"}}]},
            ]
        }
    }
    assert _resolve_value_at_path(candidate, "root.children.0.style.margin") == "0 auto"
    assert _resolve_value_at_path(candidate, "root.children[1].children[0].props.text") == "x"
    assert _resolve_value_at_path(candidate, "root.children.9.style.margin") is None


def test_failed_generation_returns_no_document():
    """fail-closed：失败路径绝不返回半合法文档（前端据此保留当前有效页面）。"""
    provider = ScriptedProvider(
        [_invalid_unknown_field_doc(), _invalid_unknown_field_doc()]
    )
    with pytest.raises(GenerationError):
        _run(generate_document("落地页", provider))


def test_provider_error_on_first_attempt_fails_without_repair():
    """Provider 崩溃是传输层失败：直接 fail-closed，不进入 repair（repair 只修校验错误）。"""
    provider = ScriptedProvider([RuntimeError("boom")])
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("落地页", provider))
    assert exc.value.code == "provider_error"
    assert len(provider.calls) == 1
