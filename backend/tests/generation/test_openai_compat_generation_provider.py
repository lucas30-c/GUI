"""OpenAICompatGenerationProvider 单元测试 — stub client 驱动，完全离线。

覆盖 Spec 008 AC-18 ~ AC-19、AC-25、AC-28 ~ AC-32、AC-38。
所有测试都显式注入 client=stub(...) 与 model="test-model"：stub 路径不依赖任何环境变量。
异步调用沿用仓库既有的 asyncio.run 模式（不引入新的测试依赖）。
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from genui_api.generation.base import UnrecognizedIntentError
from genui_api.generation.openai_compat_provider import (
    MAX_TOKENS,
    TEMPERATURE,
    OpenAICompatGenerationProvider,
)
from genui_api.llm.client import ProviderResponseError
from genui_api.llm.prompts import build_generation_system_prompt

TEST_MODEL = "test-model"

VALID_DSL = {
    "version": "0.1",
    "root": {
        "id": "page",
        "type": "Page",
        "props": {"title": "Demo"},
        "children": [
            {"id": "hero.title", "type": "Heading", "props": {"text": "Hi", "level": 1}}
        ],
    },
}


def _run(coro):
    return asyncio.run(coro)


# ============================================================
# Stub client
# ============================================================


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
    return OpenAICompatGenerationProvider(client=client, model=TEST_MODEL), client


# ============================================================
# 构造（AC-18 / AC-19）
# ============================================================


def test_provider_can_be_constructed_without_credentials():
    """构造阶段不读凭证、不建连接：无环境变量下也能实例化。"""
    assert OpenAICompatGenerationProvider() is not None


def test_default_sampling_constants_are_deterministic():
    assert TEMPERATURE == 0.0
    assert MAX_TOKENS == 4096


# ============================================================
# 正向路径（AC-25 / AC-28 / AC-29）
# ============================================================


def test_generate_draft_returns_dict_on_valid_json():
    provider, _ = _provider(content=json.dumps(VALID_DSL))
    result = _run(provider.generate_draft("做一个落地页"))
    assert isinstance(result, dict)
    assert result == VALID_DSL


def test_generate_draft_uses_injected_model_not_environment():
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("做一个落地页"))
    assert client.calls[0]["model"] == TEST_MODEL, client.calls[0]


def test_generate_draft_requests_json_object_response_format():
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("做一个落地页"))
    assert client.calls[0]["response_format"] == {"type": "json_object"}


def test_generate_draft_passes_deterministic_sampling():
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("做一个落地页"))
    kwargs = client.calls[0]
    assert kwargs["temperature"] == 0.0
    assert kwargs["max_tokens"] == 4096


def test_generate_draft_separates_system_and_user_roles():
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("做一个咖啡店落地页"))
    messages = client.calls[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == build_generation_system_prompt()
    assert messages[1]["content"] == "做一个咖啡店落地页"


def test_generate_draft_never_puts_user_input_in_system_message():
    provider, client = _provider(content=json.dumps(VALID_DSL))
    marker = "INJECTED-USER-MARKER"
    _run(provider.generate_draft(marker))
    messages = client.calls[0]["messages"]
    assert marker not in messages[0]["content"]
    assert marker in messages[1]["content"]


def test_generate_draft_returns_candidate_without_sanitizing():
    """Provider 不清洗候选：schema 外字段原样上报，由 Pipeline 校验层拒绝。"""
    hostile = {"version": "0.1", "root": {}, "evil": "<script>alert(1)</script>"}
    provider, _ = _provider(content=json.dumps(hostile))
    assert _run(provider.generate_draft("x")) == hostile


def test_response_format_is_a_fresh_copy_per_call():
    """response_format 每次传入独立副本，被调用方改动不会污染模块常量。"""
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("a"))
    client.calls[0]["response_format"]["type"] = "mutated"
    _run(provider.generate_draft("b"))
    assert client.calls[1]["response_format"] == {"type": "json_object"}


# ============================================================
# 反向路径（AC-30 / AC-31 / AC-32）
# ============================================================


@pytest.mark.parametrize(
    "content",
    [
        "这是一段自然语言，不是 JSON",
        "",
        "   ",
        None,
        "[]",
        '```json\n{"version": "0.1"}\n```',
        '{"unclosed":',
    ],
)
def test_generate_draft_raises_on_unusable_content(content):
    provider, _ = _provider(content=content)
    with pytest.raises(ProviderResponseError):
        _run(provider.generate_draft("x"))


def test_generate_draft_raises_on_empty_choices():
    provider, _ = _provider(with_choices=False)
    with pytest.raises(ProviderResponseError):
        _run(provider.generate_draft("x"))


def test_generate_draft_converts_sdk_exception_to_sanitized_error():
    """SDK 网络/认证异常 → 固定文案异常，绝不携带端点或凭证片段。"""
    provider, _ = _provider(
        raises=RuntimeError(
            "401 Unauthorized: api_key=sk-secret https://real.invalid/v1"
        )
    )
    with pytest.raises(ProviderResponseError) as exc:
        _run(provider.generate_draft("x"))
    message = str(exc.value)
    assert "sk-secret" not in message
    assert "real.invalid" not in message
    assert exc.value.__cause__ is None


def test_generate_draft_never_raises_unrecognized_intent():
    """真实 Provider 不做意图分类：失败必须表达为 provider 错误而非「意图无法识别」。"""
    provider, _ = _provider(content="not json")
    with pytest.raises(ProviderResponseError) as exc:
        _run(provider.generate_draft("x"))
    assert not isinstance(exc.value, UnrecognizedIntentError)


def test_generate_draft_error_message_is_fixed():
    provider_a, _ = _provider(content="not json")
    provider_b, _ = _provider(raises=TimeoutError("connect timeout to real.invalid"))
    with pytest.raises(ProviderResponseError) as first:
        _run(provider_a.generate_draft("x"))
    with pytest.raises(ProviderResponseError) as second:
        _run(provider_b.generate_draft("x"))
    assert str(first.value) == str(second.value)


# ============================================================
# 无跨请求状态（AC-38）
# ============================================================


def test_provider_has_no_cross_request_state():
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("第一次请求"))
    _run(provider.generate_draft("第二次请求"))
    first, second = client.calls
    assert first["messages"][0] == second["messages"][0]
    assert first["messages"][1]["content"] == "第一次请求"
    assert second["messages"][1]["content"] == "第二次请求"
    assert len(first["messages"]) == len(second["messages"]) == 2


def test_failed_call_does_not_poison_subsequent_calls():
    provider, client = _provider(content="not json")
    with pytest.raises(ProviderResponseError):
        _run(provider.generate_draft("bad"))

    client.content = json.dumps(VALID_DSL)
    assert _run(provider.generate_draft("good")) == VALID_DSL


def test_two_provider_instances_are_independent():
    provider_a, client_a = _provider(content=json.dumps(VALID_DSL))
    provider_b, client_b = _provider(content=json.dumps(VALID_DSL))
    _run(provider_a.generate_draft("a"))
    assert client_b.calls == []
    _run(provider_b.generate_draft("b"))
    assert len(client_a.calls) == 1
    assert len(client_b.calls) == 1
