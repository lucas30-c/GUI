"""
DSL v0.1 数据模型定义

使用 Pydantic v2 定义 GenUI DSL 的完整类型系统，包含：
- 节点 ID 格式约束
- 九种组件的 Props 模型
- 受控 Style 模型
- 基于 discriminated union 的节点树
- 顶层 DslDocument 模型
"""

from __future__ import annotations

import re
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ============================================================
# 节点 ID 类型约束
# ============================================================

# ID 正则：小写字母开头，后续允许小写字母/数字，段之间用 . 或 - 分隔
_NODE_ID_PATTERN = r"^[a-z][a-z0-9]*(?:[.\-][a-z0-9]+)*$"
_NODE_ID_MAX_LENGTH = 128

NodeId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=_NODE_ID_MAX_LENGTH,
        pattern=_NODE_ID_PATTERN,
        description="节点唯一标识符，格式：小写字母开头，段间用 . 或 - 分隔",
    ),
]

# ============================================================
# 受控 Style 模型 v2（Box Model + Layout + Typography + Border）
# ============================================================

# 颜色格式：# + 3-8 位 hex，或命名色白名单
_COLOR_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_NAMED_COLORS = frozenset(["black", "white", "transparent"])

# CssLength：允许 "0"（无单位零值）或 数字+单位
_CSS_LENGTH_RE = re.compile(r"^(0|[0-9]+(\.[0-9]+)?(px|rem|em|%))$")

# MarginAtom：CssLength 或 "auto"
_MARGIN_ATOM_RE = re.compile(r"^(auto|0|[0-9]+(\.[0-9]+)?(px|rem|em|%))$")

# MarginShorthand：1-4 个 MarginAtom 空格分隔
_MARGIN_SHORTHAND_RE = re.compile(
    r"^(auto|0|[0-9]+(\.[0-9]+)?(px|rem|em|%))"
    r"( (auto|0|[0-9]+(\.[0-9]+)?(px|rem|em|%))){0,3}$"
)

# PaddingShorthand：1-4 个 CssLength 空格分隔（不允许 auto）
_PADDING_SHORTHAND_RE = re.compile(
    r"^(0|[0-9]+(\.[0-9]+)?(px|rem|em|%))"
    r"( (0|[0-9]+(\.[0-9]+)?(px|rem|em|%))){0,3}$"
)

# LineHeight：CssLength 或 无单位非负数字倍数（CSS 标准行高写法，如 "1.5"）
_LINE_HEIGHT_RE = re.compile(
    r"^(0|[0-9]+(\.[0-9]+)?(px|rem|em|%)|[0-9]+(\.[0-9]+)?)$"
)

# 注入安全正则：不允许分号、括号、url()、expression() 等
_UNSAFE_RE = re.compile(r"[;(){}]|url\s*\(|expression\s*\(|javascript\s*:", re.IGNORECASE)


def _validate_color(v: str) -> str:
    """校验颜色值：# + 3-8 位 hex 或命名色白名单"""
    if _UNSAFE_RE.search(v):
        raise ValueError(f"颜色值包含非法字符，实际值: {v!r}")
    if _COLOR_HEX_RE.match(v) or v in _NAMED_COLORS:
        return v
    raise ValueError(
        f"颜色值必须为 #hex（3-8位）或命名色（black/white/transparent），"
        f"实际值: {v!r}"
    )


def _validate_css_length(v: str) -> str:
    """校验 CssLength：'0' 或 数字+单位"""
    if _UNSAFE_RE.search(v):
        raise ValueError(f"尺寸值包含非法字符，实际值: {v!r}")
    if _CSS_LENGTH_RE.match(v):
        return v
    raise ValueError(
        f"尺寸值必须为 '0' 或 数字+单位(px/rem/em/%)，实际值: {v!r}"
    )


def _validate_margin_atom(v: str) -> str:
    """校验 MarginAtom：CssLength 或 'auto'"""
    if _UNSAFE_RE.search(v):
        raise ValueError(f"margin 值包含非法字符，实际值: {v!r}")
    if _MARGIN_ATOM_RE.match(v):
        return v
    raise ValueError(
        f"margin 值必须为 '0'、数字+单位(px/rem/em/%) 或 'auto'，实际值: {v!r}"
    )


def _validate_margin_shorthand(v: str) -> str:
    """校验 MarginShorthand：1-4 个 MarginAtom 空格分隔"""
    if _UNSAFE_RE.search(v):
        raise ValueError(f"margin 值包含非法字符，实际值: {v!r}")
    if _MARGIN_SHORTHAND_RE.match(v):
        return v
    raise ValueError(
        f"margin 必须为 1-4 个值（'0'/数字+单位/'auto'）空格分隔，实际值: {v!r}"
    )


def _validate_padding_shorthand(v: str) -> str:
    """校验 PaddingShorthand：1-4 个 CssLength 空格分隔（不允许 auto）"""
    if _UNSAFE_RE.search(v):
        raise ValueError(f"padding 值包含非法字符，实际值: {v!r}")
    if _PADDING_SHORTHAND_RE.match(v):
        return v
    raise ValueError(
        f"padding 必须为 1-4 个值（'0'/数字+单位）空格分隔，不允许 auto，实际值: {v!r}"
    )


def _validate_line_height(v: str) -> str:
    """校验 LineHeight：CssLength 或无单位非负数字倍数（如 "1.5"）"""
    if _UNSAFE_RE.search(v):
        raise ValueError(f"lineHeight 值包含非法字符，实际值: {v!r}")
    if _LINE_HEIGHT_RE.match(v):
        return v
    raise ValueError(
        f"lineHeight 必须为 '0'、数字+单位(px/rem/em/%) 或无单位非负数字倍数，"
        f"实际值: {v!r}"
    )


class Style(BaseModel):
    """受控 Style DSL v2 — Box Model + Layout + Typography + Border。

    31 个白名单字段，extra=forbid 拒绝一切未列出属性。
    每个字段使用其专属值域类型（CssLength / MarginAtom / MarginShorthand /
    PaddingShorthand / LineHeight / Color / 枚举），不再共用单一尺寸正则。
    字段的机器可读元数据由 contracts.style_registry 从本模型派生（单一事实来源）。
    """

    model_config = ConfigDict(extra="forbid")

    # --- Box Model: Margin ---
    margin: Optional[str] = None                  # shorthand 1-4 MarginAtom
    marginTop: Optional[str] = None               # MarginAtom
    marginRight: Optional[str] = None             # MarginAtom
    marginBottom: Optional[str] = None            # MarginAtom
    marginLeft: Optional[str] = None              # MarginAtom

    # --- Box Model: Padding ---
    padding: Optional[str] = None                 # shorthand 1-4 CssLength
    paddingTop: Optional[str] = None              # CssLength
    paddingRight: Optional[str] = None            # CssLength
    paddingBottom: Optional[str] = None           # CssLength
    paddingLeft: Optional[str] = None             # CssLength

    # --- Box Model: Gap ---
    gap: Optional[str] = None                     # CssLength
    rowGap: Optional[str] = None                  # CssLength
    columnGap: Optional[str] = None               # CssLength

    # --- Sizing ---
    width: Optional[str] = None                   # CssLength
    height: Optional[str] = None                  # CssLength
    maxWidth: Optional[str] = None                # CssLength
    minWidth: Optional[str] = None                # CssLength

    # --- Color ---
    color: Optional[str] = None
    backgroundColor: Optional[str] = None

    # --- Typography ---
    fontSize: Optional[str] = None                # CssLength
    fontWeight: Optional[Literal["normal", "medium", "semibold", "bold"]] = None
    textAlign: Optional[Literal["left", "center", "right"]] = None
    lineHeight: Optional[str] = None              # LineHeight（CssLength 或无单位倍数）

    # --- Layout ---
    display: Optional[Literal["block", "flex", "grid", "inline", "none"]] = None
    flexDirection: Optional[Literal["row", "column", "row-reverse", "column-reverse"]] = None
    justifyContent: Optional[Literal[
        "flex-start", "flex-end", "center", "space-between", "space-around", "space-evenly"
    ]] = None
    alignItems: Optional[Literal[
        "flex-start", "flex-end", "center", "stretch", "baseline"
    ]] = None

    # --- Border ---
    borderWidth: Optional[str] = None             # CssLength
    borderStyle: Optional[Literal["solid", "dashed", "dotted", "none"]] = None
    borderColor: Optional[str] = None
    borderRadius: Optional[str] = None            # CssLength

    # --- Validators ---

    @field_validator("color", "backgroundColor", "borderColor", mode="after")
    @classmethod
    def _check_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_color(v)
        return v

    @field_validator(
        "fontSize", "width", "height", "maxWidth", "minWidth",
        "gap", "rowGap", "columnGap",
        "borderWidth", "borderRadius",
        "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
        mode="after",
    )
    @classmethod
    def _check_css_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_css_length(v)
        return v

    @field_validator("lineHeight", mode="after")
    @classmethod
    def _check_line_height(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_line_height(v)
        return v

    @field_validator("margin", mode="after")
    @classmethod
    def _check_margin(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_margin_shorthand(v)
        return v

    @field_validator("marginTop", "marginRight", "marginBottom", "marginLeft", mode="after")
    @classmethod
    def _check_margin_atom(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_margin_atom(v)
        return v

    @field_validator("padding", mode="after")
    @classmethod
    def _check_padding(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_padding_shorthand(v)
        return v


# ============================================================
# 各组件 Props 模型
# ============================================================


class PageProps(BaseModel):
    """Page 组件属性"""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, max_length=200)


class SectionProps(BaseModel):
    """Section 组件属性"""

    model_config = ConfigDict(extra="forbid")

    ariaLabel: Optional[str] = Field(default=None, max_length=200)


class HeadingProps(BaseModel):
    """Heading 组件属性"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=2000)
    level: int = Field(ge=1, le=6)


class TextProps(BaseModel):
    """Text 组件属性"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=2000)


class ButtonProps(BaseModel):
    """Button 组件属性，禁止事件字段"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=200)
    variant: Optional[Literal["primary", "secondary", "ghost"]] = None
    disabled: Optional[bool] = None


class ImageProps(BaseModel):
    """Image 组件属性，禁止 javascript:/vbscript: URL"""

    model_config = ConfigDict(extra="forbid")

    src: str = Field(max_length=2048)
    alt: str = Field(max_length=200)

    @field_validator("src")
    @classmethod
    def _forbid_dangerous_src(cls, v: str) -> str:
        """禁止 javascript: 和 vbscript: 协议的图片地址"""
        stripped = v.strip().lower()
        if stripped.startswith("javascript:") or stripped.startswith("vbscript:"):
            raise ValueError("Image src 禁止使用 javascript:/vbscript: 协议")
        return v


class CardProps(BaseModel):
    """Card 组件属性"""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, max_length=200)


class FormProps(BaseModel):
    """Form 组件属性"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=128)


class InputProps(BaseModel):
    """Input 组件属性"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=128)
    label: str = Field(max_length=200)
    inputType: Optional[Literal["text", "email", "tel", "number"]] = None
    placeholder: Optional[str] = Field(default=None, max_length=200)
    required: Optional[bool] = None


# ============================================================
# 节点模型（discriminated union by type）
# ============================================================


class PageNode(BaseModel):
    """Page 节点 — 必须且只能作为根节点"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Page"]
    props: PageProps = Field(default_factory=PageProps)
    style: Optional[Style] = None
    children: List["DslNode"] = Field(default_factory=list)


class SectionNode(BaseModel):
    """Section 节点 — 容器"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Section"]
    props: SectionProps = Field(default_factory=SectionProps)
    style: Optional[Style] = None
    children: List["DslNode"] = Field(default_factory=list)


class HeadingNode(BaseModel):
    """Heading 节点 — 叶子"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Heading"]
    props: HeadingProps
    style: Optional[Style] = None


class TextNode(BaseModel):
    """Text 节点 — 叶子"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Text"]
    props: TextProps
    style: Optional[Style] = None


class ButtonNode(BaseModel):
    """Button 节点 — 叶子"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Button"]
    props: ButtonProps
    style: Optional[Style] = None


class ImageNode(BaseModel):
    """Image 节点 — 叶子"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Image"]
    props: ImageProps
    style: Optional[Style] = None


class CardNode(BaseModel):
    """Card 节点 — 容器"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Card"]
    props: CardProps = Field(default_factory=CardProps)
    style: Optional[Style] = None
    children: List["DslNode"] = Field(default_factory=list)


class FormNode(BaseModel):
    """Form 节点 — 容器"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Form"]
    props: FormProps = Field(default_factory=FormProps)
    style: Optional[Style] = None
    children: List["DslNode"] = Field(default_factory=list)


class InputNode(BaseModel):
    """Input 节点 — 叶子"""

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    type: Literal["Input"]
    props: InputProps
    style: Optional[Style] = None


# Discriminated Union：根据 type 字段区分节点类型
DslNode = Annotated[
    Union[
        PageNode,
        SectionNode,
        HeadingNode,
        TextNode,
        ButtonNode,
        ImageNode,
        CardNode,
        FormNode,
        InputNode,
    ],
    Field(discriminator="type"),
]

# 更新 forward references
PageNode.model_rebuild()
SectionNode.model_rebuild()
CardNode.model_rebuild()
FormNode.model_rebuild()


# ============================================================
# Metadata 模型
# ============================================================


class DslMetadata(BaseModel):
    """文档元数据，仅允许预定义字段"""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    description: Optional[str] = None


# ============================================================
# 顶层 DslDocument 模型
# ============================================================


class DslDocument(BaseModel):
    """DSL v0.1 文档顶层结构"""

    model_config = ConfigDict(extra="forbid")

    version: Literal["0.1"]
    root: PageNode
    metadata: Optional[DslMetadata] = None
