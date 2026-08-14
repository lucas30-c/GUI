"""Provider 选择与配置装配测试 — Real-Provider-only、DI override 优先、启动期校验。

Real-Provider-only（Owner 决策）：生产链路只接受 GENUI_MODEL_PROVIDER=
openai_compatible；mock 不再是运行时模式，测试替身只能经 create_app 显式注入。
全程离线：真实 Provider 只被实例化，不发起任何请求。
"""

import importlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from genui_api.api.routes import get_generation_provider, get_provider
from genui_api.generation.openai_compat_provider import OpenAICompatGenerationProvider
from genui_api.llm.client import ProviderConfigError
from genui_api.main import create_app
from genui_api.provider.openai_compat_provider import OpenAICompatRefinementProvider
from tests.doubles.generation import MockGenerationProvider
from tests.doubles.refinement import MockProvider

PLACEHOLDER_KEY = "test-api-key-placeholder"
PLACEHOLDER_BASE_URL = "https://example.invalid/v1"

GOLD_DOCUMENT = {
    "version": "0.1",
    "root": {
        "id": "page",
        "type": "Page",
        "props": {"title": "Demo"},
        "children": [
            {
                "id": "hero.title",
                "type": "Heading",
                "props": {"text": "欢迎", "level": 1},
            }
        ],
    },
}


def _set_real_env(monkeypatch, **overrides):
    values = {
        "GENUI_MODEL_PROVIDER": "openai_compatible",
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


class RecordingGenerationProvider:
    def __init__(self):
        self.calls: list[str] = []

    async def generate_draft(self, prompt: str) -> dict:
        self.calls.append(prompt)
        return GOLD_DOCUMENT


class RecordingRefinementProvider:
    def __init__(self):
        self.calls: list[str] = []

    async def generate_patch(self, context) -> dict:
        self.calls.append(context.selected_node_id)
        return {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": context.selected_node_id,
                    "props": {"text": "已更新"},
                }
            ],
        }


# ============================================================
# Real-Provider-only：默认与 mock 值都不再是合法运行时模式
# ============================================================


def test_default_without_env_fails_fast_not_mock(monkeypatch):
    """未设置 GENUI_MODEL_PROVIDER 时 fail fast，绝不回退 Mock。"""
    monkeypatch.delenv("GENUI_MODEL_PROVIDER", raising=False)
    with pytest.raises(ProviderConfigError):
        get_provider()
    with pytest.raises(ProviderConfigError):
        get_generation_provider()


@pytest.mark.parametrize("raw", ["mock", "  mock  ", "MOCK"])
def test_mock_value_is_rejected_as_runtime_mode(monkeypatch, raw):
    """mock 不再是运行时模式：显式设置也被拒绝（测试替身只能注入）。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", raw)
    with pytest.raises(ProviderConfigError):
        get_generation_provider()
    with pytest.raises(ProviderConfigError):
        get_provider()


def test_rejected_config_error_mentions_env_var(monkeypatch):
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "mock")
    with pytest.raises(ProviderConfigError) as exc:
        get_generation_provider()
    assert "GENUI_MODEL_PROVIDER" in str(exc.value)


def test_default_app_requires_real_config(monkeypatch):
    """未注入 Provider 时，create_app 要求真实配置，否则启动失败（fail fast）。"""
    monkeypatch.delenv("GENUI_MODEL_PROVIDER", raising=False)
    with pytest.raises(ProviderConfigError):
        create_app()


def test_injected_mock_doubles_still_serve_generation():
    """测试替身经显式注入仍可用——但这是测试装配，不是生产默认。"""
    client = TestClient(
        create_app(
            refinement_provider=MockProvider(),
            generation_provider=MockGenerationProvider(),
        )
    )
    response = client.post(
        "/api/v1/dsl/generate",
        content=json.dumps({"prompt": "做一个咖啡店落地页"}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_injected_mock_generation_remains_deterministic():
    """同一 prompt 两次调用得到完全相同的文档（注入替身的确定性）。"""
    client = TestClient(
        create_app(
            refinement_provider=MockProvider(),
            generation_provider=MockGenerationProvider(),
        )
    )
    payload = json.dumps({"prompt": "做一个咖啡店落地页"})
    headers = {"Content-Type": "application/json"}
    first = client.post("/api/v1/dsl/generate", content=payload, headers=headers)
    second = client.post("/api/v1/dsl/generate", content=payload, headers=headers)
    assert first.json()["document"] == second.json()["document"]


# ============================================================
# openai_compatible → 真实 Provider（AC-02）
# ============================================================


def test_openai_compatible_selects_real_providers(monkeypatch):
    _set_real_env(monkeypatch)
    assert isinstance(get_generation_provider(), OpenAICompatGenerationProvider)
    assert isinstance(get_provider(), OpenAICompatRefinementProvider)


def test_openai_compatible_selection_makes_no_network_call(monkeypatch):
    """选择真实 Provider 只是实例化：不建连接、不发请求。"""
    _set_real_env(monkeypatch)
    provider = get_generation_provider()
    assert isinstance(provider, OpenAICompatGenerationProvider)


# ============================================================
# 缺失/非法配置 → RuntimeError（AC-09 / AC-10 / AC-11）
# ============================================================


@pytest.mark.parametrize(
    "missing",
    ["GENUI_LLM_API_KEY", "GENUI_LLM_BASE_URL", "GENUI_GENERATION_MODEL"],
)
def test_missing_configuration_raises_runtime_error(monkeypatch, missing):
    _set_real_env(monkeypatch, **{missing: None})
    with pytest.raises(RuntimeError) as exc:
        get_generation_provider()
    assert missing in str(exc.value)

    with pytest.raises(RuntimeError):
        get_provider()


def test_unknown_provider_value_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "gemini")
    for factory in (get_provider, get_generation_provider):
        with pytest.raises(RuntimeError) as exc:
            factory()
        assert "GENUI_MODEL_PROVIDER" in str(exc.value)


def test_configuration_error_is_provider_config_error(monkeypatch):
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "gemini")
    with pytest.raises(ProviderConfigError):
        get_generation_provider()


def test_startup_fails_fast_on_invalid_configuration(monkeypatch):
    """非法配置在 create_app 阶段即失败，不留到首个请求（AC-11）。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "gemini")
    with pytest.raises(RuntimeError):
        create_app()


def test_startup_fails_fast_on_missing_credentials(monkeypatch):
    _set_real_env(monkeypatch, GENUI_LLM_API_KEY=None)
    with pytest.raises(RuntimeError):
        create_app()


def test_configuration_error_never_leaks_key(monkeypatch):
    _set_real_env(monkeypatch, GENUI_GENERATION_MODEL=None)
    with pytest.raises(RuntimeError) as exc:
        create_app()
    assert PLACEHOLDER_KEY not in str(exc.value)


# ============================================================
# DI override 优先于环境变量（AC-39 / AC-40）
# ============================================================


def test_injected_providers_override_env_selection(monkeypatch):
    _set_real_env(monkeypatch)
    generation = RecordingGenerationProvider()
    refinement = RecordingRefinementProvider()
    app = create_app(refinement_provider=refinement, generation_provider=generation)

    client = TestClient(app)
    response = client.post(
        "/api/v1/dsl/generate",
        content=json.dumps({"prompt": "做一个落地页"}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert generation.calls == ["做一个落地页"]


def test_both_injected_skips_llm_config_entirely(monkeypatch):
    """两侧都显式注入时完全不读 LLM 配置：缺凭证也不该阻塞（DD-5）。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.delenv("GENUI_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GENUI_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("GENUI_GENERATION_MODEL", raising=False)

    app = create_app(
        refinement_provider=RecordingRefinementProvider(),
        generation_provider=RecordingGenerationProvider(),
    )
    client = TestClient(app)
    assert client.get("/health").status_code == 200


def test_partial_injection_still_validates_the_other_side(monkeypatch):
    """只注入一侧时，另一侧仍需真实配置——否则首个请求才炸更难排查。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.delenv("GENUI_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GENUI_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("GENUI_GENERATION_MODEL", raising=False)

    with pytest.raises(RuntimeError):
        create_app(generation_provider=RecordingGenerationProvider())


def test_injected_refinement_provider_is_used_end_to_end(monkeypatch):
    _set_real_env(monkeypatch)
    refinement = RecordingRefinementProvider()
    app = create_app(
        refinement_provider=refinement,
        generation_provider=RecordingGenerationProvider(),
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/dsl/refine",
        content=json.dumps(
            {
                "document": GOLD_DOCUMENT,
                "selectedNodeId": "hero.title",
                "instruction": "把标题文案改一下",
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    assert refinement.calls == ["hero.title"]
    assert response.json()["integrity"]["nonTargetNodesUnchanged"] is True


def test_injection_and_env_selection_coexist(monkeypatch):
    """显式注入与真实 env 配置两条装配路径共存，互不干扰。"""
    injected_app = create_app(
        refinement_provider=RecordingRefinementProvider(),
        generation_provider=RecordingGenerationProvider(),
    )
    assert TestClient(injected_app).get("/health").status_code == 200

    _set_real_env(monkeypatch)
    assert isinstance(get_generation_provider(), OpenAICompatGenerationProvider)
    assert isinstance(get_provider(), OpenAICompatRefinementProvider)


# --- 模块级 app 入口点（惰性）---------------------------------------------------
# create_app() 自 M4-02 起在启动期校验配置。模块级实例若在导入时构造，会让
# 「real 模式 + 无凭证」下的 `from genui_api.main import create_app` 直接失败，
# 而显式注入 Provider 的调用方本不需要凭证（DD-5）。故 app 惰性化，以下用例锁定该行为。


def test_importing_main_does_not_validate_config(monkeypatch):
    """导入 main 模块本身不触发配置校验：real 模式缺凭证也能导入工厂（DD-5）。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "openai_compatible")
    for name in ("GENUI_LLM_API_KEY", "GENUI_LLM_BASE_URL", "GENUI_GENERATION_MODEL"):
        monkeypatch.delenv(name, raising=False)

    module = importlib.reload(importlib.import_module("genui_api.main"))

    # 导入成功即证明无 eager 校验；显式注入两侧后仍可正常建应用。
    app = module.create_app(
        refinement_provider=RecordingRefinementProvider(),
        generation_provider=RecordingGenerationProvider(),
    )
    assert TestClient(app).get("/health").status_code == 200


def test_module_level_app_resolves_and_is_cached(monkeypatch):
    """`uvicorn genui_api.main:app` 的入口点仍然可解析，且重复访问返回同一实例。"""
    _set_real_env(monkeypatch)
    module = importlib.reload(importlib.import_module("genui_api.main"))

    app = module.app
    assert isinstance(app, FastAPI)
    assert module.app is app, "重复解析 app 不应重建应用"
    assert TestClient(app).get("/health").status_code == 200


def test_module_level_app_still_fails_fast_on_invalid_config(monkeypatch):
    """惰性化未削弱 fail fast：解析 app 时非法配置仍抛 ProviderConfigError（AC-11）。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "openai_compatible")
    for name in ("GENUI_LLM_API_KEY", "GENUI_LLM_BASE_URL", "GENUI_GENERATION_MODEL"):
        monkeypatch.delenv(name, raising=False)
    module = importlib.reload(importlib.import_module("genui_api.main"))

    with pytest.raises(ProviderConfigError) as excinfo:
        module.app

    assert "GENUI_LLM_API_KEY" in str(excinfo.value)


def test_main_module_rejects_unknown_attribute(monkeypatch):
    """惰性 __getattr__ 只暴露 app，其余属性仍按常规抛 AttributeError。"""
    _set_real_env(monkeypatch)
    module = importlib.reload(importlib.import_module("genui_api.main"))

    with pytest.raises(AttributeError):
        module.no_such_attribute
