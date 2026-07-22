"""
Patch v0.1 应用核心测试 — 正向、反向、不可变性、原子性

覆盖：
- 正向：单操作/多操作/深层节点/浅合并/Gold Case（12+）
- 反向：源文档非法/目标不存在/后校验失败/原子性（14+）
"""

import copy
import json
from pathlib import Path

import pytest

from genui_api.contracts.dsl import DslDocument
from genui_api.contracts.validation import validate_dsl_document
from genui_api.patch import PatchError, apply_patch

# ============================================================
# 测试数据
# ============================================================

GOLD_CASE_PATH = (
    Path(__file__).resolve().parents[3] / "examples" / "dsl" / "coffee-shop-landing.json"
)


def load_gold_case() -> dict:
    return json.loads(GOLD_CASE_PATH.read_text())


MINIMAL_DSL = {
    "version": "0.1",
    "root": {
        "id": "page",
        "type": "Page",
        "props": {"title": "Test Page"},
        "children": [
            {
                "id": "heading-1",
                "type": "Heading",
                "props": {"text": "Hello", "level": 1},
            }
        ],
    },
}

NESTED_DSL = {
    "version": "0.1",
    "root": {
        "id": "page",
        "type": "Page",
        "props": {"title": "Test"},
        "children": [
            {
                "id": "section-1",
                "type": "Section",
                "props": {},
                "children": [
                    {
                        "id": "card-1",
                        "type": "Card",
                        "props": {},
                        "children": [
                            {
                                "id": "deep-text",
                                "type": "Text",
                                "props": {"text": "Deep content"},
                            }
                        ],
                    }
                ],
            }
        ],
    },
}


def make_patch(operations: list) -> dict:
    """构造 Patch 文档"""
    return {"version": "0.1", "operations": operations}


def single_op(target: str, props: dict) -> dict:
    """构造单个 update_props 操作"""
    return {"op": "update_props", "targetNodeId": target, "props": props}


# ============================================================
# 正向测试
# ============================================================


class TestPatchApplyPositive:
    """Patch 应用正向测试"""

    def test_update_root_node_props(self):
        """更新根节点 (Page) props 成功"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([single_op("page", {"title": "New Title"})])
        result = apply_patch(doc, patch)
        assert isinstance(result, DslDocument)
        assert result.root.props.title == "New Title"

    def test_update_deep_node_props(self):
        """更新深层嵌套节点 props 成功"""
        doc = copy.deepcopy(NESTED_DSL)
        patch = make_patch([single_op("deep-text", {"text": "Updated deep"})])
        result = apply_patch(doc, patch)
        # 获取深层节点
        deep_node = result.root.children[0].children[0].children[0]
        assert deep_node.props.text == "Updated deep"

    def test_unspecified_props_remain_unchanged(self):
        """未在 patch 中出现的 props 字段保持不变"""
        doc = copy.deepcopy(MINIMAL_DSL)
        # heading-1 有 text 和 level，只更新 text
        patch = make_patch([single_op("heading-1", {"text": "Updated"})])
        result = apply_patch(doc, patch)
        heading = result.root.children[0]
        assert heading.props.text == "Updated"
        assert heading.props.level == 1  # 保持不变

    def test_non_target_nodes_unchanged(self):
        """非目标节点保持不变"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([single_op("heading-1", {"text": "Changed"})])
        result = apply_patch(doc, patch)
        assert result.root.props.title == "Test Page"  # Page 未被修改

    def test_multi_operations_execute_in_order(self):
        """多操作按数组顺序执行"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([
            single_op("page", {"title": "First"}),
            single_op("heading-1", {"text": "Second"}),
        ])
        result = apply_patch(doc, patch)
        assert result.root.props.title == "First"
        assert result.root.children[0].props.text == "Second"

    def test_same_node_multi_operations(self):
        """同一节点多操作按顺序执行"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([
            single_op("heading-1", {"text": "First update"}),
            single_op("heading-1", {"text": "Second update"}),
        ])
        result = apply_patch(doc, patch)
        assert result.root.children[0].props.text == "Second update"

    def test_same_field_last_writer_wins(self):
        """同一字段多次更新时最后一个获胜（last writer wins）"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([
            single_op("page", {"title": "A"}),
            single_op("page", {"title": "B"}),
            single_op("page", {"title": "C"}),
        ])
        result = apply_patch(doc, patch)
        assert result.root.props.title == "C"

    def test_result_passes_full_dsl_validation(self):
        """结果通过完整 DSL 校验"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([single_op("heading-1", {"text": "Valid text"})])
        result = apply_patch(doc, patch)
        # 再次用 validate_dsl_document 验证
        revalidated = validate_dsl_document(result.model_dump(mode="json"))
        assert isinstance(revalidated, DslDocument)

    def test_gold_case_apply_valid_patch(self):
        """Gold Case 能成功应用合法 Patch"""
        doc = load_gold_case()
        patch = make_patch([
            single_op("hero.title", {"text": "新咖啡店", "level": 1}),
        ])
        result = apply_patch(doc, patch)
        assert isinstance(result, DslDocument)
        # 验证修改生效
        hero_section = result.root.children[0]
        hero_title = hero_section.children[0]
        assert hero_title.props.text == "新咖啡店"

    def test_original_dict_unchanged_after_success(self):
        """成功后原始 dict 输入保持不变"""
        doc = copy.deepcopy(MINIMAL_DSL)
        original_snapshot = copy.deepcopy(doc)
        patch = make_patch([single_op("heading-1", {"text": "Changed"})])
        apply_patch(doc, patch)
        assert doc == original_snapshot

    def test_original_document_unchanged_with_model_input(self):
        """使用模型转换的 dict 作为输入，原始也不应被修改"""
        doc_dict = copy.deepcopy(MINIMAL_DSL)
        original_snapshot = copy.deepcopy(doc_dict)
        patch = make_patch([single_op("page", {"title": "Changed"})])
        apply_patch(doc_dict, patch)
        assert doc_dict == original_snapshot

    def test_returned_document_no_shared_mutable_refs(self):
        """返回文档不与原始输入共享可变引用"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([single_op("heading-1", {"text": "Returned"})])
        result = apply_patch(doc, patch)
        # 修改返回的文档不应影响原始
        result_dict = result.model_dump(mode="json")
        result_dict["root"]["props"]["title"] = "MODIFIED"
        assert doc["root"]["props"]["title"] == "Test Page"


# ============================================================
# 反向测试
# ============================================================


class TestPatchApplyNegative:
    """Patch 应用反向测试"""

    def test_invalid_source_document(self):
        """源文档非法 → invalid_source_document"""
        bad_doc = {"version": "0.1", "root": {"id": "x", "type": "Heading", "props": {"text": "t", "level": 1}}}
        patch = make_patch([single_op("x", {"text": "new"})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(bad_doc, patch)
        assert exc_info.value.code == "invalid_source_document"
        assert len(exc_info.value.issues) > 0

    def test_target_node_not_found(self):
        """targetNodeId 不存在 → patch_target_not_found"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([single_op("nonexistent-id", {"text": "x"})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        assert exc_info.value.code == "patch_target_not_found"
        assert exc_info.value.issues[0].code == "target_not_found"
        assert "operations[0].targetNodeId" in exc_info.value.issues[0].path

    def test_unknown_props_field_causes_invalid_patched(self):
        """未知 props 字段 → invalid_patched_document"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([single_op("heading-1", {"unknownField": "bad"})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        assert exc_info.value.code == "invalid_patched_document"

    def test_props_type_error_causes_invalid_patched(self):
        """props 类型错误 → invalid_patched_document"""
        doc = copy.deepcopy(MINIMAL_DSL)
        # level 应该是 int，给 string
        patch = make_patch([single_op("heading-1", {"level": "not-a-number"})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        assert exc_info.value.code == "invalid_patched_document"

    def test_null_violates_target_model(self):
        """null 违反目标模型约束 → 适当错误"""
        doc = copy.deepcopy(MINIMAL_DSL)
        # text 是必填 str，设为 null
        patch = make_patch([single_op("heading-1", {"text": None})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        assert exc_info.value.code == "invalid_patched_document"

    def test_middle_operation_fails_entire_patch_fails(self):
        """中间操作失败 → 整个 Patch 失败"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([
            single_op("heading-1", {"text": "Good"}),
            single_op("nonexistent", {"text": "Bad"}),
            single_op("page", {"title": "Also good"}),
        ])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        assert exc_info.value.code == "patch_target_not_found"

    def test_last_operation_fails_no_partial_result(self):
        """最后一个操作失败 → 不返回前面操作的部分结果"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([
            single_op("heading-1", {"text": "Partial should not persist"}),
            single_op("heading-1", {"unknownProp": "will-fail-post-validation"}),
        ])
        with pytest.raises(PatchError):
            apply_patch(doc, patch)
        # 确认没有部分结果泄露
        assert doc["root"]["children"][0]["props"]["text"] == "Hello"

    def test_after_failure_original_unchanged(self):
        """失败后原始文档完全未被修改"""
        doc = copy.deepcopy(MINIMAL_DSL)
        original_snapshot = copy.deepcopy(doc)
        patch = make_patch([single_op("nonexistent", {"text": "x"})])
        with pytest.raises(PatchError):
            apply_patch(doc, patch)
        assert doc == original_snapshot

    def test_issue_path_locates_operation(self):
        """issue.path 能定位到具体的 Patch 操作"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([
            single_op("heading-1", {"text": "ok"}),
            single_op("not-found", {"text": "bad"}),
        ])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        assert "operations[1].targetNodeId" in exc_info.value.issues[0].path

    def test_post_patch_dsl_issue_code_preserved(self):
        """后校验 DSL issue.code 被保留"""
        doc = copy.deepcopy(MINIMAL_DSL)
        # 添加一个会导致 schema_error 的修改
        patch = make_patch([single_op("heading-1", {"text": None})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        assert exc_info.value.code == "invalid_patched_document"
        # issues 中应保留 DSL 错误码
        assert len(exc_info.value.issues) > 0
        assert exc_info.value.issues[0].code == "schema_error"

    def test_error_no_traceback(self):
        """错误消息不包含 traceback"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([single_op("nonexistent", {"text": "x"})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        error = exc_info.value
        error_str = f"{error.code} {error.message} " + " ".join(
            f"{i.path} {i.code} {i.message}" for i in error.issues
        )
        assert "Traceback" not in error_str
        assert "traceback" not in error_str.lower() or "traceback" not in error.message.lower()

    def test_error_no_system_paths(self):
        """错误消息不包含系统文件路径"""
        doc = copy.deepcopy(MINIMAL_DSL)
        patch = make_patch([single_op("nonexistent", {"text": "x"})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        error = exc_info.value
        error_str = f"{error.code} {error.message} " + " ".join(
            f"{i.path} {i.code} {i.message}" for i in error.issues
        )
        assert "/Users/" not in error_str
        assert "/home/" not in error_str
        assert "\\Users\\" not in error_str
        assert ".py" not in error_str

    def test_error_no_full_original_dsl(self):
        """错误消息不包含完整原始 DSL"""
        doc = load_gold_case()
        patch = make_patch([single_op("nonexistent-node-id", {"text": "x"})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        error = exc_info.value
        error_str = f"{error.message} " + " ".join(
            i.message for i in error.issues
        )
        # 不应包含 Gold Case 中的大段内容
        assert "Brew & Bean" not in error_str
        assert "coffee-shop-landing" not in error_str

    def test_error_no_full_patch_content(self):
        """错误消息不包含完整 Patch 内容"""
        doc = copy.deepcopy(MINIMAL_DSL)
        long_text = "A" * 500
        patch = make_patch([single_op("nonexistent", {"text": long_text})])
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, patch)
        error = exc_info.value
        error_str = f"{error.message} " + " ".join(
            i.message for i in error.issues
        )
        assert long_text not in error_str
