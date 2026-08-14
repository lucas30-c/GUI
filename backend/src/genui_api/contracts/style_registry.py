"""Style 字段注册表 — Style DSL v2 字段元数据的唯一事实来源。

设计动机（根因修复 RC2）：Style 白名单曾以多份手写副本存在（后端模型、
生成 SP、精修 SP、repair prompt、前端类型），任何一份漂移都会让模型收到
互相矛盾的约束。本模块从 `contracts.dsl.Style` 模型**派生**全部字段元数据：

- 字段集合：直接取 `Style.model_fields`，与模型结构性一致（extra=forbid 保证封闭）。
- 枚举值域：从字段的 `Literal[...]` 注解内省，不手写副本。
- 值域类别（CssLength / MarginAtom / MarginShorthand / PaddingShorthand /
  LineHeight / Color / Enum）：按类别显式声明一次，导入期即与模型字段集做
  双向比对，任何一侧增删字段而另一侧未跟上都会立刻 RuntimeError（fail fast）。

下游消费者（禁止再手写字段列表）：
- `llm.prompts`：生成/精修 System Prompt 的 style 白名单段落由此渲染；
- `generation.pipeline`：repair prompt 的机器可读约束由此构造；
- 测试：契约一致性测试断言 SP 文本、JSON Schema、前端白名单与本注册表一致。
"""
from __future__ import annotations

import typing
from dataclasses import dataclass

from genui_api.contracts.dsl import Style

# ============================================================
# 值域类别与文法（机器可读 + 人类可读）
# ============================================================

CATEGORY_CSS_LENGTH = "css_length"
CATEGORY_MARGIN_ATOM = "margin_atom"
CATEGORY_MARGIN_SHORTHAND = "margin_shorthand"
CATEGORY_PADDING_SHORTHAND = "padding_shorthand"
CATEGORY_LINE_HEIGHT = "line_height"
CATEGORY_COLOR = "color"
CATEGORY_ENUM = "enum"

# 每个类别的文法描述（repair prompt 的机器可读约束与 SP 文本共用同一来源）
_CATEGORY_GRAMMAR: dict[str, str] = {
    CATEGORY_CSS_LENGTH: "'0' 或 数字+单位(px/rem/em/%)",
    CATEGORY_MARGIN_ATOM: "'0'、数字+单位(px/rem/em/%) 或 'auto'",
    CATEGORY_MARGIN_SHORTHAND: "1-4 个值空格分隔，每个值为 '0'、数字+单位(px/rem/em/%) 或 'auto'",
    CATEGORY_PADDING_SHORTHAND: "1-4 个值空格分隔，每个值为 '0' 或 数字+单位(px/rem/em/%)，不允许 auto",
    CATEGORY_LINE_HEIGHT: "'0'、数字+单位(px/rem/em/%) 或 无单位非负数字倍数",
    CATEGORY_COLOR: "#hex（3-8 位十六进制）或 'black' / 'white' / 'transparent'",
    CATEGORY_ENUM: "",  # 枚举类别在渲染时列出具体取值
}

_CATEGORY_EXAMPLES: dict[str, tuple[str, ...]] = {
    CATEGORY_CSS_LENGTH: ('"16px"', '"1.5rem"', '"100%"', '"0"'),
    CATEGORY_MARGIN_ATOM: ('"1rem"', '"auto"', '"0"'),
    CATEGORY_MARGIN_SHORTHAND: ('"0 auto"', '"1rem"', '"1rem 2rem"', '"0"'),
    CATEGORY_PADDING_SHORTHAND: ('"1rem"', '"1rem 2rem"', '"0"'),
    CATEGORY_LINE_HEIGHT: ('"1.5"', '"24px"', '"150%"'),
    CATEGORY_COLOR: ('"#c0392b"', '"white"', '"transparent"'),
    CATEGORY_ENUM: (),
}

# ============================================================
# 字段 → 类别映射（唯一一次显式声明；枚举值域从模型内省）
# ============================================================

_FIELD_CATEGORIES: dict[str, str] = {
    # Box Model: Margin
    "margin": CATEGORY_MARGIN_SHORTHAND,
    "marginTop": CATEGORY_MARGIN_ATOM,
    "marginRight": CATEGORY_MARGIN_ATOM,
    "marginBottom": CATEGORY_MARGIN_ATOM,
    "marginLeft": CATEGORY_MARGIN_ATOM,
    # Box Model: Padding
    "padding": CATEGORY_PADDING_SHORTHAND,
    "paddingTop": CATEGORY_CSS_LENGTH,
    "paddingRight": CATEGORY_CSS_LENGTH,
    "paddingBottom": CATEGORY_CSS_LENGTH,
    "paddingLeft": CATEGORY_CSS_LENGTH,
    # Box Model: Gap
    "gap": CATEGORY_CSS_LENGTH,
    "rowGap": CATEGORY_CSS_LENGTH,
    "columnGap": CATEGORY_CSS_LENGTH,
    # Sizing
    "width": CATEGORY_CSS_LENGTH,
    "height": CATEGORY_CSS_LENGTH,
    "maxWidth": CATEGORY_CSS_LENGTH,
    "minWidth": CATEGORY_CSS_LENGTH,
    # Color
    "color": CATEGORY_COLOR,
    "backgroundColor": CATEGORY_COLOR,
    # Typography
    "fontSize": CATEGORY_CSS_LENGTH,
    "fontWeight": CATEGORY_ENUM,
    "textAlign": CATEGORY_ENUM,
    "lineHeight": CATEGORY_LINE_HEIGHT,
    # Layout
    "display": CATEGORY_ENUM,
    "flexDirection": CATEGORY_ENUM,
    "justifyContent": CATEGORY_ENUM,
    "alignItems": CATEGORY_ENUM,
    # Border
    "borderWidth": CATEGORY_CSS_LENGTH,
    "borderStyle": CATEGORY_ENUM,
    "borderColor": CATEGORY_COLOR,
    "borderRadius": CATEGORY_CSS_LENGTH,
}

# SP 中的分组展示顺序（仅影响渲染，不影响契约）
_FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Box Model: Margin", ("margin", "marginTop", "marginRight", "marginBottom", "marginLeft")),
    ("Box Model: Padding", ("padding", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft")),
    ("Box Model: Gap", ("gap", "rowGap", "columnGap")),
    ("Sizing", ("width", "height", "maxWidth", "minWidth")),
    ("Color", ("color", "backgroundColor")),
    ("Typography", ("fontSize", "lineHeight", "fontWeight", "textAlign")),
    ("Layout", ("display", "flexDirection", "justifyContent", "alignItems")),
    ("Border", ("borderWidth", "borderStyle", "borderColor", "borderRadius")),
)


def _enum_values(field_name: str) -> tuple[str, ...]:
    """从 Style 模型的 Literal 注解内省枚举值域（不手写副本）。"""
    annotation = Style.model_fields[field_name].annotation
    for arg in typing.get_args(annotation):
        if typing.get_origin(arg) is typing.Literal:
            values = typing.get_args(arg)
            return tuple(str(v) for v in values)
    raise RuntimeError(
        f"Style field {field_name!r} is declared as enum category "
        f"but has no Literal annotation"
    )


def _verify_coverage() -> None:
    """导入期双向比对：类别映射与模型字段集必须完全一致。"""
    model_fields = set(Style.model_fields)
    declared = set(_FIELD_CATEGORIES)
    if model_fields != declared:
        raise RuntimeError(
            "Style registry drift detected: "
            f"model-only={sorted(model_fields - declared)} "
            f"registry-only={sorted(declared - model_fields)}"
        )
    grouped = [name for _group, names in _FIELD_GROUPS for name in names]
    if set(grouped) != declared or len(grouped) != len(declared):
        raise RuntimeError("Style registry group list drift detected")


_verify_coverage()


# ============================================================
# 公开 API
# ============================================================


def style_field_names() -> tuple[str, ...]:
    """全部白名单字段名（按模型声明顺序）。"""
    return tuple(Style.model_fields)


def style_field_count() -> int:
    return len(Style.model_fields)


def field_category(field_name: str) -> str:
    """字段的值域类别；未知字段抛 KeyError（调用方应先判断成员资格）。"""
    return _FIELD_CATEGORIES[field_name]


def field_grammar(field_name: str) -> str:
    """字段值域的文法描述（人类可读，中文）。"""
    category = _FIELD_CATEGORIES[field_name]
    if category == CATEGORY_ENUM:
        values = " / ".join(f'"{v}"' for v in _enum_values(field_name))
        return f"只能是 {values}"
    return _CATEGORY_GRAMMAR[category]


def field_examples(field_name: str) -> tuple[str, ...]:
    """字段的合法值示例。"""
    category = _FIELD_CATEGORIES[field_name]
    if category == CATEGORY_ENUM:
        values = _enum_values(field_name)
        return tuple(f'"{v}"' for v in values[:2])
    return _CATEGORY_EXAMPLES[category]


def field_enum_values(field_name: str) -> tuple[str, ...] | None:
    """枚举字段的取值；非枚举返回 None。"""
    if _FIELD_CATEGORIES[field_name] != CATEGORY_ENUM:
        return None
    return _enum_values(field_name)


def machine_contract() -> dict[str, dict[str, object]]:
    """机器可读的完整 style 契约（repair prompt 使用）。

    每个字段给出处置必需的全部信息：值域类别、文法、枚举取值、示例。
    """
    contract: dict[str, dict[str, object]] = {}
    for name in style_field_names():
        category = _FIELD_CATEGORIES[name]
        entry: dict[str, object] = {
            "valueType": category,
            "grammar": field_grammar(name),
            "examples": list(field_examples(name)),
        }
        enum_values = field_enum_values(name)
        if enum_values is not None:
            entry["allowedValues"] = list(enum_values)
        contract[name] = entry
    return contract


def render_style_contract_text() -> str:
    """渲染 SP 用的 style 白名单段落（确定性纯函数，逐字节稳定）。

    生成侧与精修侧 System Prompt 共用本段落——两处对 style 能力域的
    描述永远一致，因为它们来自同一个渲染函数。
    """
    lines: list[str] = []
    lines.append(f"# style 白名单（共 {style_field_count()} 个字段，不得出现其他属性）")
    for group_title, names in _FIELD_GROUPS:
        lines.append(f"\n## {group_title}")
        for name in names:
            grammar = field_grammar(name)
            examples = field_examples(name)
            example_text = f"。示例：{'、'.join(examples)}" if examples else ""
            lines.append(f"- {name}：{grammar}{example_text}")
    lines.append("")
    lines.append(
        "- **禁止使用白名单外的任何 style 字段**（如 position、zIndex、opacity、"
        "objectFit、boxShadow、transform、transition、animation 等均非法，"
        "会导致整份文档被拒绝）。"
    )
    lines.append("- 所有 style 值都必须是**字符串**类型。")
    lines.append(
        "- 禁止 CSS 函数（calc()、var()、url() 等）、分号、括号或任何可执行内容。"
    )
    return "\n".join(lines)
