"""Provider Protocol 与 RefinementContext 定义。

本模块是零业务 import 的叶子模块（只依赖标准库），因此也是上下文预算上界常量的
**单一事实来源**（Spec 009 DD-21）：`api/**` 与 `refinement/**` 今天都已 import 它，
把常量与被它们约束的域对象放在一处，既无循环依赖也无第二份可漂移的定义。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

# --- 上下文预算上界（Spec 009 DD-21 / DD-22）---
# 条数上界：单请求携带的已确认轮次数量。
MAX_HISTORY_TURNS = 20
# 规范化序列化字符上界：条数上界无法约束 patchProps string 值的体积，
# 因此对整份 history 的序列化长度另设固定上界（安全 / 资源上界，非 token 计费）。
MAX_HISTORY_CHARS = 50_000
# 单轮 patchProps 的键数上界。
MAX_TURN_PROPS_KEYS = 16
# 单轮 patchStyle 的键数上界（Spec 010 DD-22）：等于 DSL Style 白名单字段数，
# 因为一轮最多能把 11 个受控字段各写一次，再多必然是未知键（已被契约层拒绝）。
MAX_TURN_STYLE_KEYS = 11


def history_char_size(turns: list[dict]) -> int:
    """对已规范化的 5 键 camelCase 字典列表做确定性序列化并返回字符数。

    纯函数：无 I/O、无随机。API 层与 Pipeline 层调用同一函数，
    因此两侧对同一份 history 恒得出同一个数（Spec 009 DD-22）。
    """
    return len(
        json.dumps(turns, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


@dataclass(frozen=True)
class ConfirmedTurn:
    """一个已确认（通过完整校验并已应用）的精修轮次。

    只承载重建历史 message 所需的最小信息：无 role、无模型输出原文、无 props 快照。
    """

    instruction: str
    selected_node_id: str
    selected_node_type: str
    patch_props: dict
    # 该轮已确认的 style 变更（Spec 010 DD-13）。默认空 dict → M4-03 的 4 参构造保持可用。
    patch_style: dict = field(default_factory=dict)

    def as_wire_dict(self) -> dict:
        """转为 5 键 camelCase 字典（与 wire 契约一致），供尺寸计算与序列化使用。"""
        return {
            "instruction": self.instruction,
            "selectedNodeId": self.selected_node_id,
            "nodeType": self.selected_node_type,
            "patchProps": self.patch_props,
            "patchStyle": self.patch_style,
        }


@dataclass
class RefinementContext:
    """传递给 Provider 的受控上下文。"""

    instruction: str
    selected_node_id: str
    selected_node_type: str
    selected_node_props: dict
    document_version: str
    # 已确认对话历史（oldest → newest）。默认空 tuple → M4-02 的 5 参构造保持可用。
    conversation_history: tuple[ConfirmedTurn, ...] = ()
    # 目标节点当前 style（Spec 010 DD-12）：由 Pipeline 从**已校验文档**派生，
    # 不来自模型输出、不来自 history 回灌。默认空 dict → 既有构造保持可用。
    selected_node_style: dict = field(default_factory=dict)


class RefinementProvider(Protocol):
    async def generate_patch(self, context: RefinementContext) -> dict:
        """返回候选 Patch dict（不可信，需校验）。"""
        ...
