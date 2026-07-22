"""API 路由 — DSL 校验 HTTP 接口"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from genui_api.api.schemas import (
    DslValidationFailure,
    DslValidationSuccess,
    HealthResponse,
    ValidationErrorDetail,
    ValidationIssue,
)
from genui_api.contracts.validation import (
    DslJsonParseError,
    DslValidationError,
    validate_dsl_json,
)

router = APIRouter()


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
