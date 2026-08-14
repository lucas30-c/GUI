"""API 路由 — DSL 校验、局部精修与初稿生成 HTTP 接口"""

import json
import logging
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from genui_api.api.schemas import (
    DslValidationFailure,
    DslValidationSuccess,
    GenerateFailure,
    GenerateMeta,
    GenerateRequest,
    GenerateSuccess,
    HealthResponse,
    NormalizationEntry,
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
from genui_api.generation.base import GenerationProvider
from genui_api.generation.openai_compat_provider import (
    OpenAICompatGenerationProvider,
    current_response_mode,
)
from genui_api.generation.pipeline import GenerationError, generate_document
from genui_api.llm.client import PROVIDER_OPENAI_COMPATIBLE, load_model_config
from genui_api.provider.base import ConfirmedTurn, RefinementProvider
from genui_api.provider.openai_compat_provider import OpenAICompatRefinementProvider
from genui_api.refinement.pipeline import refine, RefinementError

logger = logging.getLogger("genui.api")

router = APIRouter()


def _request_id(request: Request) -> str:
    """读取中间件注入的 request ID（缺省空串，测试直调时不报错）。"""
    return getattr(request.state, "request_id", "")


# ============================================================
# 用户可见错误文案（分层错误边界，RC6 修复）
# ============================================================
# error.message 面向普通用户：可理解、可重试、不含内部路径与 Pydantic 原文。
# error.issues[] 保留结构化诊断细节（前端默认折叠，供开发者排查）。
# 后端日志记录完整 issue 列表 + request ID（观测层）。
_USER_FACING_MESSAGES: dict[str, str] = {
    # generate
    "invalid_prompt": "页面描述为空或超长，请调整后重试。",
    "provider_error": "AI 服务暂时不可用，请稍后重试。",
    "invalid_generated_document": "AI 生成的页面未通过系统校验，请重试，或尝试简化页面描述。",
    # refine
    "invalid_instruction": "精修指令为空或超长，请调整后重试。",
    "invalid_source_document": "提交的页面文档无效，请刷新页面后重试。",
    "target_node_not_found": "未找到选中的节点，请重新选择节点后重试。",
    "invalid_request_structure": "请求格式不正确，请刷新页面后重试。",
    "invalid_candidate_structure": "AI 的精修结果未通过系统校验，页面未被改动，请重试。",
    "candidate_boundary_violation": "AI 的精修结果越过了允许的修改范围，已被系统拒绝，页面未被改动，请重试。",
    "patch_application_failed": "AI 的精修结果无法应用到页面，页面未被改动，请重试。",
    "non_target_mutation_detected": "精修完整性校验未通过，页面未被改动，请重试。",
    # shared
    "internal_error": "服务内部错误，请稍后重试。",
    "unsupported_media_type": "请求类型不支持，请使用 JSON 提交。",
    "invalid_json": "请求内容不是合法 JSON，请刷新页面后重试。",
}


def _user_message(code: str, fallback: str) -> str:
    return _USER_FACING_MESSAGES.get(code, fallback)


def get_provider() -> RefinementProvider:
    """精修 Provider 工厂（Real-Provider-only）。

    生产链路只返回真实 Provider；Mock 从生产路径移除（Owner 决策），
    测试替身经 create_app 的 dependency_overrides 显式注入，优先于本工厂。
    """
    load_model_config()  # 配置非法 → fail fast（启动期已校验，这里是运行时守卫）
    return OpenAICompatRefinementProvider()


def get_generation_provider() -> GenerationProvider:
    """生成 Provider 工厂（Real-Provider-only，同上）。"""
    load_model_config()
    return OpenAICompatGenerationProvider()


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
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="unsupported_media_type",
                    message=_user_message("unsupported_media_type", "Content-Type 必须为 application/json"),
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # 读取原始 body
    body = await request.body()

    # 检查是否为空
    if not body:
        return JSONResponse(
            status_code=400,
            content=DslValidationFailure(
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message="请求体为空",
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    body_str = body.decode("utf-8")

    try:
        doc = validate_dsl_json(body_str)
    except DslJsonParseError as e:
        # JSON 解析失败 → 400
        return JSONResponse(
            status_code=400,
            content=DslValidationFailure(
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message=_user_message("invalid_json", "JSON 解析失败"),
                    issues=[
                        ValidationIssue(
                            path="$", code="invalid_json", message=str(e)
                        )
                    ],
                ),
            ).model_dump(mode="json", by_alias=True),
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
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code=error_code,
                    message=error_message,
                    issues=issues,
                ),
            ).model_dump(mode="json", by_alias=True),
        )
    except Exception:
        # 未预期异常 → 500，不泄露内部信息
        logger.exception("request_id=%s validate unexpected error", _request_id(request))
        return JSONResponse(
            status_code=500,
            content=DslValidationFailure(
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="internal_error",
                    message=_user_message("internal_error", "服务内部错误"),
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
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
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="unsupported_media_type",
                    message=_user_message("unsupported_media_type", "Content-Type 必须为 application/json"),
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # 读取原始 body
    body = await request.body()

    # 检查是否为空
    if not body:
        return JSONResponse(
            status_code=400,
            content=RefineFailure(
                success=False,
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message="请求体为空",
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # JSON 解析
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=400,
            content=RefineFailure(
                success=False,
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message=_user_message("invalid_json", "JSON 解析失败"),
                    issues=[
                        ValidationIssue(
                            path="$", code="invalid_json", message="JSON 解析失败"
                        )
                    ],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # 请求模型校验
    try:
        req = RefineRequest.model_validate(data)
    except Exception:
        return JSONResponse(
            status_code=422,
            content=RefineFailure(
                success=False,
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="invalid_request_structure",
                    message=_user_message("invalid_request_structure", "请求结构校验失败"),
                    issues=[
                        ValidationIssue(
                            path="$",
                            code="invalid_request_structure",
                            message="请求结构校验失败",
                        )
                    ],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # wire → 域模型转换（Spec 009）：缺省 / null / [] 三态统一归一化为空 tuple。
    history = tuple(
        ConfirmedTurn(
            instruction=t.instruction,
            selected_node_id=t.selected_node_id,
            selected_node_type=t.node_type,
            patch_props=dict(t.patch_props),
            patch_style=dict(t.patch_style),
        )
        for t in (req.history or ())
    )

    # 调用 Pipeline
    try:
        result = await refine(
            document=req.document,
            selected_node_id=req.selected_node_id,
            instruction=req.instruction,
            provider=provider,
            history=history,
        )
    except RefinementError as e:
        status_code = _ERROR_HTTP_MAP.get(e.code, 500)
        issues = [
            ValidationIssue(path=iss.path, code=iss.code, message=iss.message)
            for iss in e.issues
        ]
        logger.warning(
            "request_id=%s refine_failed code=%s issues=%d detail=%s",
            _request_id(request),
            e.code,
            len(issues),
            [(iss.path, iss.code) for iss in issues],
        )
        return JSONResponse(
            status_code=status_code,
            content=RefineFailure(
                success=False,
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code=e.code,
                    message=_user_message(e.code, e.message),
                    issues=issues,
                ),
            ).model_dump(mode="json", by_alias=True),
        )
    except Exception:
        logger.exception("request_id=%s refine unexpected error", _request_id(request))
        return JSONResponse(
            status_code=500,
            content=RefineFailure(
                success=False,
                request_id=_request_id(request),
                error=ValidationErrorDetail(
                    code="internal_error",
                    message=_user_message("internal_error", "An unexpected internal error occurred"),
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # 成功
    success = RefineSuccess(
        success=True,
        patch=result.patch,
        document=result.document,
        integrity=RefinementIntegrity(
            selectedNodeId=result.integrity["selectedNodeId"],
            nonTargetNodesUnchanged=True,
        ),
    )
    content = success.model_dump(mode="json", by_alias=True)
    # patch 子树改用 exclude_unset 导出（Spec 010 DD-06）：Style 的 31 个字段都有
    # None 默认值，普通导出会把「候选未提及的样式」写成 null，与「显式 null = 删除
    # 该样式」混淆，前端无法据此还原本轮真实的 style 变更。exclude_unset 只保留候选
    # 真正给出的键（含显式 null），因此 echo 与候选逐键一致；update_props 只含无默认
    # 值的字段，该路径的输出与 M4-03 逐字节相同。
    content["patch"] = success.patch.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    return JSONResponse(status_code=200, content=content)


# ============================================================
# Generate Endpoint
# ============================================================

# 生成侧独立映射常量（DD-4）：与精修侧 _ERROR_HTTP_MAP 互不影响
_GENERATION_ERROR_HTTP_MAP: dict[str, int] = {
    "invalid_request_structure": 422,
    "invalid_prompt": 422,
    "provider_error": 502,
    "invalid_generated_document": 502,
    "internal_error": 500,
}


@router.post(
    "/api/v1/dsl/generate",
    response_model=GenerateSuccess,
    responses={
        400: {"model": GenerateFailure, "description": "JSON 解析失败或请求体为空"},
        415: {"model": GenerateFailure, "description": "不支持的 Content-Type"},
        422: {"model": GenerateFailure, "description": "请求结构/prompt 校验失败"},
        500: {"model": GenerateFailure, "description": "服务内部错误"},
        502: {"model": GenerateFailure, "description": "Provider/候选文档问题"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": GenerateRequest.model_json_schema(by_alias=True)
                }
            },
        }
    },
)
async def generate_dsl(
    request: Request,
    provider: GenerationProvider = Depends(get_generation_provider),
) -> JSONResponse | GenerateSuccess:
    """初稿生成端点 — 由一句自然语言需求产出完整 DSL 初稿"""

    request_id = _request_id(request)

    # 检查 Content-Type
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("application/json"):
        return JSONResponse(
            status_code=415,
            content=GenerateFailure(
                success=False,
                request_id=request_id,
                error=ValidationErrorDetail(
                    code="unsupported_media_type",
                    message=_user_message("unsupported_media_type", "Content-Type 必须为 application/json"),
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # 读取原始 body
    body = await request.body()

    # 检查是否为空
    if not body:
        return JSONResponse(
            status_code=400,
            content=GenerateFailure(
                success=False,
                request_id=request_id,
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message="请求体为空",
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # JSON 解析
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content=GenerateFailure(
                success=False,
                request_id=request_id,
                error=ValidationErrorDetail(
                    code="invalid_json",
                    message=_user_message("invalid_json", "JSON 解析失败"),
                    issues=[
                        ValidationIssue(
                            path="$", code="invalid_json", message="JSON 解析失败"
                        )
                    ],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # 请求模型校验
    try:
        req = GenerateRequest.model_validate(data)
    except Exception:
        return JSONResponse(
            status_code=422,
            content=GenerateFailure(
                success=False,
                request_id=request_id,
                error=ValidationErrorDetail(
                    code="invalid_request_structure",
                    message=_user_message("invalid_request_structure", "请求结构校验失败"),
                    issues=[
                        ValidationIssue(
                            path="$",
                            code="invalid_request_structure",
                            message="请求结构校验失败",
                        )
                    ],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    # 调用 Generation Pipeline（三层收敛在 Pipeline/Provider 内部完成）
    started = time.perf_counter()
    try:
        outcome = await generate_document(prompt=req.prompt, provider=provider)
    except GenerationError as e:
        duration_ms = int((time.perf_counter() - started) * 1000)
        status_code = _GENERATION_ERROR_HTTP_MAP.get(e.code, 500)
        issues = [
            ValidationIssue(path=iss.path, code=iss.code, message=iss.message)
            for iss in e.issues
        ]
        logger.warning(
            "request_id=%s generation_failed code=%s attempts=%d repair_used=%s "
            "duration_ms=%d issues=%s",
            request_id,
            e.code,
            e.attempts,
            e.repair_used,
            duration_ms,
            [(iss.path, iss.code, iss.message) for iss in issues],
        )
        return JSONResponse(
            status_code=status_code,
            content=GenerateFailure(
                success=False,
                request_id=request_id,
                error=ValidationErrorDetail(
                    code=e.code,
                    message=_user_message(e.code, e.message),
                    issues=issues,
                ),
            ).model_dump(mode="json", by_alias=True),
        )
    except Exception:
        logger.exception("request_id=%s generation unexpected error", request_id)
        return JSONResponse(
            status_code=500,
            content=GenerateFailure(
                success=False,
                request_id=request_id,
                error=ValidationErrorDetail(
                    code="internal_error",
                    message=_user_message("internal_error", "An unexpected internal error occurred"),
                    issues=[],
                ),
            ).model_dump(mode="json", by_alias=True),
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    config = load_model_config()
    meta = GenerateMeta(
        request_id=request_id,
        provider=PROVIDER_OPENAI_COMPATIBLE,
        model=config.generation_model,
        structured_output=current_response_mode(),
        attempts=outcome.attempts,
        repair_used=outcome.repair_used,
        normalization=[
            NormalizationEntry(
                path=record.path,
                kind=record.kind,
                before=record.before,
                after=record.after,
            )
            for record in outcome.normalization
        ],
        duration_ms=duration_ms,
    )
    logger.info(
        "request_id=%s generation_succeeded attempts=%d repair_used=%s "
        "normalization=%d structured_output=%s duration_ms=%d",
        request_id,
        outcome.attempts,
        outcome.repair_used,
        len(outcome.normalization),
        meta.structured_output,
        duration_ms,
    )

    # 成功
    return JSONResponse(
        status_code=200,
        content=GenerateSuccess(
            success=True,
            document=outcome.document.model_dump(mode="json"),
            meta=meta,
        ).model_dump(mode="json", by_alias=True),
    )
