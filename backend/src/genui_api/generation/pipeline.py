"""Generation Pipeline — 无状态异步编排函数（固定 6 步，DD-8）。"""
from __future__ import annotations

from dataclasses import dataclass

from genui_api.contracts.dsl import DslDocument
from genui_api.contracts.validation import DslValidationError, validate_dsl_document
from genui_api.generation.base import GenerationProvider, UnrecognizedIntentError

# prompt 长度上限（trim 后），与前端 MAX_PROMPT_LENGTH 同值；后端是最终事实来源（DD-5）
MAX_PROMPT_LENGTH = 500

# Provider 崩溃时的固定净化文案：不含异常原文、traceback 或 prompt 内容
_PROVIDER_ERROR_MESSAGE = "Generation provider failed to produce a candidate document"


@dataclass
class GenerationIssue:
    path: str
    code: str
    message: str


class GenerationError(Exception):
    """Pipeline 失败异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        issues: list[GenerationIssue] | None = None,
    ):
        self.code = code
        self.message = message
        self.issues = issues or []
        super().__init__(message)


async def generate_document(
    prompt: str,
    provider: GenerationProvider,
) -> DslDocument:
    """
    初稿生成管线核心。无状态、不修改输入的异步编排函数。
    失败时抛出 GenerationError。
    """
    # 步骤 1: prompt trim 后非空
    trimmed = prompt.strip()
    if not trimmed:
        raise GenerationError(
            code="invalid_prompt",
            message="Prompt must not be empty or whitespace-only",
            issues=[
                GenerationIssue(
                    path="prompt",
                    code="invalid_prompt",
                    message="Empty or whitespace-only prompt",
                )
            ],
        )

    # 步骤 2: 长度上限（恰好 500 合法）
    if len(trimmed) > MAX_PROMPT_LENGTH:
        raise GenerationError(
            code="invalid_prompt",
            message=f"Prompt exceeds {MAX_PROMPT_LENGTH} character limit",
            issues=[
                GenerationIssue(
                    path="prompt",
                    code="invalid_prompt",
                    message=f"Exceeds {MAX_PROMPT_LENGTH} characters",
                )
            ],
        )

    # 步骤 3 / 4: 调用 Provider（传入 trim 后的 prompt），区分意图失败与 Provider 崩溃
    try:
        candidate = await provider.generate_draft(trimmed)
    except UnrecognizedIntentError:
        raise GenerationError(
            code="unrecognized_intent",
            message="No draft intent matches the given prompt",
            issues=[
                GenerationIssue(
                    path="prompt",
                    code="unrecognized_intent",
                    message="Prompt could not be mapped to any known draft intent",
                )
            ],
        )
    except Exception:
        raise GenerationError(
            code="provider_error",
            message=_PROVIDER_ERROR_MESSAGE,
            issues=[
                GenerationIssue(
                    path="provider",
                    code="provider_error",
                    message="Provider invocation failed",
                )
            ],
        )

    # 步骤 5: 候选必须是 dict
    if not isinstance(candidate, dict):
        raise GenerationError(
            code="invalid_generated_document",
            message="Generated candidate is not a JSON object",
            issues=[
                GenerationIssue(
                    path="candidate",
                    code="invalid_generated_document",
                    message="Candidate document must be an object",
                )
            ],
        )

    # 步骤 6: 唯一校验入口 —— 完整 Schema + 业务规则校验
    try:
        return validate_dsl_document(candidate)
    except DslValidationError as e:
        raise GenerationError(
            code="invalid_generated_document",
            message="Generated document failed DSL validation",
            issues=[
                GenerationIssue(path=err.path, code=err.code, message=err.message)
                for err in e.errors
            ],
        )
