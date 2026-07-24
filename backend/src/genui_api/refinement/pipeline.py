"""Refinement Pipeline — 无状态异步编排函数。"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from genui_api.contracts.validation import validate_dsl_document, DslValidationError
from genui_api.contracts.dsl import DslDocument, DslNode
from genui_api.patch.apply import apply_patch, PatchError
from genui_api.patch.models import PatchDocument
from genui_api.provider.base import RefinementProvider, RefinementContext


@dataclass
class RefinementResult:
    """Pipeline 成功时的返回值。"""

    success: bool
    patch: dict
    document: dict
    integrity: dict


@dataclass
class RefinementIssue:
    path: str
    code: str
    message: str


class RefinementError(Exception):
    """Pipeline 失败异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        issues: list[RefinementIssue] | None = None,
    ):
        self.code = code
        self.message = message
        self.issues = issues or []
        super().__init__(message)


def _find_node(node_data: dict, target_id: str) -> dict | None:
    """递归查找节点（在 dict 结构中）。"""
    if node_data.get("id") == target_id:
        return node_data
    for child in node_data.get("children", []):
        result = _find_node(child, target_id)
        if result is not None:
            return result
    return None


def _find_node_in_model(node: Any, target_id: str) -> Any:
    """在 Pydantic 模型树中查找节点。"""
    if node.id == target_id:
        return node
    if hasattr(node, "children") and node.children:
        for child in node.children:
            result = _find_node_in_model(child, target_id)
            if result is not None:
                return result
    return None


def _remove_props_from_node(doc_dict: dict, target_id: str) -> dict:
    """深拷贝 dict 并移除目标节点的 props 字段。"""
    result = copy.deepcopy(doc_dict)
    root = result.get("root", {})
    node = _find_node(root, target_id)
    if node is not None and "props" in node:
        del node["props"]
    return result


def verify_non_target_unchanged(
    original_doc: DslDocument,
    patched_doc: DslDocument,
    selected_node_id: str,
) -> bool:
    """
    完整性验证：序列化 → 移除目标 props → 全量深等比较。
    """
    original_dict = original_doc.model_dump(mode="json", by_alias=True)
    patched_dict = patched_doc.model_dump(mode="json", by_alias=True)

    original_stripped = _remove_props_from_node(original_dict, selected_node_id)
    patched_stripped = _remove_props_from_node(patched_dict, selected_node_id)

    return original_stripped == patched_stripped


# PatchError.code → Refine error mapping
_CANDIDATE_PATCH_ERRORS = frozenset(
    {
        "invalid_patched_document",
        "patch_target_not_found",
        "invalid_patch_structure",
    }
)


async def refine(
    document: dict,
    selected_node_id: str,
    instruction: str,
    provider: RefinementProvider,
) -> RefinementResult:
    """
    Refinement Pipeline 核心。无状态、不修改输入的异步编排函数。
    失败时抛出 RefinementError。
    """
    # 步骤 1: 校验 instruction
    if not instruction or not instruction.strip():
        raise RefinementError(
            code="invalid_instruction",
            message="Instruction must not be empty or whitespace-only",
            issues=[
                RefinementIssue(
                    path="instruction",
                    code="invalid_instruction",
                    message="Empty or whitespace-only instruction",
                )
            ],
        )
    if len(instruction) > 1000:
        raise RefinementError(
            code="invalid_instruction",
            message="Instruction exceeds 1000 character limit",
            issues=[
                RefinementIssue(
                    path="instruction",
                    code="invalid_instruction",
                    message="Exceeds 1000 characters",
                )
            ],
        )

    # 步骤 2: 校验源文档
    try:
        validated_doc = validate_dsl_document(document)
    except DslValidationError:
        raise RefinementError(
            code="invalid_source_document",
            message="Source document failed validation",
            issues=[
                RefinementIssue(
                    path="document",
                    code="invalid_source_document",
                    message="Document validation failed",
                )
            ],
        )

    # 步骤 3: 查找 selected_node_id（保存可信副本）
    trusted_selected_node_id = selected_node_id
    target_node = _find_node_in_model(validated_doc.root, trusted_selected_node_id)
    if target_node is None:
        raise RefinementError(
            code="target_node_not_found",
            message="Node not found in document",
            issues=[
                RefinementIssue(
                    path="selectedNodeId",
                    code="target_node_not_found",
                    message="Node not found in document",
                )
            ],
        )

    # 步骤 4: 构造 RefinementContext（深拷贝 props）
    target_props = (
        target_node.props.model_dump(mode="json", by_alias=True)
        if target_node.props
        else {}
    )
    context = RefinementContext(
        instruction=instruction,
        selected_node_id=trusted_selected_node_id,
        selected_node_type=target_node.type,
        selected_node_props=copy.deepcopy(target_props),
        document_version=validated_doc.version,
    )

    # 步骤 5: 调用 Provider
    try:
        candidate = await provider.generate_patch(context)
    except Exception:
        raise RefinementError(
            code="provider_error",
            message="Provider failed to generate a valid candidate",
            issues=[
                RefinementIssue(
                    path="provider",
                    code="provider_error",
                    message="Provider invocation failed",
                )
            ],
        )

    # 步骤 6: 校验候选结构
    try:
        PatchDocument.model_validate(candidate)
    except Exception:
        raise RefinementError(
            code="invalid_candidate_structure",
            message="Provider returned an invalid patch structure",
            issues=[
                RefinementIssue(
                    path="candidate",
                    code="invalid_candidate_structure",
                    message="Candidate patch structure validation failed",
                )
            ],
        )

    # 步骤 7: 边界检查（使用可信 selected_node_id）
    operations = candidate.get("operations", [])
    for i, op in enumerate(operations):
        target_node_id = op.get("targetNodeId", op.get("target_node_id", ""))
        if target_node_id != trusted_selected_node_id:
            raise RefinementError(
                code="candidate_boundary_violation",
                message="Candidate patch targets nodes outside selection boundary",
                issues=[
                    RefinementIssue(
                        path=f"operations[{i}].targetNodeId",
                        code="candidate_boundary_violation",
                        message="Operation targets a non-selected node",
                    )
                ],
            )

    # 步骤 8: 应用 Patch
    try:
        patched_doc = apply_patch(document, candidate)
    except PatchError as e:
        if e.code in _CANDIDATE_PATCH_ERRORS:
            raise RefinementError(
                code="patch_application_failed",
                message="Patch application failed due to candidate content",
                issues=[
                    RefinementIssue(
                        path="candidate",
                        code="patch_application_failed",
                        message="Apply patch failed",
                    )
                ],
            )
        else:
            raise RefinementError(
                code="internal_error",
                message="An internal error occurred during patch application",
                issues=[
                    RefinementIssue(
                        path="internal",
                        code="internal_error",
                        message="Internal patch error",
                    )
                ],
            )
    except Exception:
        raise RefinementError(
            code="internal_error",
            message="An unexpected internal error occurred",
            issues=[
                RefinementIssue(
                    path="internal",
                    code="internal_error",
                    message="Unexpected error",
                )
            ],
        )

    # 步骤 9: 非目标完整性验证
    if not verify_non_target_unchanged(
        validated_doc, patched_doc, trusted_selected_node_id
    ):
        raise RefinementError(
            code="non_target_mutation_detected",
            message="Non-target nodes were unexpectedly modified",
            issues=[
                RefinementIssue(
                    path="document",
                    code="non_target_mutation_detected",
                    message="Non-target node integrity check failed",
                )
            ],
        )

    # 步骤 10: 构造返回值
    patched_dict = patched_doc.model_dump(mode="json", by_alias=True)
    return RefinementResult(
        success=True,
        patch=candidate,
        document=patched_dict,
        integrity={
            "selectedNodeId": trusted_selected_node_id,
            "nonTargetNodesUnchanged": True,
        },
    )
