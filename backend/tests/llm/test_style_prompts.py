"""Prompt 层的 style 维度测试（Spec 010 第 5 层测试 / AC-14 ~ AC-16 / DD-14 ~ DD-16）。

关注三件事，且只关注这三件：
1. SP 升级的是**文本**而非**性质** —— 仍无参、仍逐字节稳定、仍不含任何请求数据，
   同时必须完整覆盖 11 字段白名单与 `update_style` 的形状，且旧禁令已彻底移除。
2. 当前轮 UP 恰 5 键，`currentStyle` 严格等于 Pipeline 从已校验 Document 派生的值
   （提示词层不做任何补全 / 猜测 / 默认值填充）。
3. 历史 assistant 内容是由 ConfirmedTurn **确定性重建**的 Patch，四种分支都有定义。

这些断言全部落在纯函数上：无 I/O、无 Provider、无网络。
"""

import json

import pytest

from genui_api.contracts.dsl import Style
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

_STYLE_FIELDS = tuple(Style.model_fields)


def _turn(
    instruction: str = "字大一点",
    node_id: str = "hero.title",
    node_type: str = "Heading",
    props: dict | None = None,
    style: dict | None = None,
) -> ConfirmedTurn:
    return ConfirmedTurn(
        instruction=instruction,
        selected_node_id=node_id,
        selected_node_type=node_type,
        patch_props=props if props is not None else {},
        patch_style=style if style is not None else {},
    )


def _context(
    history: tuple[ConfirmedTurn, ...] = (),
    style: dict | None = None,
) -> RefinementContext:
    return RefinementContext(
        instruction="标题改红并加粗",
        selected_node_id="hero.title",
        selected_node_type="Heading",
        selected_node_props={"text": "Brew", "level": 1},
        document_version="0.1",
        conversation_history=history,
        selected_node_style=style if style is not None else {},
    )


# ============================================================
# A. System Prompt：新增能力声明（AC-14）
# ============================================================


def test_system_prompt_lists_all_eleven_style_fields():
    """11 字段白名单必须逐字出现在 SP 中——事实来源是 Style 模型，不是硬编码列表。"""
    sp = build_refinement_system_prompt()
    assert len(_STYLE_FIELDS) == 11
    for name in _STYLE_FIELDS:
        assert name in sp, name


def test_system_prompt_declares_update_style_operation_shape():
    """SP 必须给出 update_style 的完整形状，且与 update_props 并列声明。"""
    sp = build_refinement_system_prompt()
    for token in (
        '"op": "update_style"',
        '"targetNodeId"',
        '"style"',
        "update_props",
        "浅合并",
        "平级",
    ):
        assert token in sp, token


def test_system_prompt_declares_null_deletion_semantics():
    """null 语义（DD-06 / SS-2）必须写进 SP，否则模型无法表达「去掉背景色」。"""
    sp = build_refinement_system_prompt()
    assert "null" in sp
    assert "删除" in sp


def test_system_prompt_declares_style_value_domains():
    """值域约束必须显式：#hex / 命名色 / 数字+单位 / 两个枚举。"""
    sp = build_refinement_system_prompt()
    for token in ("#hex", "transparent", "px", "rem", "%", "semibold", "center"):
        assert token in sp, token


def test_system_prompt_no_longer_forbids_style():
    """AP-6：旧禁令必须彻底移除，不能与新能力共存（自相矛盾的 SP 会降低成功率）。"""
    sp = build_refinement_system_prompt()
    assert "视觉样式调整暂不在本操作的能力范围内" not in sp
    assert "不要伪造 style 字段" not in sp
    assert '不得修改节点的 "style"' not in sp


def test_system_prompt_still_forbids_structural_mutation():
    """放宽 style 不等于放宽结构：id / type / children / 越界仍是硬禁令。"""
    sp = build_refinement_system_prompt()
    for token in ('不得修改节点的 "id"', '不得修改节点的 "type"', "children", "目标节点之外"):
        assert token in sp, token


def test_system_prompt_declares_mixed_operations():
    """一条指令同时改内容与样式时，SP 必须指明用同一数组内的两个 op 表达（SS-8）。"""
    sp = build_refinement_system_prompt()
    assert "同时" in sp
    assert "operations" in sp


def test_system_prompt_references_current_style_for_relative_instructions():
    """相对指令（再大一点）的权威基准是 currentStyle，而不是历史消息里的旧值。"""
    sp = build_refinement_system_prompt()
    assert "currentStyle" in sp
    assert "currentProps" in sp


def test_system_prompt_remains_byte_stable_and_data_free():
    """SP 的**性质**不变：无参、逐字节稳定、不含任何请求数据（prompt caching 前提）。"""
    sp = build_refinement_system_prompt()
    assert sp == build_refinement_system_prompt()
    polluted = build_refinement_messages(
        _context(
            history=(_turn(instruction="MARKER-INSTRUCTION", style={"color": "#MARKER"}),),
            style={"fontSize": "MARKER-SIZE"},
        )
    )[0]["content"]
    assert polluted == sp
    assert "MARKER" not in polluted


# ============================================================
# B. User Prompt：恰 5 键（AC-15）
# ============================================================


def test_user_prompt_has_exactly_five_keys_in_order():
    up = json.loads(
        build_refinement_user_prompt(
            instruction="改红",
            selected_node_id="hero.title",
            node_type="Heading",
            current_props={"text": "Brew", "level": 1},
            current_style={"fontSize": "2rem"},
        )
    )
    assert list(up) == [
        "instruction",
        "selectedNodeId",
        "nodeType",
        "currentProps",
        "currentStyle",
    ]


@pytest.mark.parametrize(
    "style",
    [
        {},
        {"color": "#c0392b"},
        {"fontSize": "2rem", "fontWeight": "bold", "textAlign": "center"},
    ],
)
def test_user_prompt_current_style_equals_derived_value(style):
    """currentStyle 逐键等于 context.selected_node_style，提示词层不加工。"""
    up = json.loads(build_refinement_messages(_context(style=style))[-1]["content"])
    assert up["currentStyle"] == style


def test_user_prompt_style_omitted_becomes_empty_object():
    """M4-02/M4-03 的 4 参调用继续可用，且键集恒为 5 键（「无样式」= 空对象而非缺键）。"""
    up = json.loads(
        build_refinement_user_prompt(
            instruction="改红",
            selected_node_id="hero.title",
            node_type="Heading",
            current_props={"text": "Brew"},
        )
    )
    assert up["currentStyle"] == {}


def test_user_prompt_contains_no_full_document():
    """最小权限（DD-10）：UP 仍不含完整文档 / 兄弟节点 / metadata。"""
    up = build_refinement_messages(_context(style={"color": "#c0392b"}))[-1]["content"]
    for token in ('"root"', '"children"', '"metadata"', '"version"'):
        assert token not in up, token


def test_user_prompt_style_survives_unicode_and_escaping():
    """ensure_ascii=False：中文与特殊字符原样进入 JSON 字符串且可被解析回来。"""
    up = json.loads(
        build_refinement_user_prompt(
            instruction='把标题改成"品牌红"',
            selected_node_id="hero.title",
            node_type="Heading",
            current_props={"text": "咖啡 & 茶"},
            current_style={"color": "#c0392b"},
        )
    )
    assert up["instruction"] == '把标题改成"品牌红"'
    assert up["currentProps"]["text"] == "咖啡 & 茶"
    assert up["currentStyle"] == {"color": "#c0392b"}


# ============================================================
# C. History 重建：四分支（AC-16 / DD-16）
# ============================================================


def test_history_user_prompt_still_has_exactly_three_keys():
    """历史 user 刻意不含 currentProps / currentStyle —— 旧快照不与当前轮竞争权威。"""
    payload = json.loads(build_refinement_history_user_prompt(_turn(style={"color": "#c0392b"})))
    assert set(payload) == {"instruction", "selectedNodeId", "nodeType"}


def test_history_assistant_props_only_branch():
    content = json.loads(build_refinement_history_assistant_content(_turn(props={"text": "新标题"})))
    assert content == {
        "version": "0.1",
        "operations": [
            {"op": "update_props", "targetNodeId": "hero.title", "props": {"text": "新标题"}}
        ],
    }


def test_history_assistant_style_only_branch():
    content = json.loads(
        build_refinement_history_assistant_content(_turn(style={"fontSize": "2rem"}))
    )
    assert content == {
        "version": "0.1",
        "operations": [
            {"op": "update_style", "targetNodeId": "hero.title", "style": {"fontSize": "2rem"}}
        ],
    }


def test_history_assistant_mixed_branch_keeps_props_first():
    """混合分支：数组内 props 在前、style 在后（确定性顺序，便于逐字节比较）。"""
    content = json.loads(
        build_refinement_history_assistant_content(
            _turn(props={"text": "立即预订"}, style={"fontWeight": "bold"})
        )
    )
    assert [op["op"] for op in content["operations"]] == ["update_props", "update_style"]
    assert content["operations"][0]["props"] == {"text": "立即预订"}
    assert content["operations"][1]["style"] == {"fontWeight": "bold"}
    assert {op["targetNodeId"] for op in content["operations"]} == {"hero.title"}


def test_history_assistant_empty_branch_degrades_to_empty_update_props():
    """两者皆空在正常链路不出现；仍必须给出形状合法、无副作用且不编造 style 的输出。"""
    content = json.loads(build_refinement_history_assistant_content(_turn()))
    assert content == {
        "version": "0.1",
        "operations": [{"op": "update_props", "targetNodeId": "hero.title", "props": {}}],
    }


def test_history_assistant_null_style_value_is_preserved():
    """删除类历史（值为 None）必须原样重建为 JSON null，模型才能学到删除语义。"""
    content = build_refinement_history_assistant_content(_turn(style={"backgroundColor": None}))
    assert '"backgroundColor": null' in content
    assert json.loads(content)["operations"][0]["style"] == {"backgroundColor": None}


def test_history_assistant_target_node_id_comes_from_turn_not_context():
    """重建只依赖 turn 自身：历史轮的 target 不会被当前轮的 selectedNodeId 覆写。"""
    content = json.loads(
        build_refinement_history_assistant_content(
            _turn(node_id="hero.subtitle", style={"color": "#000000"})
        )
    )
    assert content["operations"][0]["targetNodeId"] == "hero.subtitle"


def test_history_assistant_is_byte_stable():
    turn = _turn(props={"text": "A"}, style={"color": "#c0392b"})
    assert build_refinement_history_assistant_content(
        turn
    ) == build_refinement_history_assistant_content(turn)


# ============================================================
# D. messages 布局：2N + 2 不变（DD-23）
# ============================================================


@pytest.mark.parametrize("n", [0, 1, 3, 20])
def test_messages_layout_unchanged_with_style_turns(n):
    history = tuple(_turn(instruction=f"第 {i} 轮", style={"fontSize": f"{i + 1}rem"}) for i in range(n))
    messages = build_refinement_messages(_context(history, style={"fontSize": f"{n}rem"}))
    assert len(messages) == 2 * n + 2
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert [m["role"] for m in messages].count("system") == 1


def test_style_history_appears_only_in_assistant_role():
    """历史 style 只出现在 assistant 重建内容里，绝不进入 system role（S-7）。"""
    messages = build_refinement_messages(
        _context((_turn(style={"borderRadius": "9999px"}),), style={"borderRadius": "9999px"})
    )
    assert "9999px" not in messages[0]["content"]
    assert "9999px" in messages[2]["content"]
    assert messages[2]["role"] == "assistant"
