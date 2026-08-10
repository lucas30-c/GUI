"""
Patch v0.1 `update_style` 契约测试（Spec 010 P-1 / AC-01 ~ AC-04）

覆盖：
- `update_style` 正向解析、混合 operations、纯 `update_props` 回归
- 反向：未知键 / 空 style / 非法值 / 非字符串值 / 缺 style / style 非对象 /
  额外键 / 空 targetNodeId / 未注册 op
- discriminated union 行为与 issue.code 归属
- 11 字段白名单与 DSL `Style` 的单一事实来源一致性
"""

import json

import pytest
from pydantic import ValidationError

from genui_api.contracts.dsl import Style
from genui_api.patch import (
    PatchDocument,
    UpdatePropsOperation,
    UpdateStyleOperation,
    export_patch_schema,
)
from genui_api.patch.apply import PatchError, _validate_patch_structure


# ============================================================
# 夹具
# ============================================================


def _patch(operations: list) -> dict:
    return {"version": "0.1", "operations": operations}


def _style_op(style, target: str = "hero.title") -> dict:
    return {"op": "update_style", "targetNodeId": target, "style": style}


def _props_op(props=None, target: str = "hero.title") -> dict:
    return {
        "op": "update_props",
        "targetNodeId": target,
        "props": props if props is not None else {"text": "Brew"},
    }


def _issue_codes(patch: dict) -> list[str]:
    """通过 apply 层的结构校验入口取回稳定的 issue.code 列表"""
    with pytest.raises(PatchError) as exc_info:
        _validate_patch_structure(patch)
    assert exc_info.value.code == "invalid_patch_structure"
    return [issue.code for issue in exc_info.value.issues]


# ============================================================
# 正向：update_style
# ============================================================


class TestUpdateStylePositive:
    """update_style 正向测试"""

    def test_minimal_update_style_patch(self):
        """最小合法 update_style Patch 能被解析"""
        doc = PatchDocument.model_validate(_patch([_style_op({"color": "#c0392b"})]))
        assert len(doc.operations) == 1
        op = doc.operations[0]
        assert isinstance(op, UpdateStyleOperation)
        assert op.op == "update_style"
        assert op.target_node_id == "hero.title"
        assert op.style.color == "#c0392b"

    @pytest.mark.parametrize(
        "style,desc",
        [
            ({"color": "#fff"}, "3 位 hex"),
            ({"color": "black"}, "命名色"),
            ({"backgroundColor": "transparent"}, "透明背景"),
            ({"fontSize": "2rem"}, "rem 尺寸"),
            ({"fontSize": "16px"}, "px 尺寸"),
            ({"width": "100%"}, "百分比"),
            ({"height": "1.5em"}, "小数 em"),
            ({"fontWeight": "bold"}, "字重枚举"),
            ({"textAlign": "center"}, "对齐枚举"),
            ({"padding": "8px"}, "内边距"),
            ({"margin": "0px"}, "外边距"),
            ({"borderRadius": "4px"}, "圆角"),
            ({"gap": "12px"}, "间距"),
        ],
    )
    def test_valid_style_values_accepted(self, style: dict, desc: str):
        """合法 style 值被接受: {desc}"""
        doc = PatchDocument.model_validate(_patch([_style_op(style)]))
        key, value = next(iter(style.items()))
        assert getattr(doc.operations[0].style, key) == value

    def test_all_eleven_fields_in_one_operation(self):
        """一次操作可同时写入全部 11 个白名单字段"""
        style = {
            "color": "#111111",
            "backgroundColor": "#ffffff",
            "fontSize": "2rem",
            "fontWeight": "bold",
            "textAlign": "center",
            "width": "100%",
            "height": "48px",
            "padding": "16px",
            "margin": "0px",
            "borderRadius": "8px",
            "gap": "12px",
        }
        doc = PatchDocument.model_validate(_patch([_style_op(style)]))
        assert doc.operations[0].style.model_fields_set == set(style)

    def test_explicit_null_value_is_preserved_as_set_field(self):
        """显式 null 被保留为「已设置」字段（DD-07 删除语义的前提）"""
        doc = PatchDocument.model_validate(_patch([_style_op({"color": None})]))
        style = doc.operations[0].style
        assert style.model_fields_set == {"color"}
        assert style.model_dump(exclude_unset=True) == {"color": None}

    def test_unset_fields_excluded_from_dump(self):
        """未提及字段不出现在 exclude_unset dump 中（浅合并只影响提及的键）"""
        doc = PatchDocument.model_validate(_patch([_style_op({"fontSize": "2rem"})]))
        dumped = doc.operations[0].style.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        assert dumped == {"fontSize": "2rem"}

    def test_alias_serialization_uses_camel_case(self):
        """序列化使用 camelCase 别名，与 wire 契约一致"""
        doc = PatchDocument.model_validate(_patch([_style_op({"color": "#000000"})]))
        serialized = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
        op = serialized["operations"][0]
        assert op["op"] == "update_style"
        assert "targetNodeId" in op and "target_node_id" not in op
        assert op["style"] == {"color": "#000000"}

    def test_multiple_update_style_operations(self):
        """多条 update_style 操作能被解析并保持数组顺序"""
        doc = PatchDocument.model_validate(
            _patch(
                [
                    _style_op({"padding": "8px"}),
                    _style_op({"padding": "24px"}),
                ]
            )
        )
        assert [op.style.padding for op in doc.operations] == ["8px", "24px"]


# ============================================================
# 正向：混合 operations 与既有 update_props 回归
# ============================================================


class TestMixedAndLegacyOperations:
    """混合 operations 与纯 update_props 回归"""

    def test_mixed_operations_accepted(self):
        """update_props + update_style 可同时出现在一份 Patch 中"""
        doc = PatchDocument.model_validate(
            _patch([_props_op({"text": "New"}), _style_op({"textAlign": "center"})])
        )
        assert [op.op for op in doc.operations] == ["update_props", "update_style"]
        assert isinstance(doc.operations[0], UpdatePropsOperation)
        assert isinstance(doc.operations[1], UpdateStyleOperation)

    def test_mixed_operations_reverse_order_accepted(self):
        """混合 operations 换序同样合法"""
        doc = PatchDocument.model_validate(
            _patch([_style_op({"textAlign": "center"}), _props_op({"text": "New"})])
        )
        assert [op.op for op in doc.operations] == ["update_style", "update_props"]

    def test_pure_update_props_patch_unchanged(self):
        """纯 update_props Patch 行为回归（引入 union 后语义不变）"""
        doc = PatchDocument.model_validate(_patch([_props_op({"text": "Hello"})]))
        assert isinstance(doc.operations[0], UpdatePropsOperation)
        assert doc.operations[0].props == {"text": "Hello"}

    def test_props_may_still_carry_arbitrary_json(self):
        """update_props 的 props 仍接受任意 JSON 兼容值（不受 Style 约束影响）"""
        doc = PatchDocument.model_validate(
            _patch([_props_op({"items": [1, "two", True, None], "n": {"a": 1}})])
        )
        assert doc.operations[0].props["items"] == [1, "two", True, None]

    def test_version_remains_0_1(self):
        """加法扩展不提升 Patch 版本号（DD-25）"""
        doc = PatchDocument.model_validate(_patch([_style_op({"color": "#000000"})]))
        assert doc.version == "0.1"
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(
                {"version": "0.2", "operations": [_style_op({"color": "#000000"})]}
            )


# ============================================================
# 反向：style 结构与值域
# ============================================================


class TestUpdateStyleNegative:
    """update_style 反向测试"""

    @pytest.mark.parametrize(
        "unknown_key",
        ["boxShadow", "position", "zIndex", "content", "--custom", "props", "style"],
    )
    def test_unknown_style_key_rejected(self, unknown_key: str):
        """未知 style 键被拒（Style.extra=forbid）→ unknown_style_key"""
        patch = _patch([_style_op({unknown_key: "1px"})])
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        assert "unknown_style_key" in _issue_codes(patch)

    def test_empty_style_rejected(self):
        """空 style 对象被拒（操作必须有效果）→ empty_style"""
        patch = _patch([_style_op({})])
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        assert _issue_codes(patch) == ["empty_style"]

    @pytest.mark.parametrize(
        "style,desc",
        [
            ({"fontSize": "16"}, "缺单位"),
            ({"fontSize": "16pt"}, "非法单位"),
            ({"color": "red"}, "非白名单命名色"),
            ({"color": "rgb(1,2,3)"}, "函数式颜色"),
            ({"backgroundColor": "#12"}, "hex 位数不足"),
            ({"backgroundColor": "#GGGGGG"}, "非 hex 字符"),
            ({"fontWeight": "800"}, "字重非枚举"),
            ({"textAlign": "justify"}, "对齐非枚举"),
            ({"width": "calc(100% - 2px)"}, "calc 表达式"),
            ({"padding": "8px 16px"}, "多值简写"),
        ],
    )
    def test_invalid_style_value_rejected(self, style: dict, desc: str):
        """非法 style 值被拒: {desc} → invalid_style_value"""
        patch = _patch([_style_op(style)])
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        assert "invalid_style_value" in _issue_codes(patch)

    @pytest.mark.parametrize(
        "bad_value",
        [16, 16.5, True, ["16px"], {"value": "16px"}],
    )
    def test_non_string_style_value_rejected(self, bad_value):
        """非字符串 style 值被拒（wire 值域为 str | None）"""
        patch = _patch([_style_op({"fontSize": bad_value})])
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        assert "invalid_style_value" in _issue_codes(patch)

    def test_style_field_missing_rejected(self):
        """update_style 缺少 style 字段时拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            PatchDocument.model_validate(
                _patch([{"op": "update_style", "targetNodeId": "hero.title"}])
            )
        assert any("style" in str(e.get("loc", "")) for e in exc_info.value.errors())

    @pytest.mark.parametrize("bad_style", ["color:#fff", 123, True, None, [1, 2]])
    def test_style_not_object_rejected(self, bad_style):
        """style 不是对象时拒绝"""
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(_patch([_style_op(bad_style)]))

    def test_extra_field_on_update_style_rejected(self):
        """update_style 含未知顶层字段时拒绝（extra=forbid）"""
        patch = _patch(
            [
                {
                    "op": "update_style",
                    "targetNodeId": "hero.title",
                    "style": {"color": "#000000"},
                    "props": {"text": "x"},
                }
            ]
        )
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        assert "unknown_field" in _issue_codes(patch)

    def test_update_style_target_node_id_missing_rejected(self):
        """update_style 缺少 targetNodeId 时拒绝"""
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(
                _patch([{"op": "update_style", "style": {"color": "#000000"}}])
            )

    @pytest.mark.parametrize("bad_target", [" ", "\t", "\n", " \t\n "])
    def test_update_style_whitespace_target_node_id_rejected(self, bad_target: str):
        """update_style 的 targetNodeId 为纯空白时拒绝 → empty_target_node_id"""
        patch = _patch([_style_op({"color": "#000000"}, target=bad_target)])
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        assert "empty_target_node_id" in _issue_codes(patch)

    def test_update_style_empty_target_node_id_rejected(self):
        """update_style 的 targetNodeId 为空字符串时拒绝（min_length=1）

        注：空字符串命中 min_length，其 issue.code 归类沿用 update_props 既有行为
        （`operations` + `too_short` 分支先命中），本轮不改动该既有映射。
        """
        patch = _patch([_style_op({"color": "#000000"}, target="")])
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        with pytest.raises(PatchError) as exc_info:
            _validate_patch_structure(patch)
        assert exc_info.value.code == "invalid_patch_structure"


# ============================================================
# discriminated union 行为
# ============================================================


class TestOperationDiscriminator:
    """PatchOperation discriminated union 行为（DD-04 / DD-28）"""

    @pytest.mark.parametrize(
        "bad_op",
        ["update_styles", "UPDATE_STYLE", "delete_node", "add_node", "move", "replace", ""],
    )
    def test_unregistered_op_maps_to_invalid_op(self, bad_op: str):
        """未注册 op 被拒且 issue.code 仍为 invalid_op"""
        patch = _patch(
            [{"op": bad_op, "targetNodeId": "hero.title", "props": {"text": "x"}}]
        )
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        assert "invalid_op" in _issue_codes(patch)

    def test_missing_op_maps_to_invalid_op(self):
        """缺少 op 标签时 issue.code 仍为 invalid_op"""
        patch = _patch([{"targetNodeId": "hero.title", "props": {"text": "x"}}])
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(patch)
        assert "invalid_op" in _issue_codes(patch)

    def test_op_dispatch_selects_correct_model(self):
        """op 标签决定被实例化的模型，字段不可跨类型混用"""
        # update_style 不接受 props 字段
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(
                _patch(
                    [
                        {
                            "op": "update_style",
                            "targetNodeId": "n",
                            "props": {"text": "x"},
                        }
                    ]
                )
            )
        # update_props 不接受 style 字段
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(
                _patch(
                    [
                        {
                            "op": "update_props",
                            "targetNodeId": "n",
                            "style": {"color": "#000000"},
                        }
                    ]
                )
            )

    def test_empty_operations_still_rejected(self):
        """operations 为空数组仍被拒（union 引入不影响 min_length）"""
        assert _issue_codes({"version": "0.1", "operations": []}) == ["empty_operations"]


# ============================================================
# 白名单单一事实来源
# ============================================================


class TestStyleWhitelistSingleSource:
    """11 字段白名单只有一个事实来源（DD-02）"""

    def test_patch_style_annotation_is_dsl_style(self):
        """UpdateStyleOperation.style 的注解就是 DSL 的 Style 模型"""
        assert UpdateStyleOperation.model_fields["style"].annotation is Style

    def test_whitelist_has_exactly_eleven_fields(self):
        """白名单恰为 11 个字段"""
        assert len(Style.model_fields) == 11
        assert set(Style.model_fields) == {
            "color",
            "backgroundColor",
            "fontSize",
            "fontWeight",
            "textAlign",
            "width",
            "height",
            "padding",
            "margin",
            "borderRadius",
            "gap",
        }

    def test_exported_schema_declares_update_style(self):
        """导出的 JSON Schema 声明 update_style 且版本仍为 0.1"""
        schema = json.loads(export_patch_schema())
        assert schema["x-patch-version"] == "0.1"
        assert "UpdateStyleOperation" in schema["$defs"]
        assert "Style" in schema["$defs"]
        items = schema["properties"]["operations"]["items"]
        assert items["discriminator"]["propertyName"] == "op"
        assert set(items["discriminator"]["mapping"]) == {
            "update_props",
            "update_style",
        }
        assert schema["$defs"]["Style"]["additionalProperties"] is False

    def test_exported_schema_is_deterministic(self):
        """导出确定性：两次调用逐字节一致"""
        assert export_patch_schema() == export_patch_schema()
