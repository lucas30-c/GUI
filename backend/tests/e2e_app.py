"""E2E 确定性回归专用应用（测试范围内，非生产入口）。

Real-Provider-only 下生产 app 只接真实模型；本模块为 Playwright 的确定性
回归 specs（generation-loop / golden-path / multi-turn-stability /
refinement-loop / style-refinement）注入测试替身，保持 UI 交互链路的
零模型回归门禁。真实模型浏览器验收由 e2e/complex-generation.spec.ts
走独立端口的生产 app 完成。

启动（playwright.config.ts 的 webServer 已封装）：
    PYTHONPATH=src:. .venv/bin/python -m uvicorn tests.e2e_app:app --port 8000
"""

from genui_api.main import create_app
from tests.doubles.generation import MockGenerationProvider
from tests.doubles.refinement import MockProvider

app = create_app(
    refinement_provider=MockProvider(),
    generation_provider=MockGenerationProvider(),
)
