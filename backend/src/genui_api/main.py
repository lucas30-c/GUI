"""GenUI API 应用入口 — 最小 FastAPI 工厂"""
from __future__ import annotations

from fastapi import FastAPI

from genui_api.api.routes import get_generation_provider, get_provider, router
from genui_api.generation.base import GenerationProvider
from genui_api.provider.base import RefinementProvider


def create_app(
    refinement_provider: RefinementProvider | None = None,
    generation_provider: GenerationProvider | None = None,
) -> FastAPI:
    """创建 FastAPI 应用实例。"""
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


# 模块级应用实例，供 Uvicorn 导入
app = create_app()
