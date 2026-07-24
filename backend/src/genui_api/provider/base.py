"""Provider Protocol 与 RefinementContext 定义。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RefinementContext:
    """传递给 Provider 的受控上下文。"""

    instruction: str
    selected_node_id: str
    selected_node_type: str
    selected_node_props: dict
    document_version: str


class RefinementProvider(Protocol):
    async def generate_patch(self, context: RefinementContext) -> dict:
        """返回候选 Patch dict（不可信，需校验）。"""
        ...
