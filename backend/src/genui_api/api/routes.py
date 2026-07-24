"""API 路由 — DSL 校验与精修 HTTP 接口"""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from genui_api.api.schemas import (
    DslValidationFailure,
    DslValidationSuccess,
    HealthResponse,
    RefineFailure,
    RefineRequest,
    RefineSuccess,
    RefinementIntegrity,
    ValidationErrorDetail,
    ValidationIssue,
)
from genui_api.contracts.validation import (
    DslJsonParseError,
    DslValidationError,
    validate_dsl_json,
)
from genui_api.provider.base import RefinementProvider
from genui_api.provider.mock import MockProvider
from genui_api.refinement.pipeline import refine, RefinementError

router = APIRouter()


def get_provider() -> RefinementProvider:
    """默认 Provider 工厂，返回无状态 MockProvider。"""
    return MockProvider()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """健康检查端点"""
    return HealthResponse(status="ok", service="genui-api")


@router.post(
    "/api/v1/dsl/validate",
    response_model=DslValidationSuccess,
    responses={
        400: {"model": DslValidationFailure, "description": "JSON 解析失败或请求体为空"},
        415: {"model": DslValidationFailure, "description": "不支持的 Content-Type"},
        422: {"model": DslValidationFailure, "description": "DSL 结构或业务规则校验失败"},
        500: {"model": DslValidationFailure, "description": "服务内部错误"},
    },
)
async def validate_dsl(request: Request) -> JSONResponse | DslValidationSuccess:
    """DSL 校验端点 — 接收原始 JSON 并执行完整校验"""

    # 检查 Content-Type
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("application/json"):
        return JSONResponse(
            status_code=415,
            content=DslValidationFailure(
                error=ValidationErrorDetail(
                    code="unsupported_media_type",
                    message="Content-Type 必须为 application/json",
                    issues=[],
                )
            ).model_dump(mode="json"),
        )

    # 读取原始 body
    body = await request.body()

    # 检查是否为空
    if not body:
        return JSONResponse(
            status_code=400,
            content=DslValidationFailure(
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message="请求体为空",
                    issues=[],
                )
            ).model_dump(mode="json"),
        )

    body_str = body.decode("utf-8")

    try:
        doc = validate_dsl_json(body_str)
    except DslJsonParseError as e:
        # JSON 解析失败 → 400
        return JSONResponse(
            status_code=400,
            content=DslValidationFailure(
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message=str(e),
                    issues=[
                        ValidationIssue(
                            path="$", code="invalid_json", message=str(e)
                        )
                    ],
                )
            ).model_dump(mode="json"),
        )
    except DslValidationError as e:
        # DSL 校验失败 — 区分结构错误和业务规则错误
        issues = [
            ValidationIssue(path=err.path, code=err.code, message=err.message)
            for err in e.errors
        ]
        # 判断错误类型
        has_business_error = any(
            err.code in ("duplicate_id", "invalid_nesting", "invalid_root")
            for err in e.errors
        )
        if has_business_error:
            error_code = "invalid_dsl_business_rule"
            error_message = "DSL 业务规则校验失败"
        else:
            error_code = "invalid_dsl_structure"
            error_message = "DSL 结构校验失败"

        return JSONResponse(
            status_code=422,
            content=DslValidationFailure(
                error=ValidationErrorDetail(
                    code=error_code,
                    message=error_message,
                    issues=issues,
                )
            ).model_dump(mode="json"),
        )
    except Exception:
        # 未预期异常 → 500，不泄露内部信息
        return JSONResponse(
            status_code=500,
            content=DslValidationFailure(
                error=ValidationErrorDetail(
                    code="internal_error",
                    message="服务内部错误",
                    issues=[],
                )
            ).model_dump(mode="json"),
        )

    # 校验成功
    return DslValidationSuccess(document=doc.model_dump(mode="json"))


# ============================================================
# Refine Endpoint
# ============================================================

_ERROR_HTTP_MAP: dict[str, int] = {
    "invalid_instruction": 422,
    "invalid_source_document": 422,
    "target_node_not_found": 422,
    "invalid_request_structure": 422,
    "provider_error": 502,
    "invalid_candidate_structure": 502,
    "candidate_boundary_violation": 502,
    "patch_application_failed": 502,
    "non_target_mutation_detected": 500,
    "internal_error": 500,
}


@router.post(
    "/api/v1/dsl/refine",
    response_model=RefineSuccess,
    responses={
        400: {"model": RefineFailure, "description": "JSON 解析失败或请求体为空"},
        415: {"model": RefineFailure, "description": "不支持的 Content-Type"},
        422: {"model": RefineFailure, "description": "请求结构/指令/文档/节点校验失败"},
        500: {"model": RefineFailure, "description": "完整性破坏或内部错误"},
        502: {"model": RefineFailure, "description": "Provider/候选问题"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": RefineRequest.model_json_schema(by_alias=True)
                }
            },
        }
    },
)
async def refine_dsl(
    request: Request,
    provider: RefinementProvider = Depends(get_provider),
) -> JSONResponse | RefineSuccess:
    """精修端点 — 局部精修 DSL 文档中的单个节点"""

    # 检查 Content-Type
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("application/json"):
        return JSONResponse(
            status_code=415,
            content=RefineFailure(
                success=False,
                error=ValidationErrorDetail(
                    code="unsupported_media_type",
                    message="Content-Type 必须为 application/json",
                    issues=[],
                ),
            ).model_dump(mode="json"),
        )

    # 读取原始 body
    body = await request.body()

    # 检查是否为空
    if not body:
        return JSONResponse(
            status_code=400,
            content=RefineFailure(
                success=False,
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message="请求体为空",
                    issues=[],
                ),
            ).model_dump(mode="json"),
        )

    # JSON 解析
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=400,
            content=RefineFailure(
                success=False,
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message="JSON 解析失败",
                    issues=[
                        ValidationIssue(
                            path="$", code="invalid_json", message="JSON 解析失败"
                        )
                    ],
                ),
            ).model_dump(mode="json"),
        )

    # 请求模型校验
    try:
        req = RefineRequest.model_validate(data)
    except Exception:
        return JSONResponse(
            status_code=422,
            content=RefineFailure(
                success=False,
                error=ValidationErrorDetail(
                    code="invalid_request_structure",
                    message="请求结构校验失败",
                    issues=[
                        ValidationIssue(
                            path="$",
                            code="invalid_request_structure",
                            message="请求结构校验失败",
                        )
                    ],
                ),
            ).model_dump(mode="json"),
        )

    # 调用 Pipeline
    try:
        result = await refine(
            document=req.document,
            selected_node_id=req.selected_node_id,
            instruction=req.instruction,
            provider=provider,
        )
    except RefinementError as e:
        status_code = _ERROR_HTTP_MAP.get(e.code, 500)
        issues = [
            ValidationIssue(path=iss.path, code=iss.code, message=iss.message)
            for iss in e.issues
        ]
        return JSONResponse(
            status_code=status_code,
            content=RefineFailure(
                success=False,
                error=ValidationErrorDetail(
                    code=e.code,
                    message=e.message,
                    issues=issues,
                ),
            ).model_dump(mode="json"),
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content=RefineFailure(
                success=False,
                error=ValidationErrorDetail(
                    code="internal_error",
                    message="An unexpected internal error occurred",
                    issues=[],
                ),
            ).model_dump(mode="json"),
        )

    # 成功
    return JSONResponse(
        status_code=200,
        content=RefineSuccess(
            success=True,
            patch=result.patch,
            document=result.document,
            integrity=RefinementIntegrity(
                selectedNodeId=result.integrity["selectedNodeId"],
                nonTargetNodesUnchanged=True,
            ),
        ).model_dump(mode="json", by_alias=True),
    )
