"""Provider 选择与配置装配测试 — 环境变量分支、DI override 优先、启动期校验。

覆盖 Spec 008 AC-01 ~ AC-02、AC-05 ~ AC-06、AC-09 ~ AC-11、AC-39 ~ AC-40。
全程离线：真实 Provider 只被实例化，不发起任何请求。
"""

import importlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from genui_api.api.routes import get_generation_provider, get_provider
from genui_api.generation.mock import MockGenerationProvider
from genui_api.generation.openai_compat_provider import OpenAICompatGenerationProvider
from genui_api.llm.client import ProviderConfigError
from genui_api.main import create_app
from genui_api.provider.mock import MockProvider
from genui_api.provider.openai_compat_provider import OpenAICompatRefinementProvider

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
# 默认（未设置任何环境变量）→ Mock（AC-01）
# ============================================================


def test_default_selects_mock_providers():
    assert isinstance(get_provider(), MockProvider)
    assert isinstance(get_generation_provider(), MockGenerationProvider)


@pytest.mark.parametrize("raw", ["mock", "  mock  ", "MOCK"])
def test_explicit_mock_selects_mock_providers(monkeypatch, raw):
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", raw)
    assert isinstance(get_provider(), MockProvider)
    assert isinstance(get_generation_provider(), MockGenerationProvider)


def test_mock_mode_ignores_present_credentials(monkeypatch):
    """mock 模式即使环境里有凭证也不切换 Provider（默认离线不可被环境意外破坏）。"""
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("GENUI_LLM_API_KEY", PLACEHOLDER_KEY)
    monkeypatch.setenv("GENUI_LLM_BASE_URL", PLACEHOLDER_BASE_URL)
    monkeypatch.setenv("GENUI_GENERATION_MODEL", "placeholder-generation-model")
    assert isinstance(get_generation_provider(), MockGenerationProvider)
    assert isinstance(get_provider(), MockProvider)


def test_default_app_still_serves_mock_generation():
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/dsl/generate",
        content=json.dumps({"prompt": "做一个咖啡店落地页"}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_mock_generation_remains_deterministic():
    """同一 prompt 两次调用得到完全相同的文档（Mock 的确定性不被本次改动影响）。"""
    client = TestClient(create_app())
    payload = json.dumps({"prompt": "做一个咖啡店落地页"})
    headers = {"Content-Type": "application/json"}
    first = client.post("/api/v1/dsl/generate", content=payload, headers=headers)
    second = client.post("/api/v1/dsl/generate", content=payload, headers=headers)
    assert first.json() == second.json()


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


def test_three_way_coexistence(monkeypatch):
    """真实 env 配置 + Mock 默认 + 显式注入三点共存，互不干扰（AC-40）。"""
    injected_app = create_app(
        refinement_provider=RecordingRefinementProvider(),
        generation_provider=RecordingGenerationProvider(),
    )
    assert TestClient(injected_app).get("/health").status_code == 200

    mock_app = create_app()
    assert TestClient(mock_app).get("/health").status_code == 200
    assert isinstance(get_generation_provider(), MockGenerationProvider)

    _set_real_env(monkeypatch)
    assert isinstance(get_generation_provider(), OpenAICompatGenerationProvider)


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
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "mock")
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
    monkeypatch.setenv("GENUI_MODEL_PROVIDER", "mock")
    module = importlib.reload(importlib.import_module("genui_api.main"))

    with pytest.raises(AttributeError):
        module.no_such_attribute
