"""
GenUI Patch v0.1 模块

提供 Patch 数据契约与确定性应用核心：
- PatchDocument / UpdatePropsOperation / UpdateStyleOperation: Patch 数据模型
- PatchOperation: 以 op 为 discriminator 的操作联合类型
- apply_patch: Patch 应用入口
- PatchError / PatchIssue: 错误体系
- export_patch_schema: JSON Schema 导出
"""

from .apply import PatchError, PatchIssue, apply_patch
from .models import (
    PatchDocument,
    PatchOperation,
    StylePatchValue,
    UpdatePropsOperation,
    UpdateStyleOperation,
)
from .schema_export import export_patch_schema

__all__ = [
    "PatchDocument",
    "PatchOperation",
    "StylePatchValue",
    "UpdatePropsOperation",
    "UpdateStyleOperation",
    "apply_patch",
    "PatchError",
    "PatchIssue",
    "export_patch_schema",
]
