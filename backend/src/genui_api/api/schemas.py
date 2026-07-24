"""API 响应模型 — DSL 校验与精修接口的请求/响应契约"""

from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field

from genui_api.contracts.dsl import DslDocument
from genui_api.patch.models import PatchDocument


class HealthResponse(BaseModel):
    """GET /health 响应"""

    status: str
    service: str


class DslValidationSuccess(BaseModel):
    """DSL 校验成功响应"""

    valid: bool = True  # 固定为 true
    document: dict  # 经过校验的完整 DSL Document（model_dump 结果）


class ValidationIssue(BaseModel):
    """单条校验问题"""

    path: str
    code: str
    message: str


class ValidationErrorDetail(BaseModel):
    """错误详情"""

    code: str
    message: str
    issues: List[ValidationIssue]


class DslValidationFailure(BaseModel):
    """DSL 校验失败响应"""

    valid: bool = False  # 固定为 false
    error: ValidationErrorDetail


# --- Refine API Models ---


class RefineRequest(BaseModel):
    """POST /api/v1/dsl/refine 请求体。"""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    document: dict[str, Any]
    selected_node_id: str = Field(
        alias="selectedNodeId",
        min_length=1,
    )
    instruction: str


class RefinementIntegrity(BaseModel):
    """精修完整性证明。"""

    model_config = ConfigDict(populate_by_name=True)

    selected_node_id: str = Field(alias="selectedNodeId")
    non_target_nodes_unchanged: Literal[True] = Field(alias="nonTargetNodesUnchanged")


class RefineSuccess(BaseModel):
    """精修成功响应。"""

    model_config = ConfigDict(populate_by_name=True)

    success: Literal[True]
    patch: PatchDocument
    document: DslDocument
    integrity: RefinementIntegrity


class RefineFailure(BaseModel):
    """精修失败响应。"""

    model_config = ConfigDict(populate_by_name=True)

    success: Literal[False]
    error: ValidationErrorDetail
