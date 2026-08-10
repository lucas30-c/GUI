"""
Patch v0.1 数据模型定义

使用 Pydantic v2 定义 GenUI Patch 的类型系统：
- UpdatePropsOperation：单个 props 更新操作
- UpdateStyleOperation：单个 style 更新操作（Spec 010 DD-01 ~ DD-03）
- PatchOperation：以 op 为 discriminator 的操作联合类型（DD-04）
- PatchDocument：Patch 文档顶层结构
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from genui_api.contracts.dsl import Style

# wire 层 style 值域：11 个字段的合法值全部是字符串，null 表示删除该键（DD-03 / DD-07）。
# 此别名用于文档化与前后端对齐；键白名单与值域的唯一事实来源仍是 contracts.dsl.Style。
StylePatchValue = str | None


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


class UpdateStyleOperation(BaseModel):
    """单个 update_style 操作（与 UpdatePropsOperation 逐项同构，DD-01）"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    op: Literal["update_style"]
    target_node_id: str = Field(alias="targetNodeId", min_length=1)
    # 复用 DSL 的 Style 模型（DD-02）：11 字段白名单与值域只有一个事实来源，
    # 未知键由 Style 的 extra="forbid" 在 Patch schema 层即被拒绝。
    style: Style

    @model_validator(mode="after")
    def _validate_fields(self) -> "UpdateStyleOperation":
        """校验 targetNodeId 非纯空白、style 至少显式给出一个键"""
        # 拒绝纯空白 targetNodeId
        if self.target_node_id.strip() == "":
            raise ValueError("targetNodeId 不能为纯空白字符串")

        # 拒绝空 style（操作必须有效果，DD-08）
        if len(self.style.model_fields_set) == 0:
            raise ValueError("style 不能为空对象")

        return self


# 以 op 为 discriminator 的操作联合类型（DD-04）：
# 失配时 pydantic 报 union_tag_invalid / union_tag_not_found，
# 由 apply._map_pydantic_error_to_code 继续映射为 invalid_op（DD-28）。
PatchOperation = Annotated[
    Union[UpdatePropsOperation, UpdateStyleOperation],
    Field(discriminator="op"),
]


class PatchDocument(BaseModel):
    """Patch v0.1 文档顶层结构"""

    model_config = ConfigDict(extra="forbid")

    version: Literal["0.1"]
    operations: list[PatchOperation] = Field(min_length=1)


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
