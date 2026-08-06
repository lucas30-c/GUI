"""Generation Provider Protocol 与共享生成契约异常（DD-6 / DD-7）。"""
from __future__ import annotations

from typing import Protocol


class UnrecognizedIntentError(Exception):
    """Provider 无法把 prompt 映射为任何初稿意图时抛出（映射为 422 unrecognized_intent）。"""


class GenerationProvider(Protocol):
    """初稿生成 Provider 抽象。返回值一律视为不可信候选。"""

    async def generate_draft(self, prompt: str) -> dict:
        """根据一句自然语言需求生成候选 DSL 文档（原始 dict，未经任何校验）。"""
        ...
