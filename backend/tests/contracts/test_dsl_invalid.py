"""
DSL v0.1 反向测试 — 验证非法文档被正确拒绝并返回具体错误
"""

import pytest

from genui_api.contracts.validation import (
    DslJsonParseError,
    DslValidationError,
    validate_dsl_document,
    validate_dsl_json,
)


def _make_doc(root_override: dict) -> dict:
    """构建最小文档，允许覆写 root 节点"""
    base_root = {"id": "page", "type": "Page"}
    base_root.update(root_override)
    return {"version": "0.1", "root": base_root}


def _find_error_code(exc: DslValidationError, code: str) -> bool:
    """检查异常中是否包含指定 code 的错误"""
    return any(e.code == code for e in exc.errors)


class TestInvalidJson:
    """非法 JSON 字符串"""

    def test_invalid_json_raises_parse_error(self):
        """不是有效 JSON 字符串应抛出 DslJsonParseError"""
        with pytest.raises(DslJsonParseError):
            validate_dsl_json("这不是JSON{{{")

    def test_empty_string_raises_parse_error(self):
        """空字符串应抛出 DslJsonParseError"""
        with pytest.raises(DslJsonParseError):
            validate_dsl_json("")


class TestVersionError:
    """version 字段错误"""

    def test_wrong_version_number(self):
        """version 不是 '0.1' 应被拒绝"""
        data = {
            "version": "1.0",
            "root": {"id": "page", "type": "Page"},
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    def test_missing_version(self):
        """缺少 version 字段应被拒绝"""
        data = {"root": {"id": "page", "type": "Page"}}
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestRootNotPage:
    """root 不是 Page 类型"""

    def test_root_is_section(self):
        """root 节点 type 不是 Page 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {"id": "sec", "type": "Section"},
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestPageNested:
    """Page 出现在非根位置"""

    def test_page_as_child(self):
        """Page 作为子节点应产生 invalid_nesting 错误"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "nested-page",
                        "type": "Page",
                        "children": [],
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "invalid_nesting")


class TestDuplicateId:
    """重复节点 ID"""

    def test_duplicate_id_rejected(self):
        """两个节点使用相同 id 应产生 duplicate_id 错误"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "same-id",
                        "type": "Section",
                        "children": [
                            {
                                "id": "same-id",
                                "type": "Heading",
                                "props": {"text": "标题", "level": 1},
                            }
                        ],
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "duplicate_id")


class TestInvalidNodeId:
    """非法节点 ID 格式"""

    @pytest.mark.parametrize(
        "bad_id,desc",
        [
            ("Hero", "大写字母开头"),
            ("hero_primary_button", "包含下划线"),
            ("1hero", "数字开头"),
            ("hero..button", "连续两个点"),
            ("hero primary", "包含空格"),
        ],
    )
    def test_invalid_id_format(self, bad_id: str, desc: str):
        """非法 ID 格式应被拒绝: {desc}"""
        data = {
            "version": "0.1",
            "root": {
                "id": bad_id,
                "type": "Page",
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    def test_empty_id_rejected(self):
        """空字符串 ID 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "",
                "type": "Page",
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestUnknownComponentType:
    """未知组件类型"""

    @pytest.mark.parametrize("bad_type", ["Div", "Unknown", "Span"])
    def test_unknown_type_rejected(self, bad_type: str):
        """type 为未知值应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "bad-node",
                        "type": bad_type,
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestUnknownNodeField:
    """未知节点字段"""

    def test_extra_field_on_node_rejected(self):
        """节点有额外字段如 onClick 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "sec",
                        "type": "Section",
                        "onClick": "doSomething()",
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestUnknownPropsField:
    """未知 props 字段"""

    def test_extra_props_field_rejected(self):
        """props 中有未定义字段应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "heading",
                        "type": "Heading",
                        "props": {
                            "text": "标题",
                            "level": 1,
                            "color": "red",  # 未定义的 props 字段
                        },
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestUnknownStyleField:
    """未知 style 字段"""

    @pytest.mark.parametrize("bad_field", ["position", "zIndex", "opacity"])
    def test_forbidden_style_field_rejected(self, bad_field: str):
        """style 中有未允许字段应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "style": {bad_field: "block"},
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestMissingRequiredProps:
    """缺少组件必填 props"""

    def test_heading_missing_text(self):
        """Heading 缺少 text 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "heading",
                        "type": "Heading",
                        "props": {"level": 1},
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    def test_heading_missing_level(self):
        """Heading 缺少 level 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "heading",
                        "type": "Heading",
                        "props": {"text": "标题"},
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestHeadingLevelRange:
    """Heading level 超出范围"""

    @pytest.mark.parametrize("bad_level", [0, 7, -1, 100])
    def test_invalid_heading_level(self, bad_level: int):
        """level={bad_level} 超出 1-6 范围应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "heading",
                        "type": "Heading",
                        "props": {"text": "标题", "level": bad_level},
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestLeafNodeChildren:
    """叶子节点包含 children"""

    @pytest.mark.parametrize(
        "node_type,props",
        [
            ("Heading", {"text": "标题", "level": 1}),
            ("Text", {"text": "内容"}),
            ("Button", {"text": "按钮"}),
            ("Image", {"src": "/img.png", "alt": "图片"}),
        ],
    )
    def test_leaf_with_children_rejected(self, node_type: str, props: dict):
        """叶子节点 {node_type} 有 children 字段应被拒绝"""
        # 叶子节点的模型使用 extra="forbid"，children 是额外字段
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "leaf-node",
                        "type": node_type,
                        "props": props,
                        "children": [
                            {
                                "id": "child",
                                "type": "Text",
                                "props": {"text": "子节点"},
                            }
                        ],
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestInputOutsideForm:
    """Input 出现在 Form 之外"""

    def test_input_in_section_rejected(self):
        """Input 直接放在 Section 中应产生 invalid_nesting 错误"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "sec",
                        "type": "Section",
                        "children": [
                            {
                                "id": "sec.input",
                                "type": "Input",
                                "props": {"name": "field", "label": "字段"},
                            }
                        ],
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "invalid_nesting")

    def test_input_directly_in_page_rejected(self):
        """Input 直接放在 Page 中应产生 invalid_nesting 错误"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "page.input",
                        "type": "Input",
                        "props": {"name": "field", "label": "字段"},
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "invalid_nesting")


class TestFormInvalidChildren:
    """Form 包含非法子组件"""

    @pytest.mark.parametrize(
        "child_type,child_props",
        [
            ("Image", {"src": "/img.png", "alt": "图片"}),
            ("Section", {}),
        ],
    )
    def test_form_with_forbidden_child(self, child_type: str, child_props: dict):
        """Form 内放入 {child_type} 应产生 invalid_nesting 错误"""
        child = {
            "id": "form.bad-child",
            "type": child_type,
        }
        if child_props:
            child["props"] = child_props
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "form",
                        "type": "Form",
                        "children": [child],
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "invalid_nesting")


class TestImageJavascriptUrl:
    """Image 使用 javascript:/vbscript: URL"""

    def test_javascript_src_rejected(self):
        """src 为 'javascript:alert(1)' 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "img",
                        "type": "Image",
                        "props": {
                            "src": "javascript:alert(1)",
                            "alt": "恶意图片",
                        },
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    def test_vbscript_src_rejected(self):
        """src 为 'vbscript:msgbox' 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "img",
                        "type": "Image",
                        "props": {
                            "src": "vbscript:msgbox",
                            "alt": "恶意图片",
                        },
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    def test_vbscript_case_insensitive_rejected(self):
        """src 为 '  VBScript:...' 大小写混合也应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "img",
                        "type": "Image",
                        "props": {
                            "src": "  VBScript:Execute",
                            "alt": "恶意图片",
                        },
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestButtonOnClickForbidden:
    """Button 出现 onClick 或类似未授权事件字段"""

    def test_onclick_in_button_props_rejected(self):
        """Button props 中加入 onClick 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "btn",
                        "type": "Button",
                        "props": {
                            "text": "点击",
                            "onClick": "handleClick()",
                        },
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")


class TestStyleValueConstraints:
    """Style 字段值约束"""

    @pytest.mark.parametrize(
        "field,bad_value,desc",
        [
            ("color", "red", "非白名单命名色"),
            ("color", "rgb(0,0,0)", "rgb 格式不允许"),
            ("backgroundColor", "rgba(0,0,0,1)", "rgba 格式不允许"),
            ("fontWeight", "700", "数字格式的 fontWeight 不允许"),
            ("fontWeight", "light", "非白名单 fontWeight 值"),
            ("textAlign", "justify", "textAlign 不允许 justify"),
            ("textAlign", "start", "textAlign 不允许 start"),
            ("fontSize", "large", "尺寸必须为 数字+单位"),
            ("fontSize", "auto", "尺寸不允许 auto"),
            ("width", "fit-content", "尺寸不允许 fit-content"),
            ("height", "auto", "尺寸不允许 auto"),
            ("padding", "16px auto", "padding 不允许 auto"),
            ("padding", "1px 2px 3px 4px 5px", "padding shorthand 最多 4 值"),
            ("margin", "1px 2px 3px 4px 5px", "margin shorthand 最多 4 值"),
            ("margin", "abc", "非法 margin 值"),
            ("display", "inline-block", "display 只允许 block/flex/grid/inline/none"),
        ],
    )
    def test_invalid_style_value_rejected(self, field: str, bad_value: str, desc: str):
        """非法 style 值 {field}={bad_value} ({desc}) 应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "style": {field: bad_value},
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    @pytest.mark.parametrize(
        "field,good_value",
        [
            ("color", "#333"),
            ("color", "#ff00ff"),
            ("color", "#aabbccdd"),
            ("color", "black"),
            ("color", "white"),
            ("color", "transparent"),
            ("backgroundColor", "#f9f5f0"),
            ("fontWeight", "normal"),
            ("fontWeight", "bold"),
            ("fontWeight", "semibold"),
            ("fontWeight", "medium"),
            ("textAlign", "left"),
            ("textAlign", "center"),
            ("textAlign", "right"),
            ("fontSize", "16px"),
            ("fontSize", "1.5rem"),
            ("width", "100%"),
            ("height", "200px"),
            ("padding", "24px"),
            ("margin", "8px"),
            ("borderRadius", "4px"),
            ("gap", "1.5em"),
        ],
    )
    def test_valid_style_value_accepted(self, field: str, good_value: str):
        """合法 style 值 {field}={good_value} 应通过校验"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "style": {field: good_value},
            },
        }
        doc = validate_dsl_document(data)
        assert getattr(doc.root.style, field) == good_value


class TestTextLengthLimits:
    """文本字段长度限制"""

    def test_title_exceeds_200(self):
        """Page title 超过 200 字符应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {"title": "x" * 201},
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    def test_text_exceeds_2000(self):
        """Text.text 超过 2000 字符应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "txt",
                        "type": "Text",
                        "props": {"text": "x" * 2001},
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    def test_src_exceeds_2048(self):
        """Image.src 超过 2048 字符应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "img",
                        "type": "Image",
                        "props": {
                            "src": "/" + "x" * 2048,
                            "alt": "图片",
                        },
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")

    def test_name_exceeds_128(self):
        """Input.name 超过 128 字符应被拒绝"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [
                    {
                        "id": "form",
                        "type": "Form",
                        "children": [
                            {
                                "id": "form.input",
                                "type": "Input",
                                "props": {
                                    "name": "x" * 129,
                                    "label": "标签",
                                },
                            }
                        ],
                    }
                ],
            },
        }
        with pytest.raises(DslValidationError) as exc_info:
            validate_dsl_document(data)
        assert _find_error_code(exc_info.value, "schema_error")
