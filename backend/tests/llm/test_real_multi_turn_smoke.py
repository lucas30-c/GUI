"""真实模型多轮 smoke 测试 —— 显式 opt-in，默认 skip（Spec 009 DD-19 / AC-31）。

为什么把「模型是否理解相对指令」放在这里而不是必跑 AC：
「理解了吗」不是确定性断言。把它写成必跑测试只会制造随机红灯，并诱导后来者削弱断言。
可确定性保证的是**上下文确实被正确送到了模型**（由 tests/llm/test_history_prompts.py
逐条断言 messages 内容）；真实模型对相对指令的遵从度，只在人主动 opt-in 时才验证。

两级闸门与 tests/llm/test_real_smoke.py 完全一致：
1. `GENUI_RUN_REAL_LLM=1`（由 tests/conftest.py 的 real_llm_opt_in 夹具强制）；
2. `GENUI_MODEL_PROVIDER=openai_compatible` + 凭证三项齐备。
因此裸 `pytest` 在本文件上恒为 skip，零真实网络调用。
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
# 第一轮给出明确字面值 → 第二轮只给**相对指令**（不重复目标文案）。
# 若模型没有拿到上一轮上下文，「再短一点」在语义上无所指，通不过下面的长度断言。
FIRST_TEXT = "今日现磨手冲咖啡限时八折优惠中"
FIRST_INSTRUCTION = f"把文案改成「{FIRST_TEXT}」"
RELATIVE_INSTRUCTION = "在保持同样意思的前提下，把这句文案改得更短"

BASE_URL = "http://real-multi-turn-smoke"


@pytest.fixture
def config():
    try:
        loaded = load_model_config()
    except ProviderConfigError as exc:
        pytest.skip(f"credentials not configured: {exc}")
    if loaded.provider != PROVIDER_OPENAI_COMPATIBLE:
        pytest.skip(
            "credentials not configured: set GENUI_MODEL_PROVIDER=openai_compatible"
        )
    return loaded


@pytest.fixture
def app(config):
    return create_app()


def _new_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)


def _first_text_node_id(document: dict) -> str:
    stack = [document["root"]]
    while stack:
        node = stack.pop(0)
        if "text" in (node.get("props") or {}):
            return node["id"]
        stack = list(node.get("children") or []) + stack
    raise AssertionError("generated document contains no node with a text prop")


def _find_node(node: dict, node_id: str) -> dict | None:
    if node["id"] == node_id:
        return node
    for child in node.get("children") or []:
        found = _find_node(child, node_id)
        if found is not None:
            return found
    return None


def test_real_multi_turn_relative_instruction(app):
    """两轮真实精修：第二轮只给相对指令，仍需 200 + 非目标零变更 + 文案确实变短。"""

    async def run() -> None:
        async with _new_client(app) as client:
            generated = await client.post(
                "/api/v1/dsl/generate", json={"prompt": GENERATION_PROMPT}
            )
            assert generated.status_code == 200, generated.text
            document = generated.json()["document"]
            node_id = _first_text_node_id(document)

            first = await client.post(
                "/api/v1/dsl/refine",
                json={
                    "document": document,
                    "selectedNodeId": node_id,
                    "instruction": FIRST_INSTRUCTION,
                },
            )
            assert first.status_code == 200, first.text
            first_body = first.json()
            assert first_body["integrity"]["nonTargetNodesUnchanged"] is True
            first_props = _find_node(first_body["document"]["root"], node_id)["props"]

            second = await client.post(
                "/api/v1/dsl/refine",
                json={
                    "document": first_body["document"],
                    "selectedNodeId": node_id,
                    "instruction": RELATIVE_INSTRUCTION,
                    "history": [
                        {
                            "instruction": FIRST_INSTRUCTION,
                            "selectedNodeId": node_id,
                            "nodeType": _find_node(
                                first_body["document"]["root"], node_id
                            )["type"],
                            "patchProps": {"text": first_props["text"]},
                        }
                    ],
                },
            )
            assert second.status_code == 200, second.text
            second_body = second.json()
            assert second_body["success"] is True
            assert second_body["integrity"]["nonTargetNodesUnchanged"] is True
            assert second_body["integrity"]["selectedNodeId"] == node_id
            validate_dsl_document(second_body["document"])

            refined = _find_node(second_body["document"]["root"], node_id)["props"]
            assert len(refined["text"]) < len(first_props["text"]), refined["text"]

    asyncio.run(run())
