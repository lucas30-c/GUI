"""确定性 Mock Generation Provider — 关键词子串匹配到三套内置模板（DD-9 ~ DD-12）。"""
from __future__ import annotations

import copy

from genui_api.generation.base import UnrecognizedIntentError
from genui_api.generation.templates import (
    TEMPLATE_COFFEE_SHOP,
    TEMPLATE_EVENT_SIGNUP,
    TEMPLATE_PRODUCT_INTRO,
)

# 意图映射表：按固定优先级排列（咖啡店 > 活动报名 > 产品介绍），
# 组内任一关键词是归一化 prompt 的子串即命中该组并停止（DD-9）。
INTENT_RULES: tuple[tuple[str, tuple[str, ...], dict], ...] = (
    ("coffee_shop", ("咖啡", "coffee"), TEMPLATE_COFFEE_SHOP),
    (
        "event_signup",
        ("报名", "表单", "活动", "signup", "form", "event"),
        TEMPLATE_EVENT_SIGNUP,
    ),
    (
        "product_intro",
        ("产品", "介绍", "落地页", "product", "landing"),
        TEMPLATE_PRODUCT_INTRO,
    ),
)


class MockGenerationProvider:
    """确定性 Mock：无网络、无随机、无密钥、无状态。"""

    async def generate_draft(self, prompt: str) -> dict:
        normalized = prompt.strip().lower()

        for _intent, keywords, template in INTENT_RULES:
            if any(keyword in normalized for keyword in keywords):
                # 每次返回独立深拷贝，避免模块级常量被跨请求污染（DD-12）
                return copy.deepcopy(template)

        # 无任何关键词命中：显式安全失败，不静默兜底（DD-9）
        raise UnrecognizedIntentError(
            "No built-in draft intent matches the given prompt"
        )
