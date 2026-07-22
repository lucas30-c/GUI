"""API 响应模型 — DSL 校验接口的请求/响应契约"""

from typing import List

from pydantic import BaseModel


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
