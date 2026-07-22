"""
GenUI Patch v0.1 模块

提供 Patch 数据契约与确定性应用核心：
- PatchDocument / UpdatePropsOperation: Patch 数据模型
- apply_patch: Patch 应用入口
- PatchError / PatchIssue: 错误体系
- export_patch_schema: JSON Schema 导出
"""

from .apply import PatchError, PatchIssue, apply_patch
from .models import PatchDocument, UpdatePropsOperation
from .schema_export import export_patch_schema

__all__ = [
    "PatchDocument",
    "UpdatePropsOperation",
    "apply_patch",
    "PatchError",
    "PatchIssue",
    "export_patch_schema",
]
