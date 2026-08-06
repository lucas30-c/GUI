"""GenUI API 应用入口 — 最小 FastAPI 工厂"""
from __future__ import annotations

from fastapi import FastAPI

from genui_api.api.routes import get_generation_provider, get_provider, router
from genui_api.generation.base import GenerationProvider
from genui_api.llm.client import load_model_config, log_provider_summary
from genui_api.provider.base import RefinementProvider


def create_app(
    refinement_provider: RefinementProvider | None = None,
    generation_provider: GenerationProvider | None = None,
) -> FastAPI:
    """创建 FastAPI 应用实例。"""
    # 条件式启动期校验（DD-5）：谁没被显式注入，才校验谁的配置。
    # 两侧都显式注入时完全不读取 LLM 环境变量——显式注入的 Provider 自带候选来源，
    # 此时要求真实凭证是纯粹的伪依赖。
    if refinement_provider is None or generation_provider is None:
        config = load_model_config()  # 非法配置 → 启动失败（fail fast）
        log_provider_summary(config)  # INFO：provider + 两个模型名，绝不含 Key

    application = FastAPI(
        title="GenUI API",
        version="0.1.0",
        description="GenUI 受控原型后端：DSL v0.1 校验、局部精修与初稿生成接口",
    )

    if refinement_provider is not None:
        application.dependency_overrides[get_provider] = (
            lambda: refinement_provider
        )

    if generation_provider is not None:
        application.dependency_overrides[get_generation_provider] = (
            lambda: generation_provider
        )

    application.include_router(router)
    return application


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """惰性导出模块级 `app`，供 `uvicorn genui_api.main:app` 使用（PEP 562）。

    `create_app()` 自 M4-02 起在启动期校验模型配置（fail fast）。若在导入时就构造
    实例，则「real 模式 + 无凭证」下连 `from genui_api.main import create_app`
    都会失败——而显式注入 Provider 的调用方本不需要凭证（DD-5）。惰性化后 fail fast
    仍在 Uvicorn 解析 `app` 时如期发生，只是不再波及模块导入本身。
    """
    global _app
    if name != "app":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if _app is None:
        _app = create_app()
    return _app
