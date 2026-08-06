"""三套独立内置初稿模板（DD-10 / DD-11）。

约束：
- 每套模板是完整合法的 DSL v0.1 文档 dict，可直接通过 validate_dsl_document；
- 节点 ID 为语义化静态 ID，root 统一为 `page`；
- 内容独立于 Gold Case（examples/dsl/coffee-shop-landing.json），同 ID 节点文案不同；
- 不含时间戳、随机数或计数器，保证同一模板每次生成逐字段相等。

模块级常量只读：Provider 必须返回 `copy.deepcopy(常量)`（DD-12）。
"""
from __future__ import annotations

# ============================================================
# 模板 1：咖啡店落地页
# ============================================================

TEMPLATE_COFFEE_SHOP: dict = {
    "version": "0.1",
    "metadata": {
        "title": "咖啡店初稿",
        "description": "由 Mock Generation Provider 生成的咖啡店落地页初稿",
    },
    "root": {
        "id": "page",
        "type": "Page",
        "props": {"title": "晨光咖啡工坊"},
        "children": [
            {
                "id": "hero",
                "type": "Section",
                "props": {"ariaLabel": "首屏介绍"},
                "style": {
                    "padding": "56px",
                    "textAlign": "center",
                    "backgroundColor": "#fdf6ec",
                },
                "children": [
                    {
                        "id": "hero.title",
                        "type": "Heading",
                        "props": {"text": "晨光咖啡工坊", "level": 1},
                        "style": {"fontSize": "44px", "fontWeight": "bold", "color": "#3b2314"},
                    },
                    {
                        "id": "hero.subtitle",
                        "type": "Text",
                        "props": {"text": "清晨现烘的豆子，配一杯慢下来的时间"},
                        "style": {"fontSize": "18px", "color": "#6b4a32"},
                    },
                    {
                        "id": "hero.cta",
                        "type": "Button",
                        "props": {"text": "预订座位", "variant": "primary"},
                        "style": {"fontSize": "16px"},
                    },
                ],
            },
            {
                "id": "menu",
                "type": "Section",
                "props": {"ariaLabel": "本店饮品"},
                "style": {"padding": "40px", "gap": "20px"},
                "children": [
                    {
                        "id": "menu.title",
                        "type": "Heading",
                        "props": {"text": "本店饮品", "level": 2},
                        "style": {"textAlign": "center", "color": "#3b2314"},
                    },
                    {
                        "id": "menu.card-morning",
                        "type": "Card",
                        "props": {"title": "晨光特调"},
                        "style": {"padding": "16px", "borderRadius": "8px"},
                        "children": [
                            {
                                "id": "menu.card-morning.name",
                                "type": "Heading",
                                "props": {"text": "晨光特调", "level": 3},
                            },
                            {
                                "id": "menu.card-morning.desc",
                                "type": "Text",
                                "props": {"text": "浅烘豆底，柑橘尾韵，适合开启一天"},
                            },
                        ],
                    },
                    {
                        "id": "menu.card-dusk",
                        "type": "Card",
                        "props": {"title": "暮色冷萃"},
                        "style": {"padding": "16px", "borderRadius": "8px"},
                        "children": [
                            {
                                "id": "menu.card-dusk.name",
                                "type": "Heading",
                                "props": {"text": "暮色冷萃", "level": 3},
                            },
                            {
                                "id": "menu.card-dusk.desc",
                                "type": "Text",
                                "props": {"text": "十四小时慢萃，回甘干净"},
                            },
                        ],
                    },
                ],
            },
            {
                "id": "contact",
                "type": "Section",
                "props": {"ariaLabel": "到店信息"},
                "style": {"padding": "40px", "backgroundColor": "#fdf6ec"},
                "children": [
                    {
                        "id": "contact.title",
                        "type": "Heading",
                        "props": {"text": "到店信息", "level": 2},
                        "style": {"textAlign": "center", "color": "#3b2314"},
                    },
                    {
                        "id": "contact.hours",
                        "type": "Text",
                        "props": {"text": "每日 08:00 - 20:00，工作日可提前预留吧台位"},
                    },
                ],
            },
        ],
    },
}


# ============================================================
# 模板 2：活动报名表单页
# ============================================================

TEMPLATE_EVENT_SIGNUP: dict = {
    "version": "0.1",
    "metadata": {
        "title": "活动报名初稿",
        "description": "由 Mock Generation Provider 生成的活动报名表单页初稿",
    },
    "root": {
        "id": "page",
        "type": "Page",
        "props": {"title": "城市开发者夜话"},
        "children": [
            {
                "id": "intro",
                "type": "Section",
                "props": {"ariaLabel": "活动介绍"},
                "style": {"padding": "48px", "textAlign": "center", "backgroundColor": "#eef2ff"},
                "children": [
                    {
                        "id": "intro.title",
                        "type": "Heading",
                        "props": {"text": "城市开发者夜话", "level": 1},
                        "style": {"fontSize": "40px", "fontWeight": "bold", "color": "#1e2a5a"},
                    },
                    {
                        "id": "intro.desc",
                        "type": "Text",
                        "props": {"text": "一场只谈实践的线下分享，名额三十人，报名后邮件确认"},
                        "style": {"fontSize": "17px", "color": "#3f4a7a"},
                    },
                ],
            },
            {
                "id": "signup",
                "type": "Section",
                "props": {"ariaLabel": "报名区域"},
                "style": {"padding": "40px", "gap": "16px"},
                "children": [
                    {
                        "id": "signup.title",
                        "type": "Heading",
                        "props": {"text": "填写报名信息", "level": 2},
                        "style": {"color": "#1e2a5a"},
                    },
                    {
                        "id": "signup.form",
                        "type": "Form",
                        "props": {"name": "event-signup"},
                        "style": {"gap": "16px", "padding": "24px"},
                        "children": [
                            {
                                "id": "signup.form.name",
                                "type": "Input",
                                "props": {
                                    "name": "name",
                                    "label": "参会人姓名",
                                    "inputType": "text",
                                    "placeholder": "请输入姓名",
                                    "required": True,
                                },
                            },
                            {
                                "id": "signup.form.email",
                                "type": "Input",
                                "props": {
                                    "name": "email",
                                    "label": "确认邮箱",
                                    "inputType": "email",
                                    "placeholder": "name@example.com",
                                    "required": True,
                                },
                            },
                            {
                                "id": "signup.form.company",
                                "type": "Input",
                                "props": {
                                    "name": "company",
                                    "label": "所在团队",
                                    "inputType": "text",
                                    "placeholder": "可选",
                                },
                            },
                            {
                                "id": "signup.form.submit",
                                "type": "Button",
                                "props": {"text": "提交报名", "variant": "primary"},
                            },
                        ],
                    },
                    {
                        "id": "signup.note",
                        "type": "Text",
                        "props": {"text": "提交后如需修改信息，请直接回复确认邮件"},
                    },
                ],
            },
        ],
    },
}


# ============================================================
# 模板 3：产品介绍落地页
# ============================================================

TEMPLATE_PRODUCT_INTRO: dict = {
    "version": "0.1",
    "metadata": {
        "title": "产品介绍初稿",
        "description": "由 Mock Generation Provider 生成的产品介绍落地页初稿",
    },
    "root": {
        "id": "page",
        "type": "Page",
        "props": {"title": "Latchwork 协作台"},
        "children": [
            {
                "id": "hero",
                "type": "Section",
                "props": {"ariaLabel": "产品首屏"},
                "style": {"padding": "56px", "textAlign": "center", "backgroundColor": "#f2f7f4"},
                "children": [
                    {
                        "id": "hero.title",
                        "type": "Heading",
                        "props": {"text": "Latchwork 协作台", "level": 1},
                        "style": {"fontSize": "44px", "fontWeight": "bold", "color": "#14342b"},
                    },
                    {
                        "id": "hero.tagline",
                        "type": "Text",
                        "props": {"text": "把散落的需求、评审与交付记录收进同一条时间线"},
                        "style": {"fontSize": "18px", "color": "#2f5d4c"},
                    },
                    {
                        "id": "hero.cta",
                        "type": "Button",
                        "props": {"text": "免费试用", "variant": "primary"},
                        "style": {"fontSize": "16px"},
                    },
                ],
            },
            {
                "id": "features",
                "type": "Section",
                "props": {"ariaLabel": "核心特性"},
                "style": {"padding": "40px", "gap": "20px"},
                "children": [
                    {
                        "id": "features.title",
                        "type": "Heading",
                        "props": {"text": "三件事让交付不再返工", "level": 2},
                        "style": {"textAlign": "center", "color": "#14342b"},
                    },
                    {
                        "id": "features.card-trace",
                        "type": "Card",
                        "props": {"title": "全链路追溯"},
                        "style": {"padding": "16px", "borderRadius": "8px"},
                        "children": [
                            {
                                "id": "features.card-trace.name",
                                "type": "Heading",
                                "props": {"text": "全链路追溯", "level": 3},
                            },
                            {
                                "id": "features.card-trace.desc",
                                "type": "Text",
                                "props": {"text": "每次变更都能回溯到提出它的那句需求"},
                            },
                        ],
                    },
                    {
                        "id": "features.card-review",
                        "type": "Card",
                        "props": {"title": "评审留痕"},
                        "style": {"padding": "16px", "borderRadius": "8px"},
                        "children": [
                            {
                                "id": "features.card-review.name",
                                "type": "Heading",
                                "props": {"text": "评审留痕", "level": 3},
                            },
                            {
                                "id": "features.card-review.desc",
                                "type": "Text",
                                "props": {"text": "结论与理由一起存档，新人也能读懂决策"},
                            },
                        ],
                    },
                    {
                        "id": "features.card-handoff",
                        "type": "Card",
                        "props": {"title": "交付清单"},
                        "style": {"padding": "16px", "borderRadius": "8px"},
                        "children": [
                            {
                                "id": "features.card-handoff.name",
                                "type": "Heading",
                                "props": {"text": "交付清单", "level": 3},
                            },
                            {
                                "id": "features.card-handoff.desc",
                                "type": "Text",
                                "props": {"text": "上线前逐项勾选，漏项直接拦在门外"},
                            },
                        ],
                    },
                ],
            },
        ],
    },
}
