"""llm.client 单元测试 — 配置读取、客户端工厂、响应提取、日志脱敏。

覆盖 Spec 008 AC-05 ~ AC-11、AC-33 ~ AC-35。全部离线，不发起任何网络请求。
"""

import logging
from types import SimpleNamespace

import pytest
from openai import AsyncOpenAI

from genui_api.llm.client import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    PROVIDER_OPENAI_COMPATIBLE,
    PROVIDER_RESPONSE_ERROR_MESSAGE,
    ModelConfig,
    ProviderConfigError,
    ProviderResponseError,
    create_async_client,
    create_openai_client,
    extract_json_object,
    load_model_config,
    log_llm_call,
    log_provider_summary,
)

PLACEHOLDER_KEY = "test-api-key-placeholder"
PLACEHOLDER_BASE_URL = "https://example.invalid/v1"


# ============================================================
# Helpers
# ============================================================


def _response(content, *, usage=None, with_choices=True):
    """构造一个最小的 Chat Completions 响应替身。"""
    if not with_choices:
        return SimpleNamespace(choices=[], usage=usage)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
    )


def _set_real_env(monkeypatch, **overrides):
    values = {
        "GENUI_MODEL_PROVIDER": PROVIDER_OPENAI_COMPATIBLE,
        "GENUI_LLM_API_KEY": PLACEHOLDER_KEY,
        "GENUI_LLM_BASE_URL": PLACEHOLDER_BASE_URL,
        "GENUI_GENERATION_MODEL": "placeholder-generation-model",
    }
    values.update(overrides)
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


# ============================================================
# create_openai_client — 纯工厂（AC-07 / AC-08）
# ============================================================


def test_create_openai_client_returns_async_openai_instance():
    client = create_openai_client(
        api_key=PLACEHOLDER_KEY, base_url=PLACEHOLDER_BASE_URL
    )
    assert isinstance(client, AsyncOpenAI)


def test_create_openai_client_passes_parameters_through():
    client = create_openai_client(
        api_key=PLACEHOLDER_KEY, base_url=PLACEHOLDER_BASE_URL, timeout=12.5
    )
    assert client.api_key == PLACEHOLDER_KEY
    assert str(client.base_url).rstrip("/") == PLACEHOLDER_BASE_URL.rstrip("/")
    assert client.timeout == 12.5


def test_create_openai_client_defaults_are_fail_fast():
    """默认 timeout=120s、max_retries=0：fail fast 是真实行为而非纸面承诺（DD-13）。
    
    P0 修复：timeout 从 30s 增加到 120s 以支持复杂页面生成（bounded retry 最多 2 次）。
    """
    client = create_openai_client(
        api_key=PLACEHOLDER_KEY, base_url=PLACEHOLDER_BASE_URL
    )
    assert client.timeout == DEFAULT_TIMEOUT == 120.0
    assert client.max_retries == DEFAULT_MAX_RETRIES == 0


def test_create_openai_client_does_not_read_environment(monkeypatch):
    """纯工厂：即使环境里有别的凭证，也只使用参数传入的值。"""
    monkeypatch.setenv("GENUI_LLM_API_KEY", "env-key-should-be-ignored")
    monkeypatch.setenv("GENUI_LLM_BASE_URL", "https://env.invalid/v1")
    client = create_openai_client(
        api_key=PLACEHOLDER_KEY, base_url=PLACEHOLDER_BASE_URL
    )
    assert client.api_key == PLACEHOLDER_KEY
    assert "env.invalid" not in str(client.base_url)


# ============================================================
# load_model_config — Real-Provider-only（mock 不再是运行时模式）
# ============================================================


def test_load_model_config_rejects_unset_provider(monkeypatch):
    """未设置 GENUI_MODEL_PROVIDER → ProviderConfigError（绝不默认 mock）。"""
    monkeypatch.delenv("GENUI_MODEL_PROVIDER", raising=False)
    with pytest.raises(ProviderConfigError) as exc:
        load_model_config()
    assert "GENUI_MODEL_PROVIDER" in str(exc.value)


@pytest.mark.parametrize("raw", ["", "   ", "mock", "  MOCK  ", "Mock"])
def test_load_model_config_rejects_mock_variants(monkeypatch, raw):
    """mock / 空值都被拒绝：mock 只是测试替身，不是运行时模式。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", raw)
    with pytest.raises(ProviderConfigError):
        load_model_config()


def test_load_model_config_rejection_is_not_credential_dependent(monkeypatch):
    """即使凭证齐全，mock 值依然被拒绝——模式判定先于凭证读取。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("GENUI_LLM_API_KEY", PLACEHOLDER_KEY)
    monkeypatch.setenv("GENUI_LLM_BASE_URL", PLACEHOLDER_BASE_URL)
    monkeypatch.setenv("GENUI_GENERATION_MODEL", "placeholder-generation-model")
    with pytest.raises(ProviderConfigError):
        load_model_config()


# ============================================================
# load_model_config — openai_compatible（AC-06 / AC-09 / AC-10 / AC-11）
# ============================================================


def test_load_model_config_openai_compatible_full(monkeypatch):
    _set_real_env(monkeypatch)
    config = load_model_config()
    assert config.provider == PROVIDER_OPENAI_COMPATIBLE
    assert config.api_key == PLACEHOLDER_KEY
    assert config.base_url == PLACEHOLDER_BASE_URL
    assert config.generation_model == "placeholder-generation-model"


def test_load_model_config_case_and_whitespace_insensitive(monkeypatch):
    _set_real_env(monkeypatch, GENUI_MODEL_PROVIDER="  OpenAI_Compatible  ")
    assert load_model_config().provider == PROVIDER_OPENAI_COMPATIBLE


def test_refinement_model_inherits_generation_model(monkeypatch):
    _set_real_env(monkeypatch, GENUI_REFINEMENT_MODEL=None)
    config = load_model_config()
    assert config.refinement_model == config.generation_model


def test_refinement_model_can_be_overridden(monkeypatch):
    _set_real_env(monkeypatch, GENUI_REFINEMENT_MODEL="placeholder-refinement-model")
    config = load_model_config()
    assert config.refinement_model == "placeholder-refinement-model"
    assert config.generation_model == "placeholder-generation-model"


@pytest.mark.parametrize(
    "missing",
    ["GENUI_LLM_API_KEY", "GENUI_LLM_BASE_URL", "GENUI_GENERATION_MODEL"],
)
def test_missing_required_configuration_raises(monkeypatch, missing):
    _set_real_env(monkeypatch, **{missing: None})
    with pytest.raises(ProviderConfigError) as exc:
        load_model_config()
    assert missing in str(exc.value)


def test_blank_required_value_treated_as_missing(monkeypatch):
    _set_real_env(monkeypatch, GENUI_LLM_API_KEY="   ")
    with pytest.raises(ProviderConfigError) as exc:
        load_model_config()
    assert "GENUI_LLM_API_KEY" in str(exc.value)


def test_missing_configuration_error_lists_all_missing_names(monkeypatch):
    _set_real_env(
        monkeypatch,
        GENUI_LLM_API_KEY=None,
        GENUI_LLM_BASE_URL=None,
        GENUI_GENERATION_MODEL=None,
    )
    with pytest.raises(ProviderConfigError) as exc:
        load_model_config()
    message = str(exc.value)
    assert "GENUI_LLM_API_KEY" in message
    assert "GENUI_LLM_BASE_URL" in message
    assert "GENUI_GENERATION_MODEL" in message


def test_missing_configuration_error_never_leaks_credentials(monkeypatch):
    _set_real_env(monkeypatch, GENUI_GENERATION_MODEL=None)
    with pytest.raises(ProviderConfigError) as exc:
        load_model_config()
    assert PLACEHOLDER_KEY not in str(exc.value)


def test_unknown_provider_raises_with_allowed_values(monkeypatch):
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "anthropic")
    with pytest.raises(ProviderConfigError) as exc:
        load_model_config()
    message = str(exc.value)
    assert "GENUI_MODEL_PROVIDER" in message
    assert PROVIDER_OPENAI_COMPATIBLE in message


def test_config_errors_are_runtime_error_subclass():
    """工厂层「raise RuntimeError」语义成立，同时是可捕获的具体异常类型（AC-10）。"""
    assert issubclass(ProviderConfigError, RuntimeError)
    assert issubclass(ProviderResponseError, RuntimeError)


# ============================================================
# create_async_client（AC-07）
# ============================================================


def test_create_async_client_from_config():
    config = ModelConfig(
        provider=PROVIDER_OPENAI_COMPATIBLE,
        api_key=PLACEHOLDER_KEY,
        base_url=PLACEHOLDER_BASE_URL,
        generation_model="placeholder-generation-model",
        refinement_model="placeholder-generation-model",
    )
    client = create_async_client(config)
    assert isinstance(client, AsyncOpenAI)
    assert client.max_retries == 0
    assert str(client.base_url).rstrip("/") == PLACEHOLDER_BASE_URL.rstrip("/")


def test_create_async_client_rejects_non_openai_compat_mode():
    """provider 非 openai_compatible 时被误调用 → 拒绝构造 SDK 客户端。"""
    with pytest.raises(ProviderConfigError):
        create_async_client(ModelConfig(provider="mock"))


def test_create_async_client_without_config_reads_env(monkeypatch):
    _set_real_env(monkeypatch)
    client = create_async_client()
    assert isinstance(client, AsyncOpenAI)


def test_create_async_client_default_mode_rejected(monkeypatch):
    """配置不完整时不带 config 调用 → 拒绝，绝不静默连真实端点。"""
    monkeypatch.delenv("GENUI_LLM_API_KEY", raising=False)
    with pytest.raises(ProviderConfigError):
        create_async_client()


# ============================================================
# extract_json_object（AC-30 / AC-31 / AC-32）
# ============================================================


def test_extract_json_object_valid():
    result = extract_json_object(_response('{"version": "0.1", "root": {}}'))
    assert result == {"version": "0.1", "root": {}}


def test_extract_json_object_preserves_unknown_fields():
    """不清洗、不补字段：原样交给确定性校验层裁决（信任边界在 validator）。"""
    result = extract_json_object(_response('{"version": "0.1", "evil": true}'))
    assert result == {"version": "0.1", "evil": True}


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        "",
        "   ",
        "\n\t ",
        '{"unclosed": ',
        '```json\n{"version": "0.1"}\n```',
        "[1, 2, 3]",
        '"a bare string"',
        "42",
        "null",
    ],
)
def test_extract_json_object_rejects_unusable_content(content):
    with pytest.raises(ProviderResponseError):
        extract_json_object(_response(content))


def test_extract_json_object_rejects_empty_choices():
    with pytest.raises(ProviderResponseError):
        extract_json_object(_response(None, with_choices=False))


def test_extract_json_object_rejects_missing_content():
    with pytest.raises(ProviderResponseError):
        extract_json_object(_response(None))


def test_extract_json_object_rejects_non_string_content():
    with pytest.raises(ProviderResponseError):
        extract_json_object(_response({"already": "parsed"}))


def test_extract_json_object_rejects_malformed_response_object():
    with pytest.raises(ProviderResponseError):
        extract_json_object(object())


def test_provider_response_error_message_is_sanitized():
    """固定文案：不插值模型输出 / 端点 / 凭证 / 路径（DD-12）。"""
    err = ProviderResponseError()
    assert str(err) == PROVIDER_RESPONSE_ERROR_MESSAGE
    lowered = str(err).lower()
    for leaked in ("api_key", "sk-", "http", "traceback", "/users/"):
        assert leaked not in lowered


# ============================================================
# 日志脱敏（AC-33 / AC-34 / AC-35）
# ============================================================


def test_log_provider_summary_excludes_credentials(caplog):
    config = ModelConfig(
        provider=PROVIDER_OPENAI_COMPATIBLE,
        api_key=PLACEHOLDER_KEY,
        base_url=PLACEHOLDER_BASE_URL,
        generation_model="placeholder-generation-model",
        refinement_model="placeholder-refinement-model",
    )
    with caplog.at_level(logging.INFO, logger="genui.llm"):
        log_provider_summary(config)
    text = caplog.text
    assert PROVIDER_OPENAI_COMPATIBLE in text
    assert "placeholder-generation-model" in text
    assert "placeholder-refinement-model" in text
    assert PLACEHOLDER_KEY not in text
    assert PLACEHOLDER_BASE_URL not in text


def test_log_llm_call_records_token_usage(caplog):
    usage = SimpleNamespace(prompt_tokens=123, completion_tokens=45)
    with caplog.at_level(logging.INFO, logger="genui.llm"):
        log_llm_call(
            kind="generation",
            model="placeholder-generation-model",
            response=_response('{"version": "0.1"}', usage=usage),
        )
    text = caplog.text
    assert "event=llm_call" in text
    assert "kind=generation" in text
    assert "prompt_tokens=123" in text
    assert "completion_tokens=45" in text


def test_log_llm_call_excludes_prompt_and_output(caplog):
    usage = SimpleNamespace(prompt_tokens=1, completion_tokens=2)
    secret_output = '{"version": "0.1", "root": {"id": "leaky-marker-node"}}'
    with caplog.at_level(logging.INFO, logger="genui.llm"):
        log_llm_call(
            kind="refinement",
            model="placeholder-refinement-model",
            response=_response(secret_output, usage=usage),
        )
    assert "leaky-marker-node" not in caplog.text


def test_log_llm_call_tolerates_missing_usage(caplog):
    with caplog.at_level(logging.INFO, logger="genui.llm"):
        log_llm_call(kind="generation", model="m", response=_response("{}"))
    assert "prompt_tokens=None" in caplog.text
    assert "completion_tokens=None" in caplog.text


def test_log_llm_call_tolerates_non_integer_usage(caplog):
    usage = SimpleNamespace(prompt_tokens="many", completion_tokens=None)
    with caplog.at_level(logging.INFO, logger="genui.llm"):
        log_llm_call(kind="generation", model="m", response=_response("{}", usage=usage))
    assert "prompt_tokens=None" in caplog.text


def test_log_llm_call_never_raises():
    """日志失败绝不影响业务结果。"""

    class Exploding:
        @property
        def usage(self):
            raise RuntimeError("boom")

    log_llm_call(kind="generation", model=None, response=Exploding())
