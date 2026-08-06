"""真实模型 smoke 测试 —— 显式 opt-in，默认 skip（Spec 008 AC-36 / AC-37）。

两级闸门，缺任一级都不会发生真实调用：
1. `GENUI_RUN_REAL_LLM=1`（由 tests/conftest.py 的 real_llm_opt_in 夹具强制）。
   pytest 的 marker 只是分类标签，本身不会跳过任何测试——跳过靠那个夹具。
2. `GENUI_MODEL_PROVIDER=openai_compatible` + Key / BaseURL / Model 三项齐备。

因此裸 `pytest`（即使开发者 shell 里已 export 真实凭证）在本文件上恒为 skip。

本文件走**完整 HTTP API 链路**（`POST /api/v1/dsl/generate` → `POST /api/v1/dsl/refine`），
真实 Provider 由 `create_app()` 经环境变量自行装配——**不做任何 DI override**，
因此断言的是「真实模型能完成最终业务链路」这一端到端事实，而不只是 Provider 单体
可用。断言对象是**可通过性与指令遵从**（HTTP 200 + 确定性校验层放行 + 目标 prop 取到
指令给出的字面值 + 非目标零变更），不是文案质量：内容好不好是人的判断，能不能通过、
有没有照做才是可自动化的判断。
"""

import asyncio

import httpx
import pytest

from genui_api.contracts.validation import validate_dsl_document
from genui_api.llm.client import (
    PROVIDER_OPENAI_COMPATIBLE,
    ProviderConfigError,
    load_model_config,
)
from genui_api.main import create_app

pytestmark = pytest.mark.real_llm

GENERATION_PROMPT = "一个简单的咖啡店着陆页"
# 纯文案修改：Patch v0.1 的唯一 op 是 update_props 且 style 不可修改，因此 smoke 的精修
# 指令必须落在**目标节点确实存在的可写文本 prop** 上，否则失败源于指令与协议不匹配，
# 而不是真实模型不可用——那样的红灯没有诊断价值。
REFINED_TEXT = "今日现磨咖啡"
REFINEMENT_INSTRUCTION = f"把文案改成「{REFINED_TEXT}」"

BASE_URL = "http://real-smoke"


@pytest.fixture
def config():
    """真实模型配置；未切到 openai_compatible 或凭证不全时跳过（第二道闸门）。"""
    try:
        loaded = load_model_config()
    except ProviderConfigError as exc:
        pytest.skip(f"credentials not configured: {exc}")
    if loaded.provider != PROVIDER_OPENAI_COMPATIBLE:
        pytest.skip(
            "credentials not configured: "
            "set GENUI_MODEL_PROVIDER=openai_compatible"
        )
    return loaded


@pytest.fixture
def app(config):
    """真实 Provider 由环境变量装配；不注入任何 stub，不覆盖任何依赖。"""
    return create_app()


def _new_client(app) -> httpx.AsyncClient:
    """ASGI transport：不经真实端口，但完整穿过路由、请求校验与 Pipeline。"""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=BASE_URL
    )


def _first_text_node_id(document: dict) -> str:
    """按先序遍历取第一个 props 含 `text` 的节点 ID（Heading / Text / Button 之类）。

    不能取「第一个非 Page 节点」：那通常是 `Section`，它没有 `text` prop，纯文案指令
    落在它身上必然无从下手。目标节点必须自身可写文本，精修才是可判定的。
    """
    stack = [document["root"]]
    while stack:
        node = stack.pop(0)
        if "text" in (node.get("props") or {}):
            return node["id"]
        stack = list(node.get("children") or []) + stack
    raise AssertionError("generated document contains no node with a text prop")


def _find_node(node: dict, node_id: str) -> dict | None:
    """在文档中按 ID 定位节点，用于断言精修后的 props 实际值。"""
    if node["id"] == node_id:
        return node
    for child in node.get("children") or []:
        found = _find_node(child, node_id)
        if found is not None:
            return found
    return None


async def _generate(client: httpx.AsyncClient) -> dict:
    """真实模型初稿：HTTP 200 + success + document 通过 DSL 校验器。"""
    response = await client.post(
        "/api/v1/dsl/generate", json={"prompt": GENERATION_PROMPT}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    document = body["document"]
    validated = validate_dsl_document(document)
    assert validated.version == "0.1"
    assert validated.root.type == "Page"
    return document


def test_real_generation_via_http_api(app):
    """真实模型初稿必须经 /generate 端点返回 200，且文档通过与 Mock 相同的校验器。"""

    async def run() -> None:
        async with _new_client(app) as client:
            await _generate(client)

    asyncio.run(run())


def test_real_refinement_via_http_api(app):
    """真实模型精修必须经 /refine 端点返回 200，目标文案落地且非目标节点零变更可证明。"""

    async def run() -> None:
        async with _new_client(app) as client:
            document = await _generate(client)
            selected_node_id = _first_text_node_id(document)

            response = await client.post(
                "/api/v1/dsl/refine",
                json={
                    "document": document,
                    "selectedNodeId": selected_node_id,
                    "instruction": REFINEMENT_INSTRUCTION,
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["success"] is True

            target_node = _find_node(body["document"]["root"], selected_node_id)
            assert target_node is not None, selected_node_id
            assert target_node["props"]["text"] == REFINED_TEXT

            assert body["integrity"]["nonTargetNodesUnchanged"] is True
            assert body["integrity"]["selectedNodeId"] == selected_node_id
            validate_dsl_document(body["document"])

    asyncio.run(run())
