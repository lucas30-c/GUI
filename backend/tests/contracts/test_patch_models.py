"""
Patch v0.1 模型测试 — 正向与反向校验

覆盖：
- 合法 Patch 结构解析（正向 5+）
- 非法 Patch 结构拒绝（反向 17+）
"""

import pytest
from pydantic import ValidationError

from genui_api.patch import PatchDocument, UpdatePropsOperation, export_patch_schema


# ============================================================
# 正向测试
# ============================================================


class TestPatchModelPositive:
    """Patch 模型正向测试"""

    def test_minimal_valid_patch(self):
        """最小合法 Patch 能被正确解析"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "hero-title",
                    "props": {"text": "Hello"},
                }
            ],
        }
        doc = PatchDocument.model_validate(data)
        assert doc.version == "0.1"
        assert len(doc.operations) == 1
        assert doc.operations[0].op == "update_props"
        assert doc.operations[0].target_node_id == "hero-title"
        assert doc.operations[0].props == {"text": "Hello"}

    def test_multi_operation_patch(self):
        """多操作 Patch 能被正确解析"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "node-a",
                    "props": {"text": "A"},
                },
                {
                    "op": "update_props",
                    "targetNodeId": "node-b",
                    "props": {"text": "B"},
                },
                {
                    "op": "update_props",
                    "targetNodeId": "node-c",
                    "props": {"value": 42},
                },
            ],
        }
        doc = PatchDocument.model_validate(data)
        assert len(doc.operations) == 3
        assert doc.operations[0].target_node_id == "node-a"
        assert doc.operations[1].target_node_id == "node-b"
        assert doc.operations[2].target_node_id == "node-c"

    def test_alias_serialization_uses_camel_case(self):
        """序列化时 targetNodeId 使用 camelCase 别名"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "my-node",
                    "props": {"text": "test"},
                }
            ],
        }
        doc = PatchDocument.model_validate(data)
        serialized = doc.model_dump(mode="json", by_alias=True)
        op = serialized["operations"][0]
        assert "targetNodeId" in op
        assert "target_node_id" not in op

    @pytest.mark.parametrize(
        "props_value,desc",
        [
            ({"text": "string value"}, "字符串"),
            ({"count": 42}, "整数"),
            ({"ratio": 3.14}, "浮点数"),
            ({"enabled": True}, "布尔值"),
            ({"data": None}, "null"),
            ({"items": [1, "two", True, None]}, "数组"),
            ({"nested": {"a": 1, "b": "two"}}, "嵌套对象"),
            ({"mixed": {"arr": [1, {"x": 2}], "val": "ok"}}, "混合复杂结构"),
        ],
    )
    def test_valid_json_props_values(self, props_value: dict, desc: str):
        """props 中支持各种合法 JSON 值: {desc}"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "some-node",
                    "props": props_value,
                }
            ],
        }
        doc = PatchDocument.model_validate(data)
        assert doc.operations[0].props == props_value

    def test_schema_can_be_exported(self):
        """JSON Schema 可以从模型正确导出"""
        schema_str = export_patch_schema()
        assert isinstance(schema_str, str)
        import json

        schema = json.loads(schema_str)
        assert schema.get("x-patch-version") == "0.1"
        assert "properties" in schema
        assert "version" in schema["properties"]
        assert "operations" in schema["properties"]


# ============================================================
# 反向测试
# ============================================================


class TestPatchModelNegative:
    """Patch 模型反向测试"""

    def test_top_level_not_object(self):
        """顶层不是对象时拒绝"""
        with pytest.raises(ValidationError):
            PatchDocument.model_validate([1, 2, 3])

    def test_version_missing(self):
        """缺少 version 字段时拒绝"""
        data = {
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "n",
                    "props": {"x": 1},
                }
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            PatchDocument.model_validate(data)
        errors = exc_info.value.errors()
        assert any("version" in str(e.get("loc", "")) for e in errors)

    @pytest.mark.parametrize(
        "bad_version",
        ["0.2", "1.0", "0.1.0", "", "v0.1", 0.1, 1, None],
    )
    def test_version_not_0_1(self, bad_version):
        """version 不为 "0.1" 时拒绝"""
        data = {
            "version": bad_version,
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "n",
                    "props": {"x": 1},
                }
            ],
        }
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    def test_operations_missing(self):
        """缺少 operations 字段时拒绝"""
        data = {"version": "0.1"}
        with pytest.raises(ValidationError) as exc_info:
            PatchDocument.model_validate(data)
        errors = exc_info.value.errors()
        assert any("operations" in str(e.get("loc", "")) for e in errors)

    def test_operations_empty_array(self):
        """operations 为空数组时拒绝"""
        data = {"version": "0.1", "operations": []}
        with pytest.raises(ValidationError) as exc_info:
            PatchDocument.model_validate(data)
        errors = exc_info.value.errors()
        assert any("too_short" in e.get("type", "") for e in errors)

    def test_operations_not_array(self):
        """operations 不是数组时拒绝"""
        data = {"version": "0.1", "operations": "not-array"}
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    def test_operation_not_object(self):
        """operation 元素不是对象时拒绝"""
        data = {"version": "0.1", "operations": ["string-item"]}
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    @pytest.mark.parametrize(
        "bad_op",
        ["delete_node", "add_node", "move", "replace", "UPDATE_PROPS", ""],
    )
    def test_unknown_op(self, bad_op):
        """未知 op 值时拒绝"""
        data = {
            "version": "0.1",
            "operations": [
                {"op": bad_op, "targetNodeId": "node-1", "props": {"x": 1}}
            ],
        }
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    def test_target_node_id_missing(self):
        """缺少 targetNodeId 时拒绝"""
        data = {
            "version": "0.1",
            "operations": [{"op": "update_props", "props": {"x": 1}}],
        }
        with pytest.raises(ValidationError) as exc_info:
            PatchDocument.model_validate(data)
        errors = exc_info.value.errors()
        assert any(
            "targetNodeId" in str(e.get("loc", "")) or "target_node_id" in str(e.get("loc", ""))
            for e in errors
        )

    def test_target_node_id_empty_string(self):
        """targetNodeId 为空字符串时拒绝"""
        data = {
            "version": "0.1",
            "operations": [
                {"op": "update_props", "targetNodeId": "", "props": {"x": 1}}
            ],
        }
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    @pytest.mark.parametrize("whitespace", [" ", "  ", "\t", "\n", " \t\n "])
    def test_target_node_id_whitespace_only(self, whitespace):
        """targetNodeId 为纯空白字符串时拒绝"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": whitespace,
                    "props": {"x": 1},
                }
            ],
        }
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    def test_props_missing(self):
        """缺少 props 字段时拒绝"""
        data = {
            "version": "0.1",
            "operations": [
                {"op": "update_props", "targetNodeId": "node-1"}
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            PatchDocument.model_validate(data)
        errors = exc_info.value.errors()
        assert any("props" in str(e.get("loc", "")) for e in errors)

    @pytest.mark.parametrize(
        "bad_props",
        ["string", 123, True, None, [1, 2, 3]],
    )
    def test_props_not_object(self, bad_props):
        """props 不是对象时拒绝"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "node-1",
                    "props": bad_props,
                }
            ],
        }
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    def test_props_empty_dict(self):
        """props 为空对象时拒绝"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "node-1",
                    "props": {},
                }
            ],
        }
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    def test_unknown_top_level_field(self):
        """包含未知顶层字段时拒绝（extra=forbid）"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "n",
                    "props": {"x": 1},
                }
            ],
            "unknownField": "should-fail",
        }
        with pytest.raises(ValidationError) as exc_info:
            PatchDocument.model_validate(data)
        errors = exc_info.value.errors()
        assert any("extra" in e.get("type", "") for e in errors)

    def test_unknown_operation_field(self):
        """操作中包含未知字段时拒绝（extra=forbid）"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "n",
                    "props": {"x": 1},
                    "extraField": "bad",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            PatchDocument.model_validate(data)
        errors = exc_info.value.errors()
        assert any("extra" in e.get("type", "") for e in errors)

    def test_props_non_json_serializable_value(self):
        """props 包含非 JSON 兼容值时拒绝"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "node-1",
                    "props": {"func": lambda: None},
                }
            ],
        }
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)

    def test_props_non_json_set_value(self):
        """props 包含 set 类型值时拒绝"""
        data = {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "node-1",
                    "props": {"tags": {1, 2, 3}},
                }
            ],
        }
        with pytest.raises(ValidationError):
            PatchDocument.model_validate(data)
