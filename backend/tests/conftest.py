"""全局测试夹具 — 保证默认 pytest 运行零真实模型调用（Spec 008 DD-16 / AC-37）。

两条守卫：
1. 未标记 real_llm 的测试一律被剥离全部模型环境变量。即使开发者 shell 里已经
   export 了真实凭证，裸 `pytest` 也不可能走到真实 Provider 分支。
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


@pytest.fixture(autouse=True)
def isolate_model_env(request, monkeypatch):
    """剥离宿主环境的模型配置，使非 real_llm 测试始终以 mock 默认态运行。

    测试内部仍可用 monkeypatch.setenv 显式构造配置场景（在本夹具之后生效）。
    """
    if request.node.get_closest_marker("real_llm") is not None:
        return
    for name in _MODEL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


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
