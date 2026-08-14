"""确定性 Mock Generation Provider（测试替身，仅测试范围使用）。

Real-Provider-only（Owner 决策）：生产链路不再存在 Mock 与「意图无法识别」分支。
本替身只为后端测试提供可预测的候选来源；关键词未命中时不再抛
UnrecognizedIntentError（该概念已从产品移除），而是确定性回退到默认模板。
"""
from __future__ import annotations

import copy

from tests.doubles.templates import (
    TEMPLATE_COFFEE_SHOP,
    TEMPLATE_EVENT_SIGNUP,
    TEMPLATE_PRODUCT_INTRO,
)

# 意图映射表：按固定优先级排列（咖啡店 > 活动报名 > 产品介绍），
# 组内任一关键词是归一化 prompt 的子串即命中该组并停止。
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

# 无关键词命中时的确定性回退模板（不再抛「意图无法识别」）。
_FALLBACK_TEMPLATE = TEMPLATE_PRODUCT_INTRO


class MockGenerationProvider:
    """确定性 Mock：无网络、无随机、无密钥、无状态。"""

    async def generate_draft(self, prompt: str) -> dict:
        normalized = prompt.strip().lower()

        for _intent, keywords, template in INTENT_RULES:
            if any(keyword in normalized for keyword in keywords):
                # 每次返回独立深拷贝，避免模块级常量被跨请求污染
                return copy.deepcopy(template)

        # 无任何关键词命中：确定性回退，而非「意图无法识别」
        return copy.deepcopy(_FALLBACK_TEMPLATE)
