"""Generation Pipeline 单元测试 — 6 步顺序、prompt 规则、信任边界、恶意 Provider"""

import asyncio
import copy

import pytest

from genui_api.contracts.dsl import DslDocument
from genui_api.generation.base import UnrecognizedIntentError
from genui_api.generation.mock import MockGenerationProvider
from genui_api.generation.pipeline import (
    MAX_PROMPT_LENGTH,
    GenerationError,
    generate_document,
)
from genui_api.generation.templates import TEMPLATE_COFFEE_SHOP


def _run(coro):
    return asyncio.run(coro)


# ============================================================
# 测试用 Provider
# ============================================================


class CountingProvider:
    """记录调用次数与收到的 prompt。"""

    def __init__(self, candidate: object = None):
        self.calls: list[str] = []
        self._candidate = (
            candidate if candidate is not None else copy.deepcopy(TEMPLATE_COFFEE_SHOP)
        )

    async def generate_draft(self, prompt: str) -> dict:
        self.calls.append(prompt)
        return copy.deepcopy(self._candidate)


class FixedCandidateProvider:
    """返回任意固定候选（可为非 dict / 非法文档）。"""

    def __init__(self, candidate):
        self.candidate = candidate

    async def generate_draft(self, prompt: str):
        return self.candidate


class UnrecognizedProvider:
    async def generate_draft(self, prompt: str) -> dict:
        raise UnrecognizedIntentError("no intent")


class CrashingProvider:
    """抛出普通异常，异常原文含敏感标记以验证净化。"""

    async def generate_draft(self, prompt: str) -> dict:
        raise RuntimeError("SECRET_TRACE /tmp/secret/path.py api_key=abc123")


class ValueErrorProvider:
    async def generate_draft(self, prompt: str) -> dict:
        raise ValueError("boom")


# ============================================================
# 夹具
# ============================================================


def _duplicate_id_doc() -> dict:
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {"title": "Dup"},
            "children": [
                {"id": "dup", "type": "Text", "props": {"text": "one"}},
                {"id": "dup", "type": "Text", "props": {"text": "two"}},
            ],
        },
    }


def _input_outside_form_doc() -> dict:
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {"title": "Bad nesting"},
            "children": [
                {
                    "id": "lonely-input",
                    "type": "Input",
                    "props": {"name": "n", "label": "L"},
                }
            ],
        },
    }


def _unknown_type_doc() -> dict:
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {},
            "children": [{"id": "weird", "type": "Marquee", "props": {}}],
        },
    }


def _unknown_field_doc() -> dict:
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {},
            "children": [],
            "onClick": "alert(1)",
        },
    }


# ============================================================
# 步 1 / 2：prompt 规则（Provider 不被调用）
# ============================================================


@pytest.mark.parametrize("prompt", ["", "   ", "\n\t  \n"])
def test_empty_or_whitespace_prompt_is_rejected(prompt):
    provider = CountingProvider()
    with pytest.raises(GenerationError) as exc:
        _run(generate_document(prompt, provider))
    assert exc.value.code == "invalid_prompt"
    assert provider.calls == []


def test_prompt_over_limit_is_rejected_and_provider_not_called():
    provider = CountingProvider()
    prompt = "咖" * (MAX_PROMPT_LENGTH + 1)
    with pytest.raises(GenerationError) as exc:
        _run(generate_document(prompt, provider))
    assert exc.value.code == "invalid_prompt"
    assert provider.calls == []


def test_prompt_exactly_at_limit_is_accepted():
    provider = CountingProvider()
    prompt = "咖" + "a" * (MAX_PROMPT_LENGTH - 1)
    assert len(prompt) == MAX_PROMPT_LENGTH
    result = _run(generate_document(prompt, provider))
    assert isinstance(result, DslDocument)
    assert provider.calls == [prompt]


def test_prompt_is_trimmed_before_length_check():
    provider = CountingProvider()
    prompt = "   " + "a" * MAX_PROMPT_LENGTH + "   "
    result = _run(generate_document(prompt, provider))
    assert isinstance(result, DslDocument)
    # 步 3 传入的是 trim 后的 prompt
    assert provider.calls == ["a" * MAX_PROMPT_LENGTH]


def test_invalid_prompt_error_carries_issues():
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("   ", CountingProvider()))
    assert len(exc.value.issues) == 1
    assert exc.value.issues[0].code == "invalid_prompt"
    assert exc.value.issues[0].path == "prompt"


# ============================================================
# 步 3 / 4：Provider 异常分类
# ============================================================


def test_unrecognized_intent_maps_to_unrecognized_intent_code():
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("随便来点什么", UnrecognizedProvider()))
    assert exc.value.code == "unrecognized_intent"
    assert exc.value.issues[0].code == "unrecognized_intent"


def test_provider_crash_maps_to_provider_error_with_sanitized_message():
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("咖啡店", CrashingProvider()))
    assert exc.value.code == "provider_error"
    assert "SECRET_TRACE" not in exc.value.message
    assert "/tmp/secret/path.py" not in exc.value.message
    assert "api_key" not in exc.value.message
    for issue in exc.value.issues:
        assert "SECRET_TRACE" not in issue.message


def test_provider_value_error_also_maps_to_provider_error():
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("咖啡店", ValueErrorProvider()))
    assert exc.value.code == "provider_error"


# ============================================================
# 步 5：候选非 dict
# ============================================================


@pytest.mark.parametrize(
    "candidate", [None, "a string", 42, ["list"], (1, 2), True]
)
def test_non_dict_candidate_maps_to_invalid_generated_document(candidate):
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("咖啡店", FixedCandidateProvider(candidate)))
    assert exc.value.code == "invalid_generated_document"


# ============================================================
# 步 6：候选必须通过 validate_dsl_document
# ============================================================


@pytest.mark.parametrize(
    "candidate_factory",
    [
        _duplicate_id_doc,
        _input_outside_form_doc,
        _unknown_type_doc,
        _unknown_field_doc,
        dict,  # 空 dict：缺 version / root
    ],
)
def test_invalid_candidate_document_maps_to_invalid_generated_document(
    candidate_factory,
):
    with pytest.raises(GenerationError) as exc:
        _run(
            generate_document(
                "咖啡店", FixedCandidateProvider(candidate_factory())
            )
        )
    assert exc.value.code == "invalid_generated_document"


def test_duplicate_id_candidate_issues_carry_validator_details():
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("咖啡店", FixedCandidateProvider(_duplicate_id_doc())))
    assert exc.value.issues
    codes = {issue.code for issue in exc.value.issues}
    assert "duplicate_id" in codes
    for issue in exc.value.issues:
        assert issue.path
        assert issue.message


def test_invalid_nesting_candidate_issues_carry_validator_details():
    with pytest.raises(GenerationError) as exc:
        _run(
            generate_document(
                "咖啡店", FixedCandidateProvider(_input_outside_form_doc())
            )
        )
    codes = {issue.code for issue in exc.value.issues}
    assert "invalid_nesting" in codes


def test_root_not_page_candidate_is_rejected():
    candidate = {
        "version": "0.1",
        "root": {"id": "text-root", "type": "Text", "props": {"text": "x"}},
    }
    with pytest.raises(GenerationError) as exc:
        _run(generate_document("咖啡店", FixedCandidateProvider(candidate)))
    assert exc.value.code == "invalid_generated_document"


# ============================================================
# 成功路径
# ============================================================


def test_successful_generation_returns_dsl_document():
    result = _run(generate_document("咖啡店落地页", MockGenerationProvider()))
    assert isinstance(result, DslDocument)
    assert result.version == "0.1"
    assert result.root.type == "Page"
    assert result.root.id == "page"


def test_successful_generation_with_mock_provider_is_deterministic():
    first = _run(generate_document("咖啡店落地页", MockGenerationProvider()))
    second = _run(generate_document("咖啡店落地页", MockGenerationProvider()))
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_pipeline_does_not_mutate_provider_candidate_source():
    baseline = copy.deepcopy(TEMPLATE_COFFEE_SHOP)
    _run(generate_document("咖啡店", MockGenerationProvider()))
    assert TEMPLATE_COFFEE_SHOP == baseline


def test_generation_error_defaults_to_empty_issues():
    error = GenerationError(code="invalid_prompt", message="m")
    assert error.issues == []
    assert str(error) == "m"


def test_pipeline_source_has_single_validation_entry_and_no_copied_rules():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "genui_api"
        / "generation"
        / "pipeline.py"
    ).read_text()
    assert source.count("validate_dsl_document(") == 1
    # 未复制任何 DSL 校验规则
    for forbidden in (
        "duplicate",
        "FORM_ALLOWED_CHILDREN",
        "CONTAINER_TYPES",
        "LEAF_TYPES",
        '"Page"',
    ):
        assert forbidden not in source
    # 无对候选的类型断言 / 选择性信任
    assert "cast(" not in source
    assert "# type: ignore" not in source
