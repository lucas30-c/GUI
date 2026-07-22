"""
Patch v0.1 应用核心

提供 apply_patch() 入口：校验 → 深拷贝 → 定位节点 → 浅合并 props → 后校验。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from genui_api.contracts.dsl import DslDocument
from genui_api.contracts.validation import DslValidationError, validate_dsl_document

from .models import PatchDocument

# ============================================================
# 错误体系
# ============================================================


@dataclass
class PatchIssue:
    """单条 Patch 错误明细"""

    path: str
    code: str
    message: str


class PatchError(Exception):
    """Patch 应用失败异常"""

    def __init__(self, code: str, message: str, issues: List[PatchIssue]) -> None:
        self.code = code
        self.message = message
        self.issues = issues
        super().__init__(message)


# ============================================================
# 公开入口
# ============================================================


def apply_patch(document: dict, patch: dict) -> DslDocument:
    """
    将 Patch v0.1 应用于 DSL 文档。

    参数：
        document: DSL 文档原始 dict（不会被修改）
        patch: Patch 文档 dict

    返回：
        校验通过的新 DslDocument 实例

    异常：
        PatchError: 任何步骤失败时抛出，包含错误码与明细
    """
    try:
        return _apply_patch_impl(document, patch)
    except PatchError:
        raise
    except Exception as e:
        raise PatchError(
            code="internal_patch_error",
            message="Patch 应用过程中发生非预期错误",
            issues=[
                PatchIssue(
                    path="",
                    code="internal_error",
                    message=str(e)[:200],
                )
            ],
        ) from e


# ============================================================
# 内部实现
# ============================================================


def _apply_patch_impl(document: dict, patch: dict) -> DslDocument:
    """Patch 应用的核心实现"""

    # 步骤 1：校验 Patch 结构
    patch_doc = _validate_patch_structure(patch)

    # 步骤 2：校验源文档
    _validate_source_document(document)

    # 步骤 3：深拷贝文档（保护原始对象不可变）
    working_doc = copy.deepcopy(document)

    # 步骤 4：逐一执行操作
    for idx, operation in enumerate(patch_doc.operations):
        target_id = operation.target_node_id
        node = _find_node(working_doc.get("root"), target_id)
        if node is None:
            raise PatchError(
                code="patch_target_not_found",
                message=f"目标节点 '{target_id}' 在文档中不存在",
                issues=[
                    PatchIssue(
                        path=f"operations[{idx}].targetNodeId",
                        code="target_not_found",
                        message=f"未找到 ID 为 '{target_id}' 的节点",
                    )
                ],
            )
        # 步骤 4c：浅合并 props
        existing_props = node.get("props", {})
        node["props"] = {**existing_props, **operation.props}

    # 步骤 5：后校验
    _validate_patched_document(working_doc)

    # 步骤 6：返回校验后的 DslDocument
    return validate_dsl_document(working_doc)


def _validate_patch_structure(patch: dict) -> PatchDocument:
    """校验 Patch 结构，失败抛出 PatchError(invalid_patch_structure)"""
    try:
        return PatchDocument.model_validate(patch)
    except ValidationError as e:
        issues = []
        for err in e.errors():
            loc_parts = [str(p) for p in err["loc"]]
            path = ".".join(loc_parts) if loc_parts else ""
            # 提取子错误码
            issue_code = _map_pydantic_error_to_code(err, loc_parts)
            issues.append(
                PatchIssue(
                    path=path,
                    code=issue_code,
                    message=err["msg"],
                )
            )
        raise PatchError(
            code="invalid_patch_structure",
            message="Patch 结构校验失败",
            issues=issues,
        ) from e


def _validate_source_document(document: dict) -> None:
    """校验源文档，失败抛出 PatchError(invalid_source_document)"""
    try:
        validate_dsl_document(document)
    except DslValidationError as e:
        issues = [
            PatchIssue(path=err.path, code=err.code, message=err.message)
            for err in e.errors
        ]
        raise PatchError(
            code="invalid_source_document",
            message="源 DSL 文档校验失败",
            issues=issues,
        ) from e


def _validate_patched_document(document: dict) -> None:
    """后校验 Patched 文档，失败抛出 PatchError(invalid_patched_document)"""
    try:
        validate_dsl_document(document)
    except DslValidationError as e:
        issues = [
            PatchIssue(path=err.path, code=err.code, message=err.message)
            for err in e.errors
        ]
        raise PatchError(
            code="invalid_patched_document",
            message="Patch 应用后文档校验失败",
            issues=issues,
        ) from e


def _find_node(node: Any, target_id: str) -> Optional[Dict[str, Any]]:
    """递归搜索节点树，精确匹配 id 字段"""
    if not isinstance(node, dict):
        return None
    if node.get("id") == target_id:
        return node
    children = node.get("children", [])
    if isinstance(children, list):
        for child in children:
            result = _find_node(child, target_id)
            if result is not None:
                return result
    return None


def _map_pydantic_error_to_code(err: dict, loc_parts: List[str]) -> str:
    """将 Pydantic 错误映射为稳定的 issue.code"""
    err_type = err.get("type", "")
    msg = err.get("msg", "").lower()

    # 空 operations
    if "operations" in loc_parts and "too_short" in err_type:
        return "empty_operations"

    # 非法 op 值
    if "op" in loc_parts and "literal" in err_type:
        return "invalid_op"

    # targetNodeId 为空或纯空白
    if "targetNodeId" in loc_parts or "target_node_id" in loc_parts:
        if "too_short" in err_type or "空白" in msg:
            return "empty_target_node_id"
        return "invalid_target_node_id"

    # props 为空
    if "props" in loc_parts and ("空" in msg or "empty" in msg):
        return "empty_props"

    # version 非法
    if "version" in loc_parts:
        return "invalid_version"

    # 额外字段（extra=forbid）
    if "extra" in err_type:
        return "unknown_field"

    # value_error（自定义 validator 抛出）
    if "value_error" in err_type:
        if "空白" in msg:
            return "empty_target_node_id"
        if "空" in msg or "empty" in msg.lower():
            return "empty_props"
        if "json" in msg.lower() or "兼容" in msg:
            return "invalid_props_value"
        return "validation_error"

    return "schema_error"
