"""Style DSL v2 Box Model 正反向契约测试（根因修复 RC1 / Owner 验收清单）。

覆盖字段专属值域类型：
- CssLength：'0' 或 数字+单位(px/rem/em/%)
- MarginAtom：CssLength | 'auto'
- MarginShorthand：1-4 个 MarginAtom（'0 auto' 必须合法）
- PaddingShorthand：1-4 个 CssLength（不允许 auto）
- LineHeight：CssLength | 无单位非负倍数
- 注入安全：分号 / 括号 / url() / expression() / javascript: 一律拒绝
- 白名单封闭：未知字段仍被 extra=forbid 拒绝
"""

import pytest

from genui_api.contracts.dsl import Style
from genui_api.contracts.validation import DslValidationError, validate_dsl_document


def _style_doc(style: dict) -> dict:
    return {
        "version": "0.1",
        "root": {"id": "page", "type": "Page", "style": style},
    }


def _assert_style_accepted(style: dict) -> None:
    doc = validate_dsl_document(_style_doc(style))
    assert doc.root.style is not None


def _assert_style_rejected(style: dict) -> None:
    with pytest.raises(DslValidationError):
        validate_dsl_document(_style_doc(style))


# ============================================================
# margin shorthand：1-4 值，auto 合法（Owner 复现场景的核心修复）
# ============================================================


@pytest.mark.parametrize(
    "value",
    [
        "0",           # 单值零
        "0 auto",      # 经典水平居中（Owner 复现值）
        "1rem auto",   # 尺寸 + auto
        "auto",        # 单值 auto
        "1rem",        # 单值尺寸
        "1rem 2rem",   # 2 值
        "1rem 2rem 3rem",        # 3 值
        "1rem 2rem 3rem 4rem",   # 4 值
        "0 0 0 0",
        "10px auto 10px auto",
        "1.5em 5%",
    ],
)
def test_margin_shorthand_valid_values_accepted(value):
    _assert_style_accepted({"margin": value})


@pytest.mark.parametrize(
    "value",
    [
        "1rem 2rem 3rem 4rem 5rem",  # 5 值拒绝
        "",                          # 空串
        " ",                         # 纯空格
        "1rem auto extra",           # 非法 token
        "auto auto auto auto auto",  # 5 值
    ],
)
def test_margin_shorthand_invalid_values_rejected(value):
    _assert_style_rejected({"margin": value})


# ============================================================
# 单边 margin：CssLength | auto
# ============================================================


@pytest.mark.parametrize(
    "field", ["marginTop", "marginRight", "marginBottom", "marginLeft"]
)
@pytest.mark.parametrize("value", ["1rem", "0", "auto", "16px", "5%"])
def test_single_side_margin_valid_values_accepted(field, value):
    _assert_style_accepted({field: value})


@pytest.mark.parametrize(
    "field", ["marginTop", "marginRight", "marginBottom", "marginLeft"]
)
@pytest.mark.parametrize("value", ["1rem 2rem", "auto auto", "abc"])
def test_single_side_margin_rejects_shorthand_and_invalid(field, value):
    _assert_style_rejected({field: value})


# ============================================================
# padding shorthand：1-4 值，auto 不允许
# ============================================================


@pytest.mark.parametrize(
    "value",
    ["1rem", "1rem 2rem", "1rem 2rem 3rem", "1rem 2rem 3rem 4rem", "0", "0 0"],
)
def test_padding_shorthand_valid_values_accepted(value):
    _assert_style_accepted({"padding": value})


@pytest.mark.parametrize(
    "value",
    [
        "auto",               # padding 不允许 auto
        "1rem auto",          # 任一值为 auto 都拒绝
        "1rem 2rem auto",
        "1rem 2rem 3rem 4rem 5rem",  # 5 值拒绝
    ],
)
def test_padding_shorthand_rejects_auto_and_five_values(value):
    _assert_style_rejected({"padding": value})


@pytest.mark.parametrize(
    "field", ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft"]
)
def test_single_side_padding_rejects_auto(field):
    _assert_style_rejected({field: "auto"})


@pytest.mark.parametrize(
    "field", ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft"]
)
@pytest.mark.parametrize("value", ["1rem", "0", "16px"])
def test_single_side_padding_valid_values_accepted(field, value):
    _assert_style_accepted({field: value})


# ============================================================
# gap / rowGap / columnGap：CssLength
# ============================================================


@pytest.mark.parametrize("field", ["gap", "rowGap", "columnGap"])
@pytest.mark.parametrize("value", ["16px", "1rem", "0"])
def test_gap_fields_accept_css_length(field, value):
    _assert_style_accepted({field: value})


@pytest.mark.parametrize("field", ["gap", "rowGap", "columnGap"])
def test_gap_fields_reject_auto_and_shorthand(field):
    _assert_style_rejected({field: "auto"})
    _assert_style_rejected({field: "1rem 2rem"})


# ============================================================
# lineHeight：CssLength 或无单位非负倍数
# ============================================================


@pytest.mark.parametrize("value", ["1.5", "2", "0", "24px", "150%", "1.2em"])
def test_line_height_accepts_unitless_multiplier_and_lengths(value):
    _assert_style_accepted({"lineHeight": value})


@pytest.mark.parametrize("value", ["auto", "normal", "1.5 2", "abc"])
def test_line_height_rejects_invalid_values(value):
    _assert_style_rejected({"lineHeight": value})


# ============================================================
# CssLength 通用规则：零值合法、无单位非零拒绝
# ============================================================


@pytest.mark.parametrize(
    "field", ["width", "height", "maxWidth", "minWidth", "fontSize", "borderRadius"]
)
def test_css_length_zero_without_unit_is_valid(field):
    _assert_style_accepted({field: "0"})


@pytest.mark.parametrize(
    "field", ["width", "height", "maxWidth", "minWidth", "fontSize", "borderRadius"]
)
@pytest.mark.parametrize("value", ["10", "1.5", "auto", "10 px", "10px 20px"])
def test_css_length_rejects_unitless_nonzero_auto_and_shorthand(field, value):
    _assert_style_rejected({field: value})


# ============================================================
# 注入安全：任何值域都不得放行脚本 / CSS 注入
# ============================================================


@pytest.mark.parametrize(
    "field", ["margin", "marginTop", "padding", "width", "lineHeight", "color"]
)
@pytest.mark.parametrize(
    "value",
    [
        "0; background: red",
        "url(javascript:alert(1))",
        "expression(alert(1))",
        "1rem); drop",
        "javascript:alert(1)",
        "0 auto; margin: 0",
    ],
)
def test_injection_payloads_rejected_across_value_types(field, value):
    _assert_style_rejected({field: value})


# ============================================================
# 白名单封闭：未知字段仍然被拒绝
# ============================================================


@pytest.mark.parametrize(
    "field",
    [
        "objectFit",
        "position",
        "zIndex",
        "opacity",
        "boxShadow",
        "transform",
        "gridTemplateColumns",
        "cursor",
        "overflow",
    ],
)
def test_unknown_style_field_still_rejected(field):
    _assert_style_rejected({field: "1px"})


def test_style_model_forbids_extra_fields():
    with pytest.raises(Exception):
        Style.model_validate({"margin": "0 auto", "evilField": "x"})


# ============================================================
# 组合场景：Owner 复现形态（Form.style.margin + Button.style.marginTop）
# ============================================================


def test_owner_reproduction_shape_now_passes_validation():
    """Owner 复现路径的等价结构：Section>Form 的 margin:'0 auto' + Button marginTop。"""
    data = {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "children": [
                {
                    "id": "cta",
                    "type": "Section",
                    "children": [
                        {
                            "id": "cta.form",
                            "type": "Form",
                            "style": {"margin": "0 auto", "maxWidth": "480px"},
                            "children": [
                                {
                                    "id": "cta.form.name",
                                    "type": "Input",
                                    "props": {"name": "name", "label": "姓名"},
                                },
                                {
                                    "id": "cta.form.submit",
                                    "type": "Button",
                                    "props": {"text": "提交"},
                                    "style": {"marginTop": "1rem"},
                                },
                            ],
                        }
                    ],
                }
            ],
        },
    }
    doc = validate_dsl_document(data)
    form = doc.root.children[0].children[0]
    assert form.style is not None
    assert form.style.margin == "0 auto"
    button = form.children[1]
    assert button.style is not None
    assert button.style.marginTop == "1rem"
