"""Generation Provider Protocol（DD-6 / DD-7）。

Real-Provider-only：生产链路不存在「意图无法识别」分支——真实模型不做模板
意图分类，模型失败就是 provider_error，由 Pipeline fail-closed 后映射为
用户可读的分层错误。Mock / 模板匹配仅作为测试替身存在于测试范围内。
"""
from __future__ import annotations

from typing import Protocol


class GenerationProvider(Protocol):
    """初稿生成 Provider 抽象。返回值一律视为不可信候选。"""

    async def generate_draft(self, prompt: str) -> dict:
        """根据一句自然语言需求生成候选 DSL 文档（原始 dict，未经任何校验）。

        首次生成与 repair 重生成共用本方法：repair 上下文由 Pipeline 构造为
        机器可读的 user message（见 generation.pipeline.build_repair_user_prompt）。
        """
        ...
