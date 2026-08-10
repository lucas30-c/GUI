"""
Refinement Pipeline 的 style 行为测试（Spec 010 P-3 / P-4）

分部：
- A 部分：步骤 4 派生 `selected_node_style`、步骤 6 接受 `update_style`、
  步骤 7 对 style op 与混合 op 逐条边界检查、越界时文档零变更（AC-10 / AC-19）
- B 部分：步骤 9 完整性语义——目标 style 可变、非目标 style 不可变、
  目标 `id`/`type`/`children` 不可变（AC-20）
- C 部分：多轮 style 上下文累积（AC-23，见文件末尾）
"""

import asyncio
import copy
import json
from unittest.mock import patch as mock_patch

import pytest

from genui_api.contracts.validation import validate_dsl_document
from genui_api.llm.prompts import build_refinement_messages
from genui_api.provider.base import ConfirmedTurn
from genui_api.refinement.pipeline import (
    RefinementError,
    refine,
    verify_non_target_unchanged,
)


# ============================================================
# 夹具
# ============================================================


def _doc() -> dict:
    """hero.title 有 style；hero.sub 无 style；section 有 children"""
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {"title": "T"},
            "children": [
                {
                    "id": "hero.title",
                    "type": "Heading",
                    "props": {"text": "Brew", "level": 1},
                    "style": {"fontSize": "2rem", "color": "#111111"},
                },
                {
                    "id": "hero.sub",
                    "type": "Text",
                    "props": {"text": "sub"},
                },
            ],
        },
    }


class _Stub:
    """记录收到的 context 并返回预设 operations 的 Provider stub"""

    def __init__(self, operations: list):
        self.operations = operations
        self.seen: list = []

    async def generate_patch(self, context) -> dict:
        self.seen.append(context)
        return {"version": "0.1", "operations": self.operations}


def _style_op(style: dict, target: str = "hero.title") -> dict:
    return {"op": "update_style", "targetNodeId": target, "style": style}


def _props_op(props: dict, target: str = "hero.title") -> dict:
    return {"op": "update_props", "targetNodeId": target, "props": props}


def _run(
    operations: list,
    document: dict | None = None,
    selected: str = "hero.title",
    history: tuple = (),
):
    stub = _Stub(operations)
    result = asyncio.run(
        refine(
            document=document if document is not None else _doc(),
            selected_node_id=selected,
            instruction="改样式",
            provider=stub,
            history=history,
        )
    )
    return result, stub


def _node(doc: dict, node_id: str) -> dict:
    return next(c for c in doc["root"]["children"] if c["id"] == node_id)


# ============================================================
# A 部分：步骤 4 派生 + 步骤 6/7 接纳与边界
# ============================================================


class TestStyleContextDerivation:
    """A 部分：selected_node_style 的派生（步骤 4）"""

    def test_current_style_derived_from_document(self):
        """currentStyle 来自已校验文档，而非模型输出或 history"""
        _, stub = _run([_style_op({"color": "#c0392b"})])
        assert stub.seen[0].selected_node_style == {
            "fontSize": "2rem",
            "color": "#111111",
        }

    def test_current_style_excludes_none_valued_keys(self):
        """未设置的白名单字段不出现在 currentStyle 中（exclude_none）"""
        _, stub = _run([_style_op({"color": "#c0392b"})])
        style = stub.seen[0].selected_node_style
        assert set(style) == {"fontSize", "color"}
        assert all(v is not None for v in style.values())

    def test_current_style_is_empty_dict_for_styleless_node(self):
        """无 style 的节点派生为空 dict（而非 None）"""
        _, stub = _run(
            [_style_op({"color": "#c0392b"}, target="hero.sub")], selected="hero.sub"
        )
        assert stub.seen[0].selected_node_style == {}

    def test_current_style_is_deep_copied(self):
        """Provider 改写 context.selected_node_style 不影响调用方文档"""
        document = _doc()
        before = copy.deepcopy(document)

        class Mutating:
            async def generate_patch(self, context):
                context.selected_node_style["color"] = "#hacked"
                context.selected_node_style["boxShadow"] = "evil"
                return {"version": "0.1", "operations": [_style_op({"gap": "4px"})]}

        result = asyncio.run(
            refine(
                document=document,
                selected_node_id="hero.title",
                instruction="改样式",
                provider=Mutating(),
            )
        )
        assert document == before
        target = _node(result.document, "hero.title")
        assert target["style"]["color"] == "#111111"
        assert "boxShadow" not in target["style"]

    def test_current_props_still_derived_alongside_style(self):
        """props 派生行为不受 style 新增影响（M4-03 回归）"""
        _, stub = _run([_style_op({"color": "#c0392b"})])
        assert stub.seen[0].selected_node_props == {"text": "Brew", "level": 1}

    def test_history_patch_style_is_carried_and_deep_copied(self):
        """history 的 patch_style 被透传给 Provider 且是深拷贝"""
        turn_style = {"fontSize": "2rem"}
        turn = ConfirmedTurn(
            instruction="字大一点",
            selected_node_id="hero.title",
            selected_node_type="Heading",
            patch_props={},
            patch_style=turn_style,
        )
        _, stub = _run([_style_op({"color": "#c0392b"})], history=(turn,))
        seen_turn = stub.seen[0].conversation_history[0]
        assert seen_turn.patch_style == {"fontSize": "2rem"}
        assert seen_turn.patch_style is not turn_style


class TestStyleCandidateAcceptanceAndBoundary:
    """A 部分：步骤 6 接受 update_style、步骤 7 逐条边界检查"""

    def test_style_candidate_accepted_and_applied(self):
        """步骤 6 接受 update_style 候选，步骤 8 正确应用"""
        result, _ = _run([_style_op({"color": "#c0392b", "padding": "16px"})])
        style = _node(result.document, "hero.title")["style"]
        assert style["color"] == "#c0392b"
        assert style["padding"] == "16px"
        assert style["fontSize"] == "2rem"
        assert result.integrity["nonTargetNodesUnchanged"] is True
        assert result.integrity["selectedNodeId"] == "hero.title"

    def test_mixed_candidate_accepted_and_applied(self):
        """混合候选（props + style）两侧都生效"""
        result, _ = _run(
            [_props_op({"text": "New"}), _style_op({"fontWeight": "bold"})]
        )
        target = _node(result.document, "hero.title")
        assert target["props"]["text"] == "New"
        assert target["style"]["fontWeight"] == "bold"

    def test_returned_patch_is_the_candidate(self):
        """返回的 patch 就是候选本身（含 update_style op）"""
        operations = [_style_op({"textAlign": "center"})]
        result, _ = _run(operations)
        assert result.patch == {"version": "0.1", "operations": operations}

    @pytest.mark.parametrize(
        "operations,label",
        [
            ([_style_op({"color": "#000000"}, target="hero.sub")], "纯 style 越界"),
            (
                [
                    _props_op({"text": "x"}),
                    _style_op({"color": "#000000"}, target="hero.sub"),
                ],
                "混合中 style 越界",
            ),
            (
                [
                    _style_op({"color": "#000000"}),
                    _props_op({"text": "x"}, target="hero.sub"),
                ],
                "混合中 props 越界",
            ),
            ([_style_op({"color": "#000000"}, target="page")], "指向根节点",
            ),
            ([_style_op({"color": "#000000"}, target="ghost")], "指向不存在节点"),
        ],
    )
    def test_out_of_boundary_style_op_rejected(self, operations: list, label: str):
        """越界 style op 在步骤 7 被拒（Provider 之后、应用之前），文档零变更"""
        document = _doc()
        before = copy.deepcopy(document)
        with pytest.raises(RefinementError) as exc_info:
            _run(operations, document=document)
        assert exc_info.value.code == "candidate_boundary_violation"
        assert document == before

    @pytest.mark.parametrize(
        "bad_style,label",
        [
            ({"boxShadow": "1px 1px"}, "未知键"),
            ({}, "空 style"),
            ({"fontSize": "16"}, "缺单位"),
            ({"color": "red"}, "非白名单命名色"),
        ],
    )
    def test_invalid_style_candidate_rejected_at_step_6(
        self, bad_style: dict, label: str
    ):
        """非法 style 候选在步骤 6 被拒 → invalid_candidate_structure，文档零变更"""
        document = _doc()
        before = copy.deepcopy(document)
        with pytest.raises(RefinementError) as exc_info:
            _run([_style_op(bad_style)], document=document)
        assert exc_info.value.code == "invalid_candidate_structure"
        assert document == before

    def test_unknown_op_candidate_rejected_at_step_6(self):
        """未注册 op 的候选仍在步骤 6 被拒"""
        document = _doc()
        before = copy.deepcopy(document)
        with pytest.raises(RefinementError) as exc_info:
            _run(
                [{"op": "update_styles", "targetNodeId": "hero.title", "style": {}}],
                document=document,
            )
        assert exc_info.value.code == "invalid_candidate_structure"
        assert document == before


# ============================================================
# B 部分：步骤 9 完整性语义
# ============================================================


class TestNonTargetIntegrityWithStyle:
    """B 部分：verify_non_target_unchanged 的 style 语义（DD-20）"""

    def test_target_style_change_allowed(self):
        """目标节点 style 变化 → True"""
        original = validate_dsl_document(_doc())
        modified_dict = _doc()
        modified_dict["root"]["children"][0]["style"] = {"color": "#c0392b"}
        modified = validate_dsl_document(modified_dict)
        assert verify_non_target_unchanged(original, modified, "hero.title") is True

    def test_target_style_removal_allowed(self):
        """目标节点 style 被整体删除（归一化）→ True"""
        original = validate_dsl_document(_doc())
        modified_dict = _doc()
        del modified_dict["root"]["children"][0]["style"]
        modified = validate_dsl_document(modified_dict)
        assert verify_non_target_unchanged(original, modified, "hero.title") is True

    def test_target_style_addition_allowed(self):
        """目标节点从无 style 到有 style → True"""
        original = validate_dsl_document(_doc())
        modified_dict = _doc()
        modified_dict["root"]["children"][1]["style"] = {"color": "#c0392b"}
        modified = validate_dsl_document(modified_dict)
        assert verify_non_target_unchanged(original, modified, "hero.sub") is True

    def test_non_target_style_change_detected(self):
        """非目标节点 style 变化 → False"""
        original = validate_dsl_document(_doc())
        modified_dict = _doc()
        modified_dict["root"]["children"][1]["style"] = {"color": "#c0392b"}
        modified = validate_dsl_document(modified_dict)
        assert verify_non_target_unchanged(original, modified, "hero.title") is False

    def test_non_target_style_removal_detected(self):
        """非目标节点 style 被删除 → False"""
        original = validate_dsl_document(_doc())
        modified_dict = _doc()
        del modified_dict["root"]["children"][0]["style"]
        modified = validate_dsl_document(modified_dict)
        assert verify_non_target_unchanged(original, modified, "hero.sub") is False

    def test_root_style_change_detected_when_child_is_target(self):
        """根节点 style 变化在子节点为目标时仍被检出 → False"""
        original = validate_dsl_document(_doc())
        modified_dict = _doc()
        modified_dict["root"]["style"] = {"padding": "16px"}
        modified = validate_dsl_document(modified_dict)
        assert verify_non_target_unchanged(original, modified, "hero.title") is False

    def test_target_type_change_detected(self):
        """目标节点 type 变化 → False（剥离范围不含 type）"""
        original = validate_dsl_document(_doc())
        modified_dict = _doc()
        modified_dict["root"]["children"][0]["type"] = "Text"
        modified_dict["root"]["children"][0]["props"] = {"text": "x"}
        modified = validate_dsl_document(modified_dict)
        assert verify_non_target_unchanged(original, modified, "hero.title") is False

    def test_target_children_change_detected(self):
        """目标节点 children 变化 → False（剥离范围不含 children）"""
        doc_dict = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {},
                "children": [
                    {
                        "id": "sec",
                        "type": "Section",
                        "props": {},
                        "style": {"gap": "8px"},
                        "children": [
                            {"id": "t1", "type": "Text", "props": {"text": "A"}}
                        ],
                    }
                ],
            },
        }
        original = validate_dsl_document(doc_dict)
        modified_dict = copy.deepcopy(doc_dict)
        modified_dict["root"]["children"][0]["children"].append(
            {"id": "t2", "type": "Text", "props": {"text": "B"}}
        )
        modified = validate_dsl_document(modified_dict)
        assert verify_non_target_unchanged(original, modified, "sec") is False

    def test_integrity_breach_surfaces_as_internal_error(self):
        """完整性校验失败 → non_target_mutation_detected，且不返回文档"""
        document = _doc()
        before = copy.deepcopy(document)
        with mock_patch(
            "genui_api.refinement.pipeline.verify_non_target_unchanged",
            return_value=False,
        ):
            with pytest.raises(RefinementError) as exc_info:
                _run([_style_op({"color": "#c0392b"})], document=document)
        assert exc_info.value.code == "non_target_mutation_detected"
        assert document == before


# ============================================================
# C 部分：多轮 style 上下文累积（AC-23）
# ============================================================


def _derive_patch_style(patch: dict) -> dict:
    """把已确认 patch 折叠为该轮的 patchStyle（与前端 derivePatchStyle 同口径）。"""
    merged: dict = {}
    for op in patch["operations"]:
        if op["op"] == "update_style":
            merged.update(op["style"])
    return merged


def _derive_patch_props(patch: dict) -> dict:
    merged: dict = {}
    for op in patch["operations"]:
        if op["op"] == "update_props":
            merged.update(op["props"])
    return merged


def _next_turn(instruction: str, patch: dict, node_id: str, node_type: str) -> ConfirmedTurn:
    return ConfirmedTurn(
        instruction=instruction,
        selected_node_id=node_id,
        selected_node_type=node_type,
        patch_props=_derive_patch_props(patch),
        patch_style=_derive_patch_style(patch),
    )


def _play_rounds(rounds: list[tuple[str, list]], document: dict | None = None):
    """按序执行多轮精修，每轮把上一轮结果文档与累积 history 作为输入。

    返回 (最终文档, 每轮 Provider 收到的 context 列表, 累积 history, 每轮 integrity 列表)。
    """
    doc = document if document is not None else _doc()
    history: tuple[ConfirmedTurn, ...] = ()
    contexts: list = []
    integrities: list = []
    for instruction, operations in rounds:
        stub = _Stub(operations)
        result = asyncio.run(
            refine(
                document=doc,
                selected_node_id="hero.title",
                instruction=instruction,
                provider=stub,
                history=history,
            )
        )
        contexts.append(stub.seen[0])
        integrities.append(result.integrity)
        doc = result.document
        history = history + (
            _next_turn(instruction, result.patch, "hero.title", "Heading"),
        )
    return doc, contexts, history, integrities


def _effective_style(doc: dict, node_id: str) -> dict:
    """节点的**有效** style：剥掉 None 值。

    Pipeline 步骤 10 的 `model_dump(mode="json", by_alias=True)` 不带 `exclude_none`
    （M4-03 既有行为），因此返回文档会把未设置的可选字段显式写成 null。DSL 中
    `None` 与「缺失」语义等价，故多轮断言以剥掉 None 后的有效值为准。
    """
    style = _node(doc, node_id).get("style") or {}
    return {k: v for k, v in style.items() if v is not None}



_THREE_ROUNDS = [
    ("改成品牌红", [_style_op({"color": "#c0392b"})]),
    ("字再大一点", [_style_op({"fontSize": "3rem"})]),
    ("加粗并居中", [_style_op({"fontWeight": "bold", "textAlign": "center"})]),
]


class TestMultiTurnStyleAccumulation:
    """C 部分：B→C→D 三连轮的 style 累积与上下文权威（AC-23）"""

    def test_three_rounds_accumulate_style_on_document(self):
        """三轮 style 精修逐轮累积到同一节点，早轮结果不被后轮丢弃"""
        final_doc, _, _, integrities = _play_rounds(_THREE_ROUNDS)
        assert _effective_style(final_doc, "hero.title") == {
            "fontSize": "3rem",
            "color": "#c0392b",
            "fontWeight": "bold",
            "textAlign": "center",
        }
        assert all(i["nonTargetNodesUnchanged"] is True for i in integrities)

    def test_current_style_each_round_equals_previous_confirmed_document(self):
        """每轮 currentStyle 恒等于上一轮确认后的文档派生值（Document 是唯一事实来源）"""
        _, contexts, _, _ = _play_rounds(_THREE_ROUNDS)
        assert contexts[0].selected_node_style == {"fontSize": "2rem", "color": "#111111"}
        assert contexts[1].selected_node_style == {"fontSize": "2rem", "color": "#c0392b"}
        assert contexts[2].selected_node_style == {"fontSize": "3rem", "color": "#c0392b"}

    def test_round_k_history_carries_previous_style_ops(self):
        """第 k 轮的 history 恰含前 k-1 轮的 patch_style"""
        _, contexts, _, _ = _play_rounds(_THREE_ROUNDS)
        assert [len(c.conversation_history) for c in contexts] == [0, 1, 2]
        assert [t.patch_style for t in contexts[2].conversation_history] == [
            {"color": "#c0392b"},
            {"fontSize": "3rem"},
        ]

    def test_round_k_messages_contain_previous_style_operations(self):
        """第 k 轮 messages 的历史 assistant 段落逐轮重建为 update_style（2N+2 布局不变）"""
        _, contexts, _, _ = _play_rounds(_THREE_ROUNDS)
        messages = build_refinement_messages(contexts[2])
        assert len(messages) == 2 * 2 + 2
        assistants = [m["content"] for m in messages if m["role"] == "assistant"]
        assert len(assistants) == 2
        assert '"op": "update_style"' in assistants[0]
        assert "#c0392b" in assistants[0]
        assert "3rem" in assistants[1]
        # 当前轮 UP 的 currentStyle 才是权威现值
        current = json.loads(messages[-1]["content"])["currentStyle"]
        assert current == {"fontSize": "3rem", "color": "#c0392b"}

    def test_mixed_round_then_style_round_keeps_both_dimensions(self):
        """混合轮之后的纯 style 轮：props 与 style 两侧结果同时保留"""
        final_doc, contexts, history, _ = _play_rounds(
            [
                ("改文案并变红", [_props_op({"text": "Brew Co."}), _style_op({"color": "#c0392b"})]),
                ("再加粗", [_style_op({"fontWeight": "bold"})]),
            ]
        )
        assert _node(final_doc, "hero.title")["props"] == {"text": "Brew Co.", "level": 1}
        assert _effective_style(final_doc, "hero.title") == {
            "fontSize": "2rem",
            "color": "#c0392b",
            "fontWeight": "bold",
        }
        first_turn = contexts[1].conversation_history[0]
        assert first_turn.patch_props == {"text": "Brew Co."}
        assert first_turn.patch_style == {"color": "#c0392b"}
        assert len(history) == 2

    def test_null_style_round_removes_key_and_is_visible_next_round(self):
        """删除轮（null）落到文档后，下一轮 currentStyle 不再包含该键"""
        final_doc, contexts, _, _ = _play_rounds(
            [
                ("加个背景", [_style_op({"backgroundColor": "#ffffff"})]),
                ("去掉背景", [_style_op({"backgroundColor": None})]),
                ("字大一点", [_style_op({"fontSize": "3rem"})]),
            ]
        )
        assert "backgroundColor" not in _effective_style(final_doc, "hero.title")
        assert contexts[1].selected_node_style["backgroundColor"] == "#ffffff"
        assert "backgroundColor" not in contexts[2].selected_node_style
        assert contexts[2].conversation_history[1].patch_style == {"backgroundColor": None}

    def test_failed_round_does_not_pollute_document_or_next_context(self):
        """失败轮不改文档、不入 history：后续轮的 currentStyle 与失败前完全一致"""
        doc, _, history, _ = _play_rounds([_THREE_ROUNDS[0]])
        snapshot = copy.deepcopy(doc)

        with pytest.raises(RefinementError):
            asyncio.run(
                refine(
                    document=doc,
                    selected_node_id="hero.title",
                    instruction="加个阴影",
                    provider=_Stub([_style_op({"boxShadow": "1px 1px"})]),
                    history=history,
                )
            )
        assert doc == snapshot

        stub = _Stub([_style_op({"fontSize": "3rem"})])
        result = asyncio.run(
            refine(
                document=doc,
                selected_node_id="hero.title",
                instruction="字大一点",
                provider=stub,
                history=history,
            )
        )
        assert stub.seen[0].selected_node_style == {"fontSize": "2rem", "color": "#c0392b"}
        assert len(stub.seen[0].conversation_history) == 1
        assert _effective_style(result.document, "hero.title")["fontSize"] == "3rem"

    def test_non_target_node_untouched_across_all_rounds(self):
        """全程非目标节点零变更（逐轮 integrity 为 True 且有效值逐键相等）"""
        document = _doc()
        final_doc, _, _, integrities = _play_rounds(_THREE_ROUNDS, document=document)
        after_sub = _node(final_doc, "hero.sub")
        assert after_sub["id"] == "hero.sub"
        assert after_sub["type"] == "Text"
        assert after_sub["props"] == {"text": "sub"}
        assert _effective_style(final_doc, "hero.sub") == {}
        assert final_doc["root"]["props"] == document["root"]["props"]
        assert all(i["nonTargetNodesUnchanged"] is True for i in integrities)

