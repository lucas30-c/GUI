"""多轮 messages 构造测试（Spec 009 DD-7 / DD-8 / DD-10 / R-1）。

本文件是「SP 允许一次受控版本升级」这一决定的验收面：升级放宽的是 SP 的**文本**，
不放宽 SP 的**性质**。因此下面同时断言：
- SP 仍无参、仍每请求逐字节稳定、仍不含任何请求数据；
- SP 保留 M4-02 的全部关键契约要点，并新增多轮语义要点；
- 当前轮 User Prompt 与 M4-02 逐字节相同（真正的向后兼容面在这里）。
"""

import json

import pytest

from genui_api.llm.prompts import (
    build_refinement_history_assistant_content,
    build_refinement_history_user_prompt,
    build_refinement_messages,
    build_refinement_system_prompt,
    build_refinement_user_prompt,
)
from genui_api.provider.base import ConfirmedTurn, RefinementContext


# ============================================================
# Fixtures & Helpers
# ============================================================


def _turn(i: int = 1, node_id: str = "hero.title", node_type: str = "Heading") -> ConfirmedTurn:
    return ConfirmedTurn(
        instruction=f"第 {i} 轮指令",
        selected_node_id=node_id,
        selected_node_type=node_type,
        patch_props={"text": f"第 {i} 版文案"},
    )


def _context(history: tuple[ConfirmedTurn, ...] = ()) -> RefinementContext:
    return RefinementContext(
        instruction="再短一点",
        selected_node_id="hero.title",
        selected_node_type="Heading",
        selected_node_props={"text": "当前文案", "level": 1},
        document_version="0.1",
        conversation_history=history,
    )


# ============================================================
# messages 布局：2N + 2
# ============================================================


def test_empty_history_yields_exactly_two_messages():
    messages = build_refinement_messages(_context())
    assert len(messages) == 2
    assert [m["role"] for m in messages] == ["system", "user"]


@pytest.mark.parametrize("n", [1, 2, 3, 20])
def test_message_count_is_2n_plus_2(n):
    history = tuple(_turn(i) for i in range(n))
    messages = build_refinement_messages(_context(history))
    assert len(messages) == 2 * n + 2


def test_role_sequence_alternates_user_assistant():
    history = tuple(_turn(i) for i in range(3))
    roles = [m["role"] for m in build_refinement_messages(_context(history))]
    assert roles == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]


def test_history_is_ordered_oldest_to_newest():
    history = tuple(_turn(i) for i in range(3))
    messages = build_refinement_messages(_context(history))
    user_instructions = [
        json.loads(m["content"])["instruction"] for m in messages[1:-1] if m["role"] == "user"
    ]
    assert user_instructions == ["第 0 轮指令", "第 1 轮指令", "第 2 轮指令"]


def test_current_user_message_is_last():
    messages = build_refinement_messages(_context((_turn(),)))
    last = json.loads(messages[-1]["content"])
    assert last["instruction"] == "再短一点"
    assert last["currentProps"] == {"text": "当前文案", "level": 1}


def test_only_one_system_message():
    history = tuple(_turn(i) for i in range(4))
    messages = build_refinement_messages(_context(history))
    assert [m["role"] for m in messages].count("system") == 1


# ============================================================
# 三态等价与 M4-02 向后兼容（DD-10 / AC-11）
# ============================================================


def test_absent_null_empty_histories_are_byte_identical():
    """域层三态：默认 / 显式空 tuple / 显式空 list → messages 逐字节相同。"""
    default_ctx = RefinementContext(
        instruction="再短一点",
        selected_node_id="hero.title",
        selected_node_type="Heading",
        selected_node_props={"text": "当前文案", "level": 1},
        document_version="0.1",
    )
    a = build_refinement_messages(default_ctx)
    b = build_refinement_messages(_context(()))
    c = build_refinement_messages(_context(tuple([])))
    assert a == b == c


def test_current_user_prompt_is_byte_identical_to_m402():
    """当前轮 UP 恒等于 M4-02 的 4 键构造结果——history 存在与否都不改变它。"""
    expected = build_refinement_user_prompt(
        instruction="再短一点",
        selected_node_id="hero.title",
        node_type="Heading",
        current_props={"text": "当前文案", "level": 1},
    )
    without = build_refinement_messages(_context())[-1]["content"]
    with_history = build_refinement_messages(_context(tuple(_turn(i) for i in range(3))))[-1][
        "content"
    ]
    assert without == expected
    assert with_history == expected


def test_current_user_prompt_has_exactly_five_keys():
    """Spec 010 DD-14（AP-6 批准）：当前轮 UP 由 4 键升级为 5 键，新增 currentStyle。"""
    payload = json.loads(build_refinement_messages(_context((_turn(),)))[-1]["content"])
    assert set(payload.keys()) == {
        "instruction",
        "selectedNodeId",
        "nodeType",
        "currentProps",
        "currentStyle",
    }


# ============================================================
# System Prompt 的性质（升级文本，不放宽性质）
# ============================================================


def test_system_prompt_is_byte_stable_across_calls():
    assert build_refinement_system_prompt() == build_refinement_system_prompt()


def test_system_prompt_independent_of_request_data():
    """SP 不随 context 变化：任何 history / instruction 都不进入 system role。"""
    plain = build_refinement_messages(_context())[0]["content"]
    polluted_history = (
        ConfirmedTurn(
            instruction="MARKER-INSTRUCTION",
            selected_node_id="MARKER-NODE",
            selected_node_type="Heading",
            patch_props={"text": "MARKER-PROP"},
        ),
    )
    polluted = build_refinement_messages(_context(polluted_history))[0]["content"]
    assert plain == polluted == build_refinement_system_prompt()
    assert "MARKER" not in polluted


def test_system_prompt_retains_m402_contract_points():
    sp = build_refinement_system_prompt()
    for token in ("update_props", "targetNodeId", "operations", "0.1", "JSON", "children"):
        assert token in sp


def test_system_prompt_declares_multi_turn_semantics():
    sp = build_refinement_system_prompt()
    for token in ("历史", "最后一条 user 消息", "currentProps"):
        assert token in sp


# ============================================================
# 历史消息内容构造
# ============================================================


def test_history_user_prompt_has_exactly_three_keys():
    payload = json.loads(build_refinement_history_user_prompt(_turn()))
    assert set(payload.keys()) == {"instruction", "selectedNodeId", "nodeType"}
    assert "currentProps" not in payload


def test_history_assistant_content_is_reconstructed_patch():
    turn = _turn()
    payload = json.loads(build_refinement_history_assistant_content(turn))
    assert payload == {
        "version": "0.1",
        "operations": [
            {
                "op": "update_props",
                "targetNodeId": turn.selected_node_id,
                "props": turn.patch_props,
            }
        ],
    }


def test_history_assistant_content_is_valid_patch_shape():
    """重建结果必须能通过 Patch 模型校验（历史上下文本身不越界）。"""
    from genui_api.patch.models import PatchDocument

    raw = build_refinement_history_assistant_content(_turn())
    patch = PatchDocument.model_validate(json.loads(raw))
    assert patch.operations[0].op == "update_props"


def test_history_messages_are_deterministic():
    """同一 turn 反复构造逐字节相同（纯函数、无时间戳、无随机）。"""
    turn = _turn()
    assert build_refinement_history_user_prompt(turn) == build_refinement_history_user_prompt(
        turn
    )
    assert build_refinement_history_assistant_content(
        turn
    ) == build_refinement_history_assistant_content(turn)


def test_history_messages_preserve_non_ascii():
    content = build_refinement_history_user_prompt(_turn())
    assert "第 1 轮指令" in content
    assert "\\u" not in content


def test_history_of_other_node_appears_only_as_context():
    """历史轮指向别的节点时，当前轮 UP 的 selectedNodeId 不受影响。"""
    history = (_turn(node_id="hero.cta", node_type="Button"),)
    messages = build_refinement_messages(_context(history))
    assert json.loads(messages[1]["content"])["selectedNodeId"] == "hero.cta"
    assert json.loads(messages[-1]["content"])["selectedNodeId"] == "hero.title"
