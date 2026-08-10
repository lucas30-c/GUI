"""
Patch v0.1 `update_style` 应用语义测试（Spec 010 P-2 / AC-05 ~ AC-08）

覆盖 §8 Style Semantics 的 SS-1 ~ SS-11：
- 有/无既有 style 的浅合并、未提及键保持
- `null` 删键、删不存在键幂等、删空后移除 `style` 键
- 幂等重放、多条 `update_style` 顺序、混合 ops 双生效与换序等价
- 非目标节点零变更、源文档不可变、应用后 DSL 校验兜底
"""

import copy
import json

import pytest

from genui_api.patch.apply import PatchError, apply_patch


# ============================================================
# 夹具
# ============================================================


def _doc() -> dict:
    """hero.title 有 style；hero.sub 有 style；hero.cta 无 style"""
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
                    "style": {"color": "#222222"},
                },
                {
                    "id": "hero.cta",
                    "type": "Button",
                    "props": {"text": "Book", "variant": "primary"},
                },
            ],
        },
    }


def _patch(operations: list) -> dict:
    return {"version": "0.1", "operations": operations}


def _style_op(style: dict, target: str = "hero.title") -> dict:
    return {"op": "update_style", "targetNodeId": target, "style": style}


def _props_op(props: dict, target: str = "hero.title") -> dict:
    return {"op": "update_props", "targetNodeId": target, "props": props}


def _dump(result, exclude_none: bool = False) -> dict:
    return result.model_dump(mode="json", by_alias=True, exclude_none=exclude_none)


def _node(doc: dict, node_id: str) -> dict:
    return next(c for c in doc["root"]["children"] if c["id"] == node_id)


# ============================================================
# 浅合并（SS-1）
# ============================================================


class TestStyleShallowMerge:
    """style 浅合并语义"""

    def test_merge_into_existing_style_keeps_unmentioned_keys(self):
        """已有 style 的节点：未提及键保持原值，提及键被覆盖/新增"""
        result = apply_patch(
            _doc(), _patch([_style_op({"color": "#c0392b", "padding": "16px"})])
        )
        style = _node(_dump(result), "hero.title")["style"]
        assert style["fontSize"] == "2rem"  # 未提及 → 保持
        assert style["color"] == "#c0392b"  # 提及 → 覆盖
        assert style["padding"] == "16px"  # 提及 → 新增

    def test_merge_into_node_without_style(self):
        """无 style 的节点：视作 {} 起点，直接写入"""
        result = apply_patch(
            _doc(), _patch([_style_op({"borderRadius": "8px"}, target="hero.cta")])
        )
        style = _node(_dump(result, exclude_none=True), "hero.cta")["style"]
        assert style == {"borderRadius": "8px"}

    def test_style_change_does_not_touch_props(self):
        """update_style 只影响 style，不影响 props / id / type"""
        result = apply_patch(_doc(), _patch([_style_op({"textAlign": "center"})]))
        node = _node(_dump(result), "hero.title")
        assert node["props"] == {"text": "Brew", "level": 1}
        assert node["id"] == "hero.title"
        assert node["type"] == "Heading"

    def test_non_target_nodes_unchanged(self):
        """非目标节点的 style 与 props 零变更"""
        result = apply_patch(_doc(), _patch([_style_op({"color": "#c0392b"})]))
        dumped = _dump(result, exclude_none=True)
        assert _node(dumped, "hero.sub")["style"] == {"color": "#222222"}
        assert _node(dumped, "hero.sub")["props"]["text"] == "sub"
        assert "style" not in _node(dumped, "hero.cta")

    def test_source_document_not_mutated(self):
        """源文档在应用过程中不被修改（deepcopy 保护）"""
        document = _doc()
        before = copy.deepcopy(document)
        apply_patch(document, _patch([_style_op({"color": "#c0392b"})]))
        assert document == before


# ============================================================
# null 删除语义与空归一化（SS-2 / SS-3）
# ============================================================


class TestStyleNullDeletion:
    """null 删键与空 style 归一化"""

    def test_null_removes_existing_key(self):
        """null 值删除既有键，其余键保持"""
        result = apply_patch(_doc(), _patch([_style_op({"color": None})]))
        style = _node(_dump(result, exclude_none=True), "hero.title")["style"]
        assert "color" not in style
        assert style == {"fontSize": "2rem"}

    def test_null_on_absent_key_is_idempotent_noop(self):
        """对本就不存在的键使用 null 是幂等无操作，不报错"""
        result = apply_patch(_doc(), _patch([_style_op({"gap": None})]))
        style = _node(_dump(result, exclude_none=True), "hero.title")["style"]
        assert style == {"fontSize": "2rem", "color": "#111111"}

    def test_mixed_null_and_value_in_one_operation(self):
        """同一操作中 null 与非 null 混用：各自按语义生效"""
        result = apply_patch(
            _doc(), _patch([_style_op({"color": None, "fontWeight": "bold"})])
        )
        style = _node(_dump(result, exclude_none=True), "hero.title")["style"]
        assert style == {"fontSize": "2rem", "fontWeight": "bold"}

    def test_deleting_all_keys_removes_style_key(self):
        """删完所有键 → 节点上不再有 style 键（DD-27）"""
        result = apply_patch(
            _doc(), _patch([_style_op({"fontSize": None, "color": None})])
        )
        node = _node(_dump(result, exclude_none=True), "hero.title")
        assert "style" not in node

    def test_null_on_styleless_node_leaves_no_style_key(self):
        """对无 style 节点仅发 null：结果仍无 style 键"""
        result = apply_patch(
            _doc(), _patch([_style_op({"color": None}, target="hero.cta")])
        )
        node = _node(_dump(result, exclude_none=True), "hero.cta")
        assert "style" not in node


# ============================================================
# 幂等与顺序（SS-7）
# ============================================================


class TestStyleIdempotencyAndOrder:
    """幂等重放与多条操作顺序"""

    def test_replay_is_byte_identical(self):
        """同一份 Patch 重复应用，结果文档逐字节相同（AC-06）"""
        patch = _patch([_style_op({"fontWeight": "bold"})])
        first = _dump(apply_patch(_doc(), patch))
        second = _dump(apply_patch(_doc(), patch))
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_applying_twice_in_sequence_is_stable(self):
        """连续两次应用同一操作，第二次不再改变文档"""
        patch = _patch([_style_op({"padding": "16px"})])
        once = apply_patch(_doc(), patch)
        twice = apply_patch(_dump(once, exclude_none=True), patch)
        assert json.dumps(_dump(once), sort_keys=True) == json.dumps(
            _dump(twice), sort_keys=True
        )

    def test_last_write_wins_across_operations(self):
        """多条 update_style 按数组顺序执行，后者覆盖前者同名键"""
        result = apply_patch(
            _doc(),
            _patch([_style_op({"padding": "8px"}), _style_op({"padding": "24px"})]),
        )
        assert _node(_dump(result), "hero.title")["style"]["padding"] == "24px"

    def test_null_then_value_across_operations(self):
        """先 null 删除再写入：最终结果由最后一次写入决定"""
        result = apply_patch(
            _doc(),
            _patch([_style_op({"color": None}), _style_op({"color": "#c0392b"})]),
        )
        assert _node(_dump(result), "hero.title")["style"]["color"] == "#c0392b"

    def test_value_then_null_across_operations(self):
        """先写入再 null 删除：最终该键不存在"""
        result = apply_patch(
            _doc(),
            _patch([_style_op({"gap": "12px"}), _style_op({"gap": None})]),
        )
        style = _node(_dump(result, exclude_none=True), "hero.title")["style"]
        assert "gap" not in style

    def test_operations_on_different_nodes_are_independent(self):
        """作用于不同节点的 style 操作互不影响"""
        result = apply_patch(
            _doc(),
            _patch(
                [
                    _style_op({"color": "#c0392b"}),
                    _style_op({"color": "#2980b9"}, target="hero.sub"),
                ]
            ),
        )
        dumped = _dump(result)
        assert _node(dumped, "hero.title")["style"]["color"] == "#c0392b"
        assert _node(dumped, "hero.sub")["style"]["color"] == "#2980b9"


# ============================================================
# 混合 operations（SS-8）
# ============================================================


class TestMixedOperations:
    """update_props 与 update_style 混合"""

    def test_mixed_operations_both_take_effect(self):
        """混合 ops：props 与 style 同时生效，互不干扰"""
        result = apply_patch(
            _doc(),
            _patch([_props_op({"text": "New"}), _style_op({"textAlign": "center"})]),
        )
        node = _node(_dump(result), "hero.title")
        assert node["props"]["text"] == "New"
        assert node["props"]["level"] == 1  # props 也是浅合并
        assert node["style"]["textAlign"] == "center"
        assert node["style"]["fontSize"] == "2rem"

    def test_mixed_operations_order_is_irrelevant(self):
        """混合 ops 换序结果等价（各自只影响自己的字段）"""
        props_op = _props_op({"text": "New"})
        style_op = _style_op({"textAlign": "center"})
        forward = _dump(apply_patch(_doc(), _patch([props_op, style_op])))
        reverse = _dump(apply_patch(_doc(), _patch([style_op, props_op])))
        assert json.dumps(forward, sort_keys=True) == json.dumps(
            reverse, sort_keys=True
        )

    def test_mixed_operations_across_nodes(self):
        """混合 ops 可分别作用于不同节点"""
        result = apply_patch(
            _doc(),
            _patch(
                [
                    _props_op({"text": "立即预约"}, target="hero.cta"),
                    _style_op({"backgroundColor": "#111111"}, target="hero.cta"),
                ]
            ),
        )
        node = _node(_dump(result), "hero.cta")
        assert node["props"]["text"] == "立即预约"
        assert node["style"]["backgroundColor"] == "#111111"

    def test_pure_update_props_behavior_unchanged(self):
        """纯 update_props 行为回归：不产生 style 键"""
        result = apply_patch(_doc(), _patch([_props_op({"text": "New"})]))
        dumped = _dump(result, exclude_none=True)
        assert _node(dumped, "hero.title")["props"]["text"] == "New"
        assert _node(dumped, "hero.title")["style"] == {
            "fontSize": "2rem",
            "color": "#111111",
        }
        assert "style" not in _node(dumped, "hero.cta")


# ============================================================
# 反向：结构与值域拒绝（SS-4 ~ SS-6 / SS-9）
# ============================================================


class TestStyleApplyNegative:
    """非法 style 操作被拒且文档零变更"""

    @pytest.mark.parametrize(
        "bad_style,expected_issue,desc",
        [
            ({"boxShadow": "1px 1px"}, "unknown_style_key", "未知键"),
            ({"position": "absolute"}, "unknown_style_key", "布局逃逸键"),
            ({"--custom": "1px"}, "unknown_style_key", "CSS 变量"),
            ({}, "empty_style", "空 style"),
            ({"fontSize": "16"}, "invalid_style_value", "缺单位"),
            ({"color": "red"}, "invalid_style_value", "非白名单命名色"),
            ({"fontWeight": "800"}, "invalid_style_value", "字重非枚举"),
            ({"fontSize": 16}, "invalid_style_value", "数字值"),
        ],
    )
    def test_invalid_style_rejected_with_stable_issue_code(
        self, bad_style, expected_issue: str, desc: str
    ):
        """非法 style 在结构闸门被拒: {desc}"""
        document = _doc()
        before = copy.deepcopy(document)
        with pytest.raises(PatchError) as exc_info:
            apply_patch(document, _patch([_style_op(bad_style)]))
        assert exc_info.value.code == "invalid_patch_structure"
        assert expected_issue in [i.code for i in exc_info.value.issues]
        assert document == before

    def test_style_target_not_found(self):
        """style 操作的目标节点不存在 → patch_target_not_found"""
        document = _doc()
        before = copy.deepcopy(document)
        with pytest.raises(PatchError) as exc_info:
            apply_patch(document, _patch([_style_op({"color": "#000000"}, target="ghost")]))
        assert exc_info.value.code == "patch_target_not_found"
        assert document == before

    def test_mixed_patch_rejected_atomically_when_style_invalid(self):
        """混合 Patch 中任一 style 非法 → 整体被拒，props 部分也不生效"""
        document = _doc()
        before = copy.deepcopy(document)
        with pytest.raises(PatchError) as exc_info:
            apply_patch(
                document,
                _patch([_props_op({"text": "New"}), _style_op({"boxShadow": "1px"})]),
            )
        assert exc_info.value.code == "invalid_patch_structure"
        assert document == before

    def test_style_written_into_props_still_rejected(self):
        """把 style 塞进 props 仍然非法（应用后 DSL 校验兜底，SS-10）"""
        document = _doc()
        before = copy.deepcopy(document)
        with pytest.raises(PatchError) as exc_info:
            apply_patch(document, _patch([_props_op({"style": {"color": "#000000"}})]))
        assert exc_info.value.code == "invalid_patched_document"
        assert document == before

    def test_patched_document_passes_full_dsl_validation(self):
        """成功路径返回的是通过全量 DSL 校验的 DslDocument"""
        result = apply_patch(_doc(), _patch([_style_op({"color": "#c0392b"})]))
        assert result.version == "0.1"
        target = result.root.children[0]
        assert target.style is not None
        assert target.style.color == "#c0392b"
