"""GenUI API 应用入口 — 最小 FastAPI 工厂"""

from fastapi import FastAPI

from genui_api.api.routes import router


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    application = FastAPI(
        title="GenUI API",
        version="0.1.0",
        description="GenUI 受控原型后端：DSL v0.1 校验接口",
    )
    application.include_router(router)
    return application


# 模块级应用实例，供 Uvicorn 导入
app = create_app()
