"""OpenAICompatGenerationProvider 单元测试 — stub client 驱动，完全离线。

覆盖 Spec 008 AC-18 ~ AC-19、AC-25、AC-28 ~ AC-32、AC-38。
所有测试都显式注入 client=stub(...) 与 model="test-model"：stub 路径不依赖任何环境变量。
异步调用沿用仓库既有的 asyncio.run 模式（不引入新的测试依赖）。
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

import genui_api.generation.openai_compat_provider as provider_module
from genui_api.generation.openai_compat_provider import (
    MAX_TOKENS,
    MODE_JSON_OBJECT,
    MODE_JSON_SCHEMA,
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


@pytest.fixture(autouse=True)
def _reset_structured_output_mode():
    """结构化输出模式是进程内协商状态（模块级）；每个测试前复位，保证隔离。"""
    provider_module._active_mode = MODE_JSON_SCHEMA
    yield
    provider_module._active_mode = MODE_JSON_SCHEMA


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
    # 复杂页面输出可达数千 token；8000 经真实端点验证，避免截断产生半成品 JSON。
    assert MAX_TOKENS == 8000


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


def test_generate_draft_requests_json_schema_response_format_by_default():
    """第一层收敛：默认以 DSL Schema 驱动的 json_schema 结构化输出约束候选。"""
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("做一个落地页"))
    response_format = client.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    json_schema = response_format["json_schema"]
    assert json_schema["name"] == "genui_dsl_document"
    # Schema 派生自唯一契约事实来源（DslDocument 模型），含递归 $defs
    assert json_schema["schema"]["$defs"]
    assert json_schema["schema"]["properties"]["version"]["const"] == "0.1"


def test_generate_draft_passes_deterministic_sampling():
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("做一个落地页"))
    kwargs = client.calls[0]
    assert kwargs["temperature"] == 0.0
    assert kwargs["max_tokens"] == 8000


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
    """response_format 每次传入独立外层 dict，被调用方改动不会污染后续调用。"""
    provider, client = _provider(content=json.dumps(VALID_DSL))
    _run(provider.generate_draft("a"))
    client.calls[0]["response_format"]["type"] = "mutated"
    _run(provider.generate_draft("b"))
    assert client.calls[1]["response_format"]["type"] == "json_schema"


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


def test_generate_draft_failure_is_provider_response_error_not_intent():
    """真实 Provider 不做意图分类：内容不可用 → ProviderResponseError（固定文案）。

    「意图无法识别」概念已从产品移除——失败就是失败，由上层 fail-closed。
    """
    provider, _ = _provider(content="not json")
    with pytest.raises(ProviderResponseError):
        _run(provider.generate_draft("x"))


# ============================================================
# 结构化输出降级梯度（json_schema → json_object）
# ============================================================


class _FormatRejection400(Exception):
    """模拟端点拒绝 json_schema 的 400（带 status_code 与 schema 字样）。"""

    status_code = 400

    def __str__(self):
        return "Error code: 400 - response_format.json_schema is not supported"


class DowngradeStubClient(StubClient):
    """首次调用按 raises 抛错，之后恢复正常（用于模拟一次性协商失败）。"""

    def __init__(self, *, fail_first=None, **kwargs):
        super().__init__(**kwargs)
        self._fail_first = fail_first

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail_first is not None:
            exc = self._fail_first
            self._fail_first = None
            raise exc
        if not self.with_choices:
            return SimpleNamespace(choices=[], usage=self.usage)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=self.usage,
        )


def test_downgrades_to_json_object_when_endpoint_rejects_json_schema():
    """端点拒绝 json_schema（400 + schema 字样）→ 本次请求内降级并重试成功。"""
    client = DowngradeStubClient(
        fail_first=_FormatRejection400(), content=json.dumps(VALID_DSL)
    )
    provider = OpenAICompatGenerationProvider(client=client, model=TEST_MODEL)
    result = _run(provider.generate_draft("做一个落地页"))
    assert result == VALID_DSL
    # 第一次 json_schema，第二次 json_object
    assert client.calls[0]["response_format"]["type"] == "json_schema"
    assert client.calls[1]["response_format"] == {"type": "json_object"}
    # 协商结果对进程内后续调用固定
    assert provider_module._active_mode == MODE_JSON_OBJECT


def test_downgrade_persists_for_subsequent_requests():
    client = DowngradeStubClient(
        fail_first=_FormatRejection400(), content=json.dumps(VALID_DSL)
    )
    provider = OpenAICompatGenerationProvider(client=client, model=TEST_MODEL)
    _run(provider.generate_draft("a"))
    _run(provider.generate_draft("b"))
    # 第三次调用（第二个请求）直接用 json_object，不再试探 json_schema
    assert client.calls[2]["response_format"] == {"type": "json_object"}
    assert provider_module._active_mode == MODE_JSON_OBJECT


def test_non_format_400_does_not_downgrade():
    """与格式无关的 400（如模型名非法）不触发降级，直接净化上报。"""

    class ModelNotFound400(Exception):
        status_code = 400

        def __str__(self):
            return "Error code: 400 - model not found"

    provider, _ = _provider(raises=ModelNotFound400())
    with pytest.raises(ProviderResponseError):
        _run(provider.generate_draft("x"))
    assert provider_module._active_mode == MODE_JSON_SCHEMA


def test_downgrade_failure_still_sanitized():
    """json_schema 与 json_object 都失败时，仍是固定净化文案，无端点/凭证泄漏。"""

    class Always400(DowngradeStubClient):
        async def _create(self, **kwargs):
            self.calls.append(kwargs)
            raise _FormatRejection400()

    client = Always400(content=json.dumps(VALID_DSL))
    provider = OpenAICompatGenerationProvider(client=client, model=TEST_MODEL)
    with pytest.raises(ProviderResponseError) as exc:
        _run(provider.generate_draft("x"))
    assert "json_schema" not in str(exc.value)


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
