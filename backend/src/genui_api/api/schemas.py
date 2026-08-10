"""API 响应模型 — DSL 校验与精修接口的请求/响应契约"""

from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from genui_api.contracts.dsl import DslDocument
from genui_api.patch.models import PatchDocument, StylePatchValue

# 上下文预算上界的单一事实来源是 provider/base.py（Spec 009 DD-21）。
# 此处 import 并再导出，既保证 `from genui_api.api.schemas import MAX_HISTORY_TURNS`
# 可用，也保证两处引用的是同一个对象（不是同值副本）。
from genui_api.provider.base import (  # noqa: F401  (re-export)
    MAX_HISTORY_CHARS,
    MAX_HISTORY_TURNS,
    MAX_TURN_PROPS_KEYS,
    MAX_TURN_STYLE_KEYS,
    history_char_size,
)


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


# 9 种注册组件类型的只读镜像；contracts/** 仍是唯一契约事实来源，
# 由测试断言本镜像与 DSL 节点联合类型集合完全一致（防漂移）。
RegisteredNodeType = Literal[
    "Page", "Section", "Heading", "Text", "Button", "Image", "Card", "Form", "Input"
]

# history 的 patchProps 值只能是 JSON 标量 —— DSL v0.1 全部 props 都是标量，
# 因此该限制不损失任何合法表达，却关掉了「history 变成任意嵌套 payload 通道」。
PatchPropValue = str | int | float | bool | None

# history 的 patchStyle 值域与 DSL Style 一致：全部字段都是字符串，null 表示
# 「该轮删除了这个样式」。值类型直接复用 patch 层的 StylePatchValue（单一事实来源）。
# 刻意**不**在 wire 层做白名单与值域校验 —— history 不参与任何判定（Spec 009 TB-3），
# 它只是上下文；真正的 hard gate 在 Patch schema 与应用后的 DSL 全量校验处
# （Spec 010 DD-24 / S-6）。


class RefineHistoryTurn(BaseModel):
    """一个已确认精修轮次的请求级摘要（无 role、无模型输出原文、无 props 快照）。"""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    instruction: str = Field(min_length=1, max_length=1000)
    selected_node_id: str = Field(
        alias="selectedNodeId",
        min_length=1,
        max_length=128,
    )
    node_type: RegisteredNodeType = Field(alias="nodeType")
    patch_props: dict[str, PatchPropValue] = Field(
        alias="patchProps",
        max_length=MAX_TURN_PROPS_KEYS,
    )
    # 可选：缺省 ≡ `{}`，因此 M4-03 客户端上传的旧 history 无需任何改动即被接受
    # （Spec 010 DD-24 / BC-7）。键数上界与 Style 白名单基数同源。
    patch_style: dict[str, StylePatchValue] = Field(
        alias="patchStyle",
        default_factory=dict,
        max_length=MAX_TURN_STYLE_KEYS,
    )


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
    # 已确认对话历史（可选）：缺省 / null / [] 三态行为等价（Spec 009 DD-10）。
    history: list[RefineHistoryTurn] | None = Field(
        default=None,
        max_length=MAX_HISTORY_TURNS,
    )

    @model_validator(mode="after")
    def _check_history_char_size(self) -> "RefineRequest":
        """序列化字符上界校验（Spec 009 DD-22）。

        放在 model_validator 而非 route handler，使 schema 自身即为完整校验器；
        逐 turn 结构校验通过后才统一判定整份 history 的体积。
        """
        if self.history:
            payload = [turn.model_dump(by_alias=True) for turn in self.history]
            if history_char_size(payload) > MAX_HISTORY_CHARS:
                raise ValueError(
                    f"history serialized size exceeds {MAX_HISTORY_CHARS} characters"
                )
        return self


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


# --- Generate API Models ---


class GenerateRequest(BaseModel):
    """POST /api/v1/dsl/generate 请求体。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str


class GenerateSuccess(BaseModel):
    """初稿生成成功响应。"""

    success: Literal[True]
    document: dict  # DslDocument.model_dump(mode="json")


class GenerateFailure(BaseModel):
    """初稿生成失败响应。"""

    success: Literal[False]
    error: ValidationErrorDetail
