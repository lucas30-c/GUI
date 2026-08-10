"""真实模型**多轮 style** smoke 测试 —— 显式 opt-in，默认 skip（Spec 010 §19.1 / AC-40）。

运行：`GENUI_RUN_REAL_LLM=1 pytest tests/llm/test_real_style_smoke.py -v`
未设置 `GENUI_RUN_REAL_LLM=1` 或凭证缺失时恒为 `skipped`（报告为
`NOT RUN — credentials not configured`，**严禁**记为 PASS）。

本文件证明的性质：**真实模型路径下多轮 style 精修的受控性质与 Mock 路径完全一致**。
Round 1 给出绝对指令「把标题改成红色」，Round 2 只给相对指令「再大一点」——
若 `currentStyle` 不是从上一轮**已确认的 Document** 派生（DD-12），
「再大一点」在语义上无所指，模型无从换算出新字号。

不作断言的部分（延续 Spec 008 DD-13 / Spec 009 DD-19）：具体色值、字号增幅、
模型是否额外给出其他白名单字段。只要落在白名单与值域内、边界与完整性成立即视为通过。

三级闸门与 tests/llm/test_real_smoke.py 完全一致：
1. `GENUI_RUN_REAL_LLM=1`（由 tests/conftest.py 的 real_llm_opt_in 夹具强制）；
2. `GENUI_MODEL_PROVIDER=openai_compatible` + 凭证三项齐备；
3. 候选 Patch **全部来自真实模型** —— 本文件不注入任何 stub / mock 候选。
因此裸 `pytest` 在本文件上恒为 skip，零真实网络调用。
"""

import asyncio
import copy
import json
import pathlib
import re

import httpx
import pytest

from genui_api.contracts.dsl import Style
from genui_api.contracts.validation import validate_dsl_document
from genui_api.llm.client import (
    PROVIDER_OPENAI_COMPATIBLE,
    ProviderConfigError,
    load_model_config,
)
from genui_api.main import create_app
from genui_api.patch.apply import apply_patch
from genui_api.provider.base import RefinementContext
from genui_api.provider.openai_compat_provider import OpenAICompatRefinementProvider

pytestmark = pytest.mark.real_llm

BASE_URL = "http://real-style-smoke"

# 目标节点：Gold Case 的 hero.title —— Heading，且带**确定的初始 style**
# （fontSize / fontWeight / color 三键齐备），因此「改成红色」与「再大一点」都有确定基线。
TARGET_NODE_ID = "hero.title"
INITIAL_COLOR = "#2c1810"
INITIAL_FONT_SIZE = "48px"

ROUND_1_INSTRUCTION = "把标题改成红色"
ROUND_2_INSTRUCTION = "再大一点"

_GOLD_CASE_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "examples"
    / "dsl"
    / "coffee-shop-landing.json"
)

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3,8})$")
_SIZE_RE = re.compile(r"^\d+(?:\.\d+)?(?:px|rem|em|%)$")


class _ContextSpy:
    """透明代理 Provider：候选**完全来自真实模型**，只额外记录受控上下文。

    这不是 mock —— `generate_patch` 原样转发给 `OpenAICompatRefinementProvider`，
    真实网络调用与真实候选一个不少。记录上下文的唯一理由是
    「`currentStyle` 来自已确认 Document 而非 history 回灌」（DD-12）
    这一性质在 HTTP 响应体中不可观测，只能在 Pipeline → Provider 的边界上取证。
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.contexts: list[RefinementContext] = []

    async def generate_patch(self, context: RefinementContext) -> dict:
        # 深拷贝：后续断言看到的必须是**调用当时**的上下文快照
        self.contexts.append(copy.deepcopy(context))
        return await self._inner.generate_patch(context)


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
def spy(config):
    return _ContextSpy(OpenAICompatRefinementProvider())


@pytest.fixture
def app(spy):
    return create_app(refinement_provider=spy)


@pytest.fixture
def gold_case() -> dict:
    return json.loads(_GOLD_CASE_PATH.read_text(encoding="utf-8"))


def _new_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)


def _find_node(node: dict, node_id: str) -> dict | None:
    if node["id"] == node_id:
        return node
    for child in node.get("children") or []:
        found = _find_node(child, node_id)
        if found is not None:
            return found
    return None


def _drop_none(mapping: dict | None) -> dict:
    """丢弃值为 None 的键。

    响应文档是 `model_dump(by_alias=True)` 的产物，未设置的白名单字段会显式带上
    `None`；源文档（Gold Case JSON）只写出已生效字段。归一化后两侧才可直接比较，
    且比较口径与上下文派生一致：「未设置」与「设为 null」都等于「该键不存在」。
    """
    if not mapping:
        return {}
    return {key: value for key, value in mapping.items() if value is not None}


def _shallow(node: dict) -> dict:
    """节点自身的可比较视图：不含子树内容，只含子节点 ID 序列。

    这样逐节点比较才不会因为「祖先包含目标节点」而把目标的合法变更算成非目标变更。
    """
    return {
        "type": node["type"],
        "props": _drop_none(node.get("props")),
        "style": _drop_none(node.get("style")),
        "children": [child["id"] for child in (node.get("children") or [])],
    }


def _shallow_map(root: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        out[node["id"]] = _shallow(node)
        for child in node.get("children") or []:
            stack.append(child)
    return out


def _assert_non_target_unchanged(before: dict, after: dict, target_id: str) -> None:
    """逐节点深等比较：除目标节点外，节点集合与每个节点的 props/style/子序列必须全等。"""
    before_map = _shallow_map(before["root"])
    after_map = _shallow_map(after["root"])
    assert set(before_map) == set(after_map), sorted(set(before_map) ^ set(after_map))
    for node_id, snapshot in before_map.items():
        if node_id == target_id:
            continue
        assert after_map[node_id] == snapshot, (node_id, snapshot, after_map[node_id])


def _style_ops(patch: dict, target_id: str) -> list[dict]:
    return [
        op
        for op in patch["operations"]
        if op.get("op") == "update_style" and op.get("targetNodeId") == target_id
    ]


def _merged_style(patch: dict, target_id: str) -> dict:
    """按数组顺序浅合并目标节点的 update_style —— 与前端 derivePatchStyle 同构。"""
    merged: dict = {}
    for op in _style_ops(patch, target_id):
        merged.update(op["style"])
    return merged


def _merged_props(patch: dict, target_id: str) -> dict:
    merged: dict = {}
    for op in patch["operations"]:
        if op.get("op") != "update_props" or op.get("targetNodeId") != target_id:
            continue
        merged.update(op["props"])
    return merged


def _assert_in_color_domain(value: str) -> None:
    """值必须落在 DSL 颜色值域内（Style 模型是唯一判据，本测试不复制其正则）。"""
    Style(color=value)


def _assert_in_size_domain(value: str) -> None:
    Style(fontSize=value)


def _assert_reddish(value: str) -> None:
    """「红色系」的最小可判定口径：hex 且红通道严格大于绿、蓝两通道。

    不断言具体色值（Spec 008 DD-13）—— 只断言模型确实朝「红」的方向走，
    而不是返回了一个合法但与指令无关的颜色。
    """
    assert _HEX_COLOR_RE.match(value), value
    digits = value[1:]
    if len(digits) == 3:
        red, green, blue = (int(char * 2, 16) for char in digits)
    else:
        assert len(digits) >= 6, value
        red, green, blue = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    assert red > green and red > blue, value


def test_real_multi_turn_style_relative_followup(app, spy, gold_case):
    """两轮真实 style 精修：Round 1 绝对指令改色，Round 2 相对指令改大。

    Round 2 的一切都建立在「Document 是 style 的唯一事实来源」之上：
    `currentStyle` 由 Pipeline 从 Round 1 **已确认的返回文档**派生，
    既不来自模型上一轮的输出原文，也不来自 history 里的 `patchStyle` 回灌。
    """

    async def run() -> None:
        async with _new_client(app) as client:
            # === Round 1：绝对指令「把标题改成红色」===
            source = copy.deepcopy(gold_case)
            first = await client.post(
                "/api/v1/dsl/refine",
                json={
                    "document": source,
                    "selectedNodeId": TARGET_NODE_ID,
                    "instruction": ROUND_1_INSTRUCTION,
                },
            )
            assert first.status_code == 200, first.text
            first_body = first.json()
            assert first_body["success"] is True
            assert first_body["integrity"]["nonTargetNodesUnchanged"] is True
            assert first_body["integrity"]["selectedNodeId"] == TARGET_NODE_ID

            first_doc = first_body["document"]
            validate_dsl_document(first_doc)
            _assert_non_target_unchanged(gold_case, first_doc, TARGET_NODE_ID)

            # 至少一条落在目标节点上的 update_style，且改的是 color
            assert _style_ops(first_body["patch"], TARGET_NODE_ID), first_body["patch"]
            assert "color" in _merged_style(first_body["patch"], TARGET_NODE_ID)

            first_node = _find_node(first_doc["root"], TARGET_NODE_ID)
            assert first_node is not None
            round_1_color = first_node["style"]["color"]
            assert round_1_color != INITIAL_COLOR, round_1_color
            _assert_in_color_domain(round_1_color)
            _assert_reddish(round_1_color)
            # 未提及的键保持原值（浅合并语义）
            assert first_node["style"]["fontSize"] == INITIAL_FONT_SIZE
            # Document 是事实来源：返回文档 == 系统把候选应用到副本后的结果
            assert first_doc == apply_patch(source, first_body["patch"]).model_dump(
                mode="json", by_alias=True
            )
            # Round 1 的上下文里 currentStyle 就是 Gold Case 的初始 style
            assert spy.contexts[0].selected_node_style["color"] == INITIAL_COLOR
            assert spy.contexts[0].selected_node_style["fontSize"] == INITIAL_FONT_SIZE

            # === Round 2：同一节点，只给相对指令「再大一点」===
            # history 里的 ConfirmedTurn 由 Round 1 的**已校验 patch** 确定性派生
            round_1_turn = {
                "instruction": ROUND_1_INSTRUCTION,
                "selectedNodeId": TARGET_NODE_ID,
                "nodeType": first_node["type"],
                "patchProps": _merged_props(first_body["patch"], TARGET_NODE_ID),
                "patchStyle": _merged_style(first_body["patch"], TARGET_NODE_ID),
            }
            assert round_1_turn["patchStyle"]["color"] == round_1_color

            second = await client.post(
                "/api/v1/dsl/refine",
                json={
                    "document": first_doc,
                    "selectedNodeId": TARGET_NODE_ID,
                    "instruction": ROUND_2_INSTRUCTION,
                    "history": [round_1_turn],
                },
            )
            assert second.status_code == 200, second.text
            second_body = second.json()
            assert second_body["success"] is True
            assert second_body["integrity"]["nonTargetNodesUnchanged"] is True
            # selectedNodeId 与 Round 1 相同
            assert second_body["integrity"]["selectedNodeId"] == TARGET_NODE_ID

            # --- currentStyle 的来源取证（DD-12）---
            second_context = spy.contexts[1]
            expected_current_style = _drop_none(first_node["style"])
            assert second_context.selected_node_style == expected_current_style
            # 含 Round 1 已确认的 color —— 上下文确实是「上一轮之后」的状态
            assert second_context.selected_node_style["color"] == round_1_color
            # 且是**整个节点的现行 style**，不是 history 里那份只含 color 的 patchStyle
            assert set(second_context.selected_node_style) >= {
                "color",
                "fontSize",
                "fontWeight",
            }
            # confirmed history 原样到达 Provider，且其 patchStyle 含 Round 1 的 color
            assert len(second_context.conversation_history) == 1
            history_turn = second_context.conversation_history[0]
            assert history_turn.instruction == ROUND_1_INSTRUCTION
            assert history_turn.selected_node_id == TARGET_NODE_ID
            assert history_turn.patch_style["color"] == round_1_color

            # --- Round 2 的产出：合法 fontSize 修改 ---
            second_doc = second_body["document"]
            validate_dsl_document(second_doc)
            second_merged = _merged_style(second_body["patch"], TARGET_NODE_ID)
            assert "fontSize" in second_merged, second_body["patch"]
            new_font_size = second_merged["fontSize"]
            _assert_in_size_domain(new_font_size)
            assert _SIZE_RE.match(new_font_size), new_font_size
            assert new_font_size != INITIAL_FONT_SIZE, new_font_size

            second_node = _find_node(second_doc["root"], TARGET_NODE_ID)
            assert second_node is not None
            assert second_node["style"]["fontSize"] == new_font_size
            # --- 浅合并语义正确：Round 1 已确认的 color 未被丢失 ---
            assert second_node["style"]["color"] == round_1_color
            # --- 非目标节点零变更（相对 Round 1 的已确认文档）---
            _assert_non_target_unchanged(first_doc, second_doc, TARGET_NODE_ID)
            # --- Document 仍是唯一事实来源 ---
            assert second_doc == apply_patch(
                first_doc, second_body["patch"]
            ).model_dump(mode="json", by_alias=True)

    asyncio.run(run())
