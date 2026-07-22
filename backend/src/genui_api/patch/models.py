"""
Patch v0.1 数据模型定义

使用 Pydantic v2 定义 GenUI Patch 的类型系统：
- UpdatePropsOperation：单个 props 更新操作
- PatchDocument：Patch 文档顶层结构
"""

from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UpdatePropsOperation(BaseModel):
    """单个 update_props 操作"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    op: Literal["update_props"]
    target_node_id: str = Field(alias="targetNodeId", min_length=1)
    props: Dict[str, Any]

    @model_validator(mode="after")
    def _validate_fields(self) -> "UpdatePropsOperation":
        """校验 targetNodeId 非纯空白、props 非空且值为 JSON 兼容类型"""
        # 拒绝纯空白 targetNodeId
        if self.target_node_id.strip() == "":
            raise ValueError("targetNodeId 不能为纯空白字符串")

        # 拒绝空 props
        if len(self.props) == 0:
            raise ValueError("props 不能为空对象")

        # 校验 props 值为 JSON 兼容类型
        _check_json_compatible(self.props, "props")

        return self


class PatchDocument(BaseModel):
    """Patch v0.1 文档顶层结构"""

    model_config = ConfigDict(extra="forbid")

    version: Literal["0.1"]
    operations: list[UpdatePropsOperation] = Field(min_length=1)


def _check_json_compatible(value: Any, path: str) -> None:
    """递归检查值是否为 JSON 兼容类型"""
    if value is None:
        return
    if isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(
                    f"{path} 中的键必须为字符串类型"
                )
            _check_json_compatible(v, f"{path}.{k}")
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check_json_compatible(item, f"{path}[{i}]")
        return
    raise ValueError(
        f"{path} 包含非 JSON 兼容值（类型: {type(value).__name__}）"
    )
