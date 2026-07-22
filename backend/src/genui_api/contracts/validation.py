"""
DSL v0.1 校验入口与业务规则

提供两个公开入口：
- validate_dsl_document(data: dict) -> DslDocument
- validate_dsl_json(raw_json: str) -> DslDocument

业务规则在 Pydantic 结构校验之后执行，包括：
- 全局 ID 唯一性
- root 必须是 Page
- Page 不能出现在非根位置
- 叶子节点不能有 children
- Form 内只允许 Input, Button, Text, Heading
- Input 不能出现在 Form 之外
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Set

from pydantic import ValidationError

from .dsl import (
    CardNode,
    DslDocument,
    DslNode,
    FormNode,
    PageNode,
    SectionNode,
)

# ============================================================
# 异常定义
# ============================================================


@dataclass
class DslError:
    """单条校验错误"""

    path: str
    code: str
    message: str


class DslValidationError(Exception):
    """DSL 校验失败异常，包含错误列表"""

    def __init__(self, errors: List[DslError]) -> None:
        self.errors = errors
        messages = "; ".join(f"[{e.code}] {e.path}: {e.message}" for e in errors)
        super().__init__(f"DSL 校验失败 ({len(errors)} 个错误): {messages}")


class DslJsonParseError(Exception):
    """JSON 解析错误（区别于 DSL 结构校验错误）"""

    def __init__(self, message: str) -> None:
        super().__init__(f"JSON 解析失败: {message}")


# ============================================================
# 嵌套规则矩阵（集中定义）
# ============================================================

# 容器节点类型
CONTAINER_TYPES: Set[str] = {"Page", "Section", "Card", "Form"}

# 叶子节点类型
LEAF_TYPES: Set[str] = {"Heading", "Text", "Button", "Image", "Input"}

# Form 内允许的子节点类型
FORM_ALLOWED_CHILDREN: Set[str] = {"Input", "Button", "Text", "Heading"}

# Input 只能出现在 Form 内部
INPUT_REQUIRED_PARENT: str = "Form"


# ============================================================
# 业务规则校验器
# ============================================================


@dataclass
class _ValidationContext:
    """校验过程中的上下文状态"""

    errors: List[DslError] = field(default_factory=list)
    seen_ids: dict = field(default_factory=dict)  # id -> path


def _get_children(node: object) -> List[DslNode]:
    """安全获取节点的 children 列表"""
    if hasattr(node, "children"):
        return node.children  # type: ignore
    return []


def _walk_tree(
    node: object,
    path: str,
    parent_type: str | None,
    in_form: bool,
    ctx: _ValidationContext,
) -> None:
    """递归遍历节点树，执行业务规则校验"""
    node_type: str = node.type  # type: ignore
    node_id: str = node.id  # type: ignore

    # 规则 1：全局 ID 唯一性
    if node_id in ctx.seen_ids:
        ctx.errors.append(
            DslError(
                path=path,
                code="duplicate_id",
                message=f"ID '{node_id}' 重复，首次出现在 {ctx.seen_ids[node_id]}",
            )
        )
    else:
        ctx.seen_ids[node_id] = path

    # 规则 3：Page 不能出现在非根位置
    if node_type == "Page" and parent_type is not None:
        ctx.errors.append(
            DslError(
                path=path,
                code="invalid_nesting",
                message="Page 节点只能作为根节点，不能嵌套在其他节点内",
            )
        )

    # 规则 7：Input 不能出现在 Form 之外
    if node_type == "Input" and not in_form:
        ctx.errors.append(
            DslError(
                path=path,
                code="invalid_nesting",
                message="Input 节点必须在 Form 内部",
            )
        )

    # 规则 6：Form 内只允许特定子节点类型
    if parent_type == "Form" and node_type not in FORM_ALLOWED_CHILDREN:
        ctx.errors.append(
            DslError(
                path=path,
                code="invalid_nesting",
                message=f"Form 内不允许 {node_type} 节点，只允许: {', '.join(sorted(FORM_ALLOWED_CHILDREN))}",
            )
        )

    # 递归遍历子节点
    children = _get_children(node)
    current_in_form = in_form or node_type == "Form"

    for i, child in enumerate(children):
        child_path = f"{path}.children[{i}]"
        _walk_tree(child, child_path, node_type, current_in_form, ctx)


def _run_business_rules(doc: DslDocument) -> None:
    """执行所有业务规则校验，失败时抛出 DslValidationError"""
    ctx = _ValidationContext()
    root = doc.root

    # 规则 2：root 必须是 Page 类型（由 DslDocument 模型保证，但双重检查）
    if root.type != "Page":
        ctx.errors.append(
            DslError(
                path="root",
                code="invalid_root",
                message=f"根节点必须是 Page 类型，当前为 {root.type}",
            )
        )

    # 遍历整棵树
    _walk_tree(root, "root", None, False, ctx)

    if ctx.errors:
        raise DslValidationError(ctx.errors)


# ============================================================
# 公开校验入口
# ============================================================


def validate_dsl_document(data: dict) -> DslDocument:
    """
    从 dict 校验 DSL 文档。

    1. 执行 Pydantic 结构校验（类型、格式、extra fields）
    2. 执行业务规则校验（ID 唯一、嵌套规则等）

    成功返回 DslDocument 实例，失败抛出异常。
    """
    try:
        doc = DslDocument.model_validate(data)
    except ValidationError as e:
        # 将 Pydantic 错误转换为统一的 DslValidationError
        errors = []
        for err in e.errors():
            loc_parts = [str(p) for p in err["loc"]]
            path = ".".join(loc_parts) if loc_parts else "root"
            errors.append(
                DslError(
                    path=path,
                    code="schema_error",
                    message=err["msg"],
                )
            )
        raise DslValidationError(errors) from e

    # 通过结构校验后执行业务规则
    _run_business_rules(doc)
    return doc


def validate_dsl_json(raw_json: str) -> DslDocument:
    """
    从 JSON 字符串校验 DSL 文档。

    区分两类错误：
    - JSON 解析错误 -> DslJsonParseError
    - DSL 校验错误 -> DslValidationError
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError) as e:
        raise DslJsonParseError(str(e)) from e

    if not isinstance(data, dict):
        raise DslValidationError(
            [DslError(path="root", code="schema_error", message="顶层必须是 JSON 对象")]
        )

    return validate_dsl_document(data)
