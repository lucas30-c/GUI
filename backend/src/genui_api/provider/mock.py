"""确定性 Mock Provider — 按 node type 选择合法文案字段，并支持受控 style 指令。"""
from genui_api.provider.base import RefinementContext


# 节点类型到 props 字段的映射
_NODE_TYPE_FIELD_MAP: dict[str, str] = {
    "Heading": "text",
    "Text": "text",
    "Button": "text",
    "Page": "title",
    "Card": "title",
    "Section": "ariaLabel",
    "Image": "alt",
    "Form": "name",
    "Input": "label",
}

_STYLE_PREFIX = "set_style:"
_TEXT_STYLE_PREFIX = "set_text_style:"
_TEXT_PREFIX = "set_text:"


def _parse_style_spec(spec: str) -> dict:
    """把 `k=v,k=v` 解析为 style 字典；字面量 `null` → None。

    刻意**不**做白名单过滤、值域校验或空白裁剪：Mock 的职责是可预测地把指令映射为
    候选，合法性由 Patch schema 与应用后的 DSL 全量校验判定（Spec 010 S-1）。
    这样 `set_style:boxShadow=evil` 才能真实地走到「被拒绝」那条路径。
    """
    style: dict = {}
    for pair in spec.split(","):
        if not pair:
            continue
        key, sep, value = pair.partition("=")
        if not sep:
            continue
        style[key] = None if value == "null" else value
    return style


class MockProvider:
    """确定性 Mock，无网络、无随机、无密钥。"""

    async def generate_patch(self, context: RefinementContext) -> dict:
        instruction = context.instruction
        target = context.selected_node_id
        field = _NODE_TYPE_FIELD_MAP.get(context.selected_node_type, "text")

        # 混合指令：`set_text_style:<文案>|<k=v,k=v>` → update_props + update_style
        if instruction.startswith(_TEXT_STYLE_PREFIX):
            payload = instruction[len(_TEXT_STYLE_PREFIX) :]
            text, _, style_spec = payload.partition("|")
            return {
                "version": "0.1",
                "operations": [
                    {
                        "op": "update_props",
                        "targetNodeId": target,
                        "props": {field: text},
                    },
                    {
                        "op": "update_style",
                        "targetNodeId": target,
                        "style": _parse_style_spec(style_spec),
                    },
                ],
            }

        # 纯样式指令：`set_style:<k=v,k=v>` → 单条 update_style
        if instruction.startswith(_STYLE_PREFIX):
            return {
                "version": "0.1",
                "operations": [
                    {
                        "op": "update_style",
                        "targetNodeId": target,
                        "style": _parse_style_spec(instruction[len(_STYLE_PREFIX) :]),
                    }
                ],
            }

        # 既有行为（逐字节不变）：`set_text:<文案>` 与裸文本都映射为 update_props
        if instruction.startswith(_TEXT_PREFIX):
            value = instruction[len(_TEXT_PREFIX) :]
        else:
            value = instruction

        return {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": target,
                    "props": {field: value},
                }
            ],
        }
