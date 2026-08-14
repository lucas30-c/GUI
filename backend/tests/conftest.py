"""全局测试夹具 — 保证默认 pytest 运行零真实模型调用（Spec 008 DD-16 / AC-37）。

Real-Provider-only 下的两条守卫：
1. 未标记 real_llm 的测试，把模型环境变量统一改写为**离线占位配置**
   （openai_compatible + 不可达端点 + 占位 Key）。这样 `create_app()` 无注入
   也能通过启动期配置校验（Provider 只被实例化、不会发起任何真实请求），
   同时无论宿主 shell 里 export 了什么真实凭证，裸 `pytest` 都不可能触达
   真实端点——占位值覆盖了宿主值。
2. 标记 real_llm 的测试必须显式设置 GENUI_RUN_REAL_LLM=1 才执行。
   pytest 的 marker 本身只是分类标签，不会让任何测试跳过——跳过必须由本文件实现。
"""

import os

import pytest

# llm.client 读取的 5 个模型配置变量（GENUI_RUN_REAL_LLM 不在其中，它只是测试开关）
_MODEL_ENV_VARS = (
    "GENUI_MODEL_PROVIDER",
    "GENUI_LLM_API_KEY",
    "GENUI_LLM_BASE_URL",
    "GENUI_GENERATION_MODEL",
    "GENUI_REFINEMENT_MODEL",
)

_OPT_IN_ENV_VAR = "GENUI_RUN_REAL_LLM"

# 离线占位配置：满足 openai_compatible 的完整性校验，但端点不可达、Key 为占位符。
# 任何真正发起网络请求的路径都会立刻失败，从而保证「零真实模型调用」。
_OFFLINE_PLACEHOLDER_ENV = {
    "GENUI_MODEL_PROVIDER": "openai_compatible",
    "GENUI_LLM_API_KEY": "<TEST_PLACEHOLDER_KEY>",
    "GENUI_LLM_BASE_URL": "https://offline.invalid/v1",
    "GENUI_GENERATION_MODEL": "offline-placeholder-model",
}


@pytest.fixture(autouse=True)
def isolate_model_env(request, monkeypatch):
    """把宿主环境的模型配置改写为离线占位值，使非 real_llm 测试绝不触达真实端点。

    测试内部仍可用 monkeypatch.setenv / delenv 显式构造配置场景（在本夹具之后生效）。
    """
    if request.node.get_closest_marker("real_llm") is not None:
        return
    for name in _MODEL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in _OFFLINE_PLACEHOLDER_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(autouse=True)
def real_llm_opt_in(request):
    """real_llm 测试的显式 opt-in 闸门：未设置 GENUI_RUN_REAL_LLM=1 则跳过。"""
    if request.node.get_closest_marker("real_llm") is None:
        return
    if os.environ.get(_OPT_IN_ENV_VAR, "").strip() != "1":
        pytest.skip(
            "explicit opt-in not enabled: "
            f"set {_OPT_IN_ENV_VAR}=1 to run real model smoke tests"
        )
