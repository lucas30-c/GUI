"""
DSL v0.1 正向测试 — 验证合法文档能通过校验
"""

import json
from pathlib import Path

import pytest

from genui_api.contracts.dsl import DslDocument
from genui_api.contracts.validation import validate_dsl_document, validate_dsl_json

# Gold Case 文件路径
_EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "examples" / "dsl"
_GOLD_CASE_PATH = _EXAMPLES_DIR / "coffee-shop-landing.json"


class TestMinimalDocument:
    """最小合法 DSL 文档"""

    def test_minimal_page_only(self):
        """只有 Page 根节点的最小文档应该通过校验"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
            },
        }
        doc = validate_dsl_document(data)
        assert doc.root.type == "Page"
        assert doc.root.id == "page"
        assert doc.root.children == []

    def test_empty_children_is_valid(self):
        """children 为空列表是允许的"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "children": [],
            },
        }
        doc = validate_dsl_document(data)
        assert doc.root.children == []


class TestGoldCase:
    """完整咖啡店 Gold Case"""

    def test_coffee_shop_landing_passes_validation(self):
        """读取 examples/dsl/coffee-shop-landing.json 并通过校验"""
        raw_json = _GOLD_CASE_PATH.read_text(encoding="utf-8")
        doc = validate_dsl_json(raw_json)
        assert doc.version == "0.1"
        assert doc.root.type == "Page"
        assert doc.root.id == "page"
        # 应有 3 个顶层 section
        assert len(doc.root.children) == 3


class TestAllComponentTypes:
    """九种合法组件的代表性组合"""

    def test_all_nine_component_types(self):
        """文档中包含全部 9 种组件类型应通过校验"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {"title": "测试页面"},
                "children": [
                    {
                        "id": "sec",
                        "type": "Section",
                        "children": [
                            {
                                "id": "sec.heading",
                                "type": "Heading",
                                "props": {"text": "标题", "level": 1},
                            },
                            {
                                "id": "sec.text",
                                "type": "Text",
                                "props": {"text": "正文内容"},
                            },
                            {
                                "id": "sec.button",
                                "type": "Button",
                                "props": {"text": "点击"},
                            },
                            {
                                "id": "sec.image",
                                "type": "Image",
                                "props": {"src": "/img.png", "alt": "图片"},
                            },
                        ],
                    },
                    {
                        "id": "card",
                        "type": "Card",
                        "props": {"title": "卡片"},
                        "children": [
                            {
                                "id": "card.text",
                                "type": "Text",
                                "props": {"text": "卡片内容"},
                            }
                        ],
                    },
                    {
                        "id": "form",
                        "type": "Form",
                        "props": {"name": "my-form"},
                        "children": [
                            {
                                "id": "form.input",
                                "type": "Input",
                                "props": {
                                    "name": "email",
                                    "label": "邮箱",
                                    "inputType": "email",
                                },
                            },
                            {
                                "id": "form.submit",
                                "type": "Button",
                                "props": {"text": "提交"},
                            },
                        ],
                    },
                ],
            },
        }
        doc = validate_dsl_document(data)
        assert doc.root.type == "Page"
        # 包含 Section, Card, Form 三个容器
        assert len(doc.root.children) == 3


class TestValidNodeIds:
    """合法稳定 ID 格式"""

    @pytest.mark.parametrize(
        "node_id",
        [
            "page",
            "hero",
            "hero.title",
            "hero.primary-button",
            "coffee-menu.card-1",
            "a",
            "section1",
            "my-component.sub-part",
            "a.b.c.d",
            "x1-y2.z3",
        ],
    )
    def test_valid_id_formats(self, node_id: str):
        """各种合法 ID 格式应通过校验"""
        data = {
            "version": "0.1",
            "root": {
                "id": node_id,
                "type": "Page",
            },
        }
        doc = validate_dsl_document(data)
        assert doc.root.id == node_id


class TestValidStyle:
    """合法受控 style 字段"""

    def test_full_style_fields(self):
        """带完整 style 字段的节点应通过校验"""
        data = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "style": {
                    "color": "#333",
                    "backgroundColor": "#fff",
                    "fontSize": "16px",
                    "fontWeight": "bold",
                    "textAlign": "center",
                    "width": "100%",
                    "height": "200px",
                    "padding": "16px",
                    "margin": "8px",
                    "borderRadius": "8px",
                    "gap": "12px",
                },
                "children": [],
            },
        }
        doc = validate_dsl_document(data)
        assert doc.root.style is not None
        assert doc.root.style.color == "#333"
        assert doc.root.style.gap == "12px"


class TestValidateJsonEntry:
    """JSON 字符串校验入口"""

    def test_validate_dsl_json_works(self):
        """validate_dsl_json 接收合法 JSON 字符串并正确工作"""
        raw = json.dumps(
            {
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
                                    "id": "sec.heading",
                                    "type": "Heading",
                                    "props": {"text": "Hello", "level": 2},
                                }
                            ],
                        }
                    ],
                },
            }
        )
        doc = validate_dsl_json(raw)
        assert doc.version == "0.1"
        assert doc.root.id == "page"
