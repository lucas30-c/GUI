"""OpenAICompatRefinementProvider 单元测试 — stub client 驱动，完全离线。

覆盖 Spec 008 AC-18 ~ AC-19、AC-26 ~ AC-32、AC-38。
所有测试都显式注入 client=stub(...) 与 model="test-model"。
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from genui_api.llm.client import ProviderResponseError
from genui_api.llm.prompts import build_refinement_system_prompt
from genui_api.provider.base import RefinementContext
from genui_api.provider.openai_compat_provider import (
    MAX_TOKENS,
    TEMPERATURE,
    OpenAICompatRefinementProvider,
)

TEST_MODEL = "test-model"

VALID_PATCH = {
    "version": "0.1",
    "operations": [
        {
            "op": "update_props",
            "targetNodeId": "hero.title",
            "props": {"style": {"color": "#ff0000"}},
        }
    ],
}


def _run(coro):
    return asyncio.run(coro)


def _context(**overrides):
    values = {
        "instruction": "把标题改成红色",
        "selected_node_id": "hero.title",
        "selected_node_type": "Heading",
        "selected_node_props": {"text": "欢迎", "level": 1},
        "document_version": "0.1",
    }
    values.update(overrides)
    return RefinementContext(**values)


class StubClient:
    """记录调用参数的最小 AsyncOpenAI 替身；不做任何 I/O。"""

    def __init__(self, *, content=None, usage=None, raises=None, with_choices=True):
        self.content = content
        self.usage = usage
        self.raises = raises
        self.with_choices = with_choices
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        if not self.with_choices:
            return SimpleNamespace(choices=[], usage=self.usage)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=self.usage,
        )


def _provider(**stub_kwargs):
    client = StubClient(**stub_kwargs)
    return OpenAICompatRefinementProvider(client=client, model=TEST_MODEL), client


# ============================================================
# 构造（AC-18 / AC-19）
# ============================================================


def test_provider_can_be_constructed_without_credentials():
    assert OpenAICompatRefinementProvider() is not None


def test_default_sampling_constants():
    assert TEMPERATURE == 0.0
    assert MAX_TOKENS == 1024


# ============================================================
# 正向路径（AC-26 / AC-28 / AC-29）
# ============================================================


def test_generate_patch_returns_dict_on_valid_json():
    provider, _ = _provider(content=json.dumps(VALID_PATCH))
    result = _run(provider.generate_patch(_context()))
    assert isinstance(result, dict)
    assert result == VALID_PATCH


def test_generate_patch_uses_injected_model_not_environment():
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    _run(provider.generate_patch(_context()))
    assert client.calls[0]["model"] == TEST_MODEL, client.calls[0]


def test_generate_patch_requests_json_object_response_format():
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    _run(provider.generate_patch(_context()))
    assert client.calls[0]["response_format"] == {"type": "json_object"}


def test_generate_patch_passes_deterministic_sampling():
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    _run(provider.generate_patch(_context()))
    kwargs = client.calls[0]
    assert kwargs["temperature"] == 0.0
    assert kwargs["max_tokens"] == 1024


def test_generate_patch_separates_system_and_user_roles():
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    _run(provider.generate_patch(_context()))
    messages = client.calls[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == build_refinement_system_prompt()


def test_user_prompt_carries_four_dynamic_fields():
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    context = _context()
    _run(provider.generate_patch(context))
    payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert payload["instruction"] == context.instruction
    assert payload["selectedNodeId"] == context.selected_node_id
    assert payload["nodeType"] == context.selected_node_type
    assert payload["currentProps"] == context.selected_node_props


def test_user_prompt_excludes_full_document():
    """最小权限：Provider 只看得到 selected-node 上下文。"""
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    _run(provider.generate_patch(_context()))
    user_content = client.calls[0]["messages"][1]["content"]
    assert '"root"' not in user_content
    assert '"children"' not in user_content


def test_instruction_never_enters_system_message():
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    marker = "INJECTED-INSTRUCTION-MARKER"
    _run(provider.generate_patch(_context(instruction=marker)))
    messages = client.calls[0]["messages"]
    assert marker not in messages[0]["content"]
    assert marker in messages[1]["content"]


def test_provider_does_not_repair_wrong_target_node_id():
    """候选里的 targetNodeId 写错也原样上报，由 Pipeline 边界检查拒绝。

    在 Provider 里「顺手修正」会掩盖 prompt 缺陷，让越界模型看起来是合格的。
    """
    wrong = {
        "version": "0.1",
        "operations": [
            {"op": "update_props", "targetNodeId": "some.other.node", "props": {}}
        ],
    }
    provider, _ = _provider(content=json.dumps(wrong))
    result = _run(provider.generate_patch(_context(selected_node_id="hero.title")))
    assert result["operations"][0]["targetNodeId"] == "some.other.node"


def test_generate_patch_returns_candidate_without_sanitizing():
    hostile = {"version": "0.1", "operations": [], "evil": "onClick"}
    provider, _ = _provider(content=json.dumps(hostile))
    assert _run(provider.generate_patch(_context())) == hostile


def test_response_format_is_a_fresh_copy_per_call():
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    _run(provider.generate_patch(_context()))
    client.calls[0]["response_format"]["type"] = "mutated"
    _run(provider.generate_patch(_context()))
    assert client.calls[1]["response_format"] == {"type": "json_object"}


# ============================================================
# 反向路径（AC-30 / AC-31 / AC-32）
# ============================================================


@pytest.mark.parametrize(
    "content",
    [
        "好的，我已经把标题改成红色了",
        "",
        "  \n ",
        None,
        "[]",
        '```json\n{"version": "0.1"}\n```',
        '{"version":',
    ],
)
def test_generate_patch_raises_on_unusable_content(content):
    provider, _ = _provider(content=content)
    with pytest.raises(ProviderResponseError):
        _run(provider.generate_patch(_context()))


def test_generate_patch_raises_on_empty_choices():
    provider, _ = _provider(with_choices=False)
    with pytest.raises(ProviderResponseError):
        _run(provider.generate_patch(_context()))


def test_generate_patch_converts_sdk_exception_to_sanitized_error():
    provider, _ = _provider(
        raises=RuntimeError("429 rate limit: key=sk-secret at https://real.invalid/v1")
    )
    with pytest.raises(ProviderResponseError) as exc:
        _run(provider.generate_patch(_context()))
    message = str(exc.value)
    assert "sk-secret" not in message
    assert "real.invalid" not in message
    assert exc.value.__cause__ is None


def test_error_message_does_not_leak_instruction_or_props():
    provider, _ = _provider(content="not json")
    context = _context(
        instruction="SECRET-INSTRUCTION-MARKER",
        selected_node_props={"text": "SECRET-PROPS-MARKER"},
    )
    with pytest.raises(ProviderResponseError) as exc:
        _run(provider.generate_patch(context))
    message = str(exc.value)
    assert "SECRET-INSTRUCTION-MARKER" not in message
    assert "SECRET-PROPS-MARKER" not in message


# ============================================================
# 无跨请求状态（AC-38）
# ============================================================


def test_provider_has_no_cross_request_state():
    provider, client = _provider(content=json.dumps(VALID_PATCH))
    _run(provider.generate_patch(_context(instruction="第一次", selected_node_id="a")))
    _run(provider.generate_patch(_context(instruction="第二次", selected_node_id="b")))
    first, second = client.calls
    assert first["messages"][0] == second["messages"][0]
    first_payload = json.loads(first["messages"][1]["content"])
    second_payload = json.loads(second["messages"][1]["content"])
    assert first_payload["selectedNodeId"] == "a"
    assert second_payload["selectedNodeId"] == "b"
    assert "第一次" not in second["messages"][1]["content"]


def test_failed_call_does_not_poison_subsequent_calls():
    provider, client = _provider(content="not json")
    with pytest.raises(ProviderResponseError):
        _run(provider.generate_patch(_context()))

    client.content = json.dumps(VALID_PATCH)
    assert _run(provider.generate_patch(_context())) == VALID_PATCH
