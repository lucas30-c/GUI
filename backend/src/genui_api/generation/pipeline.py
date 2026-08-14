"""Generation Pipeline — 无状态异步编排函数（三层收敛：结构化约束 → 无损规范化 → 精准 repair）。

三层收敛机制（根因修复 RC1~RC3）：
1. 生成时约束：Provider 侧以 DSL Schema 驱动的结构化输出约束候选形状（见
   openai_compat_provider）；SP 的 style 契约段落由 style_registry 渲染。
2. 确定性无损规范化：仅做语义完全等价的转换（trim / 枚举大小写 / CSS 数字
   字重到关键字的精确等价映射），每条转换都被记录；不做任何有损操作。
3. 精准 repair：首次校验失败时最多执行 1 次 Real Provider repair；repair 输入
   是机器可读的错误清单（路径 / 收到的值 / 该位置允许的字段与值域），而不是
   一句「请符合 DSL」。repair 输出重走完整解析、Schema 校验与业务规则校验。

Pipeline 永不降级到 Mock、模板匹配或「意图无法识别」：真实模型的失败就是失败，
fail-closed 后由 API 层转换为用户可读的分层错误。
"""
from __future__ import annotations

import copy
import json
import logging
import typing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from genui_api.contracts.dsl import DslDocument

from genui_api.contracts.dsl import Style
from genui_api.contracts.style_registry import (
    field_examples,
    field_grammar,
    machine_contract,
    style_field_names,
)
from genui_api.contracts.validation import DslValidationError, validate_dsl_document
from genui_api.generation.base import GenerationProvider

logger = logging.getLogger("genui.generation")

# prompt 长度上限（trim 后），与前端 MAX_PROMPT_LENGTH 同值；后端是最终事实来源（DD-5）
MAX_PROMPT_LENGTH = 500

# Provider 崩溃时的固定净化文案：不含异常原文、traceback 或 prompt 内容
_PROVIDER_ERROR_MESSAGE = "Generation provider failed to produce a candidate document"

# repair 上限：首次生成之外最多 1 次 repair，超过即 fail-closed（DD-P0-R1）
MAX_GENERATION_RETRIES = 1

# CSS font-weight 数字到关键字的精确等价映射（CSS Fonts 4 规范：
# 400=normal、500=medium、600=semibold、700=bold）。这是语义等价而非近似。
_NUMERIC_FONT_WEIGHT = {
    "400": "normal",
    "500": "medium",
    "600": "semibold",
    "700": "bold",
}

# 枚举类 style 字段：大小写规范化（CSS 枚举值大小写不敏感，契约要求小写）
_ENUM_STYLE_FIELDS = (
    "fontWeight",
    "textAlign",
    "display",
    "flexDirection",
    "justifyContent",
    "alignItems",
    "borderStyle",
)

# 枚举字段合法值表（从 Style 模型内省，供大小写规范化使用）
_ENUM_ALLOWED: dict[str, frozenset[str]] = {}
for _name in _ENUM_STYLE_FIELDS:
    _annotation = Style.model_fields[_name].annotation
    for _arg in typing.get_args(_annotation):
        if typing.get_origin(_arg) is typing.Literal:
            _ENUM_ALLOWED[_name] = frozenset(str(v) for v in typing.get_args(_arg))


@dataclass
class GenerationIssue:
    path: str
    code: str
    message: str


@dataclass
class NormalizationRecord:
    """一条无损规范化转换的完整记录（可审计、可测试）。"""

    path: str
    kind: str
    before: str
    after: str


@dataclass
class GenerationOutcome:
    """Pipeline 成功结果：文档 + 收敛过程元数据（供 API meta 与观测使用）。"""

    document: "DslDocument"
    attempts: int
    repair_used: bool
    normalization: list[NormalizationRecord] = field(default_factory=list)


class GenerationError(Exception):
    """Pipeline 失败异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        issues: list[GenerationIssue] | None = None,
        attempts: int = 1,
        repair_used: bool = False,
    ):
        self.code = code
        self.message = message
        self.issues = issues or []
        self.attempts = attempts
        self.repair_used = repair_used
        super().__init__(message)


async def generate_document(
    prompt: str,
    provider: GenerationProvider,
) -> GenerationOutcome:
    """初稿生成管线核心。无状态、不修改输入的异步编排函数。

    成功返回 GenerationOutcome；失败抛出 GenerationError（fail-closed）。
    最多调用 Provider 两次：首次生成 + 至多一次 repair。
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

    current_prompt = trimmed
    last_error: GenerationError | None = None

    for attempt in range(1, MAX_GENERATION_RETRIES + 2):  # attempt 1..2
        # 步骤 3 / 4: 调用 Provider（真实模型不做意图分类，无 UnrecognizedIntent 分支）
        try:
            candidate = await provider.generate_draft(current_prompt)
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
                attempts=attempt,
                repair_used=attempt > 1,
            )

        # 步骤 5: 候选必须是 dict
        if not isinstance(candidate, dict):
            last_error = GenerationError(
                code="invalid_generated_document",
                message="Generated candidate is not a JSON object",
                issues=[
                    GenerationIssue(
                        path="candidate",
                        code="invalid_generated_document",
                        message="Candidate document must be an object",
                    )
                ],
                attempts=attempt,
                repair_used=attempt > 1,
            )
            if attempt <= MAX_GENERATION_RETRIES:
                current_prompt = build_repair_user_prompt(trimmed, last_error, candidate)
                logger.info(
                    "event=repair_request reason=non_object_candidate attempt=%d",
                    attempt + 1,
                )
                continue
            raise last_error

        # 步骤 5.5: 确定性无损规范化（每条转换被记录）
        candidate, normalization = _normalize_document(candidate)

        # 步骤 6: 唯一校验入口 —— 完整 Schema + 业务规则校验
        try:
            document = validate_dsl_document(candidate)
        except DslValidationError as e:
            issues = [
                GenerationIssue(path=err.path, code=err.code, message=err.message)
                for err in e.errors
            ]
            last_error = GenerationError(
                code="invalid_generated_document",
                message="Generated document failed DSL validation",
                issues=issues,
                attempts=attempt,
                repair_used=attempt > 1,
            )
            logger.info(
                "event=validation_failed attempt=%d issue_count=%d codes=%s",
                attempt,
                len(issues),
                sorted({iss.code for iss in issues}),
            )
            if attempt <= MAX_GENERATION_RETRIES:
                current_prompt = build_repair_user_prompt(trimmed, last_error, candidate)
                logger.info(
                    "event=repair_request attempt=%d errors=%d",
                    attempt + 1,
                    len(issues),
                )
                continue
            raise last_error

        return GenerationOutcome(
            document=document,
            attempts=attempt,
            repair_used=attempt > 1,
            normalization=normalization,
        )

    # 理论上不会到达这里（循环内必定 return 或 raise）
    assert last_error is not None, "unreachable: loop must return or raise"
    raise last_error


# ============================================================
# 第三层：精准 repair（机器可读约束）
# ============================================================


def _resolve_value_at_path(candidate: Any, path: str) -> Any:
    """按校验路径在候选 dict 中尽力定位原始值（定位失败返回 None）。

    支持两种路径形态：
    - pydantic 风格：root.children.4.style.margin（纯 . 分隔，数字为下标）
    - 业务规则风格：root.children[2]（[N] 为下标）
    """
    tokens: list[str | int] = []
    for raw in path.replace("]", "").split("."):
        if not raw:
            continue
        if "[" in raw:
            key, _, rest = raw.partition("[")
            if key:
                tokens.append(key)
            for index_text in rest.split("["):
                if index_text.isdigit():
                    tokens.append(int(index_text))
        elif raw.isdigit():
            tokens.append(int(raw))
        else:
            tokens.append(raw)

    current = candidate
    for token in tokens:
        if isinstance(token, int):
            if isinstance(current, list) and 0 <= token < len(current):
                current = current[token]
            else:
                return None
        else:
            if isinstance(current, dict) and token in current:
                current = current[token]
            else:
                return None
    return current


def _constraint_for_issue(issue: GenerationIssue, candidate: dict) -> str:
    """为单条校验错误生成机器可读的处置约束。

    style 相关错误给出字段级值域文法与示例；未知 style 字段给出完整白名单；
    其余错误给出类别说明。repair 的模型输入因此是可直接执行的，而不是
    「请符合 DSL」式的空泛要求（RC3 修复）。
    """
    path = issue.path
    parts = path.replace("]", "").split(".")

    # 定位 style 子树内的错误：...style.<field> 或 ...style.<field>...
    if "style" in parts:
        style_index = parts.index("style")
        field_name = parts[style_index + 1] if style_index + 1 < len(parts) else None
        allowed = style_field_names()

        if field_name in allowed:
            grammar = field_grammar(field_name)
            examples = "、".join(field_examples(field_name))
            return (
                f"字段 {field_name} 的合法值域：{grammar}。"
                f"示例：{examples}。请把这个字段的值改成合法值，或移除该字段。"
            )
        if field_name is not None:
            return (
                f"字段 {field_name} 不在 style 白名单中，必须整个移除。"
                f"style 只允许这些字段：{', '.join(allowed)}。"
                f"如果该字段承载的视觉效果无法用白名单字段表达，直接移除它，"
                f"用白名单内最接近的字段替代或省略该装饰。"
            )
        return (
            f"style 对象只允许这些字段：{', '.join(allowed)}。"
            "请移除所有未列出的字段，并把保留字段的值改成合法值域。"
        )

    if issue.code == "duplicate_id":
        return "存在重复的节点 id。每个节点 id 必须全局唯一，请把重复的 id 改成新的语义化 id。"
    if issue.code == "invalid_nesting":
        return (
            "节点嵌套违反结构规则。注意：Page 只能作为根节点；叶子组件不得有 children；"
            "Form 的直接子节点只允许 Input / Button / Text / Heading；Input 必须位于 Form 内部。"
            "请调整结构使其合法，不要删除用户要求的内容。"
        )
    if issue.code == "invalid_root":
        return "root 必须是 Page 节点。请把根节点修正为 Page，并保留页面内容。"
    return (
        "该位置的值不符合 DSL v0.1 契约。请修正为契约允许的形状，"
        "保持页面内容与用户原始需求一致。"
    )


def build_repair_user_prompt(
    original_prompt: str,
    error: GenerationError,
    candidate: Any,
) -> str:
    """构造 repair user message：机器可读的错误清单 + 完整 style 契约。

    内容结构（JSON）：
    - task / 系统反馈标记；
    - originalRequest：原始用户需求（repair 必须保持页面目标）；
    - errors：逐条错误的 path / code / 收到的值 / 处置约束；
    - styleContract：全部 style 字段的值域（grammar + 枚举 + 示例）；
    - rules：只修错误、保持其余内容、输出完整文档。

    SP 不变（稳定层）；repair 上下文全部进入 user role，与「用户输入不可信」
    的信任模型一致——本 JSON 由系统构造，但同样要穿过完整校验才能成为状态。
    """
    errors_payload: list[dict[str, Any]] = []
    for issue in error.issues:
        received = None
        if isinstance(candidate, dict):
            received = _resolve_value_at_path(candidate, issue.path)
        entry: dict[str, Any] = {
            "path": issue.path,
            "code": issue.code,
            "constraint": _constraint_for_issue(issue, candidate if isinstance(candidate, dict) else {}),
        }
        if received is not None:
            entry["receivedValue"] = received
        errors_payload.append(entry)

    payload = {
        "task": "repair_dsl_document",
        "systemFeedback": True,
        "originalRequest": original_prompt,
        "errors": errors_payload,
        "styleContract": machine_contract(),
        "rules": [
            "只修复 errors 中列出的问题；未列出的内容必须原样保留。",
            "保持原始页面目标与内容完整性：不得因为修复错误而删除用户要求的板块或节点。",
            "输出修正后的完整 DSL 文档（顶层仍是 {\"version\": \"0.1\", \"root\": ...}），"
            "不要只输出补丁或解释。",
            "style 字段只能使用 styleContract 中列出的字段与值域；"
            "无法用白名单表达的装饰效果直接省略。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


# ============================================================
# 第二层：确定性无损规范化
# ============================================================


def _normalize_document(doc: dict) -> tuple[dict, list[NormalizationRecord]]:
    """无损规范化：仅做语义完全等价的确定性转换，并记录每条转换。

    当前允许的转换（全部语义等价）：
    - whitespace：去除 style 字符串值的首尾空格；
    - enum_case：枚举字段值大小写规范化（CSS 枚举大小写不敏感）；
    - font_weight_numeric：CSS 数字字重到关键字的精确等价
      （400=normal / 500=medium / 600=semibold / 700=bold）。

    明确不做的事（有损操作禁令）：不删除字段、不截断多值 shorthand、
    不把非法值替换成默认值、不展开 shorthand（契约原生接受 1-4 值简写）。
    无法证明等价的任何内容都原样留给 Schema 校验层拒绝。
    """
    records: list[NormalizationRecord] = []
    doc = copy.deepcopy(doc)
    _normalize_node(doc.get("root", {}), "root", records)
    return doc, records


def _normalize_node(node: dict, path: str, records: list[NormalizationRecord]) -> None:
    """递归规范化节点树（仅无损操作）。"""
    if not isinstance(node, dict):
        return

    style = node.get("style")
    if isinstance(style, dict):
        for key, value in list(style.items()):
            if not isinstance(value, str):
                continue
            field_path = f"{path}.style.{key}"
            original = value

            stripped = value.strip()
            if stripped != value:
                value = stripped
                records.append(
                    NormalizationRecord(field_path, "whitespace", original, value)
                )

            if key == "fontWeight" and value in _NUMERIC_FONT_WEIGHT:
                value = _NUMERIC_FONT_WEIGHT[value]
                records.append(
                    NormalizationRecord(field_path, "font_weight_numeric", original, value)
                )
            elif key in _ENUM_STYLE_FIELDS:
                allowed = _ENUM_ALLOWED.get(key, frozenset())
                if value not in allowed and value.lower() in allowed:
                    value = value.lower()
                    records.append(
                        NormalizationRecord(field_path, "enum_case", original, value)
                    )

            style[key] = value

    for index, child in enumerate(node.get("children", [])):
        _normalize_node(child, f"{path}.children.{index}", records)
