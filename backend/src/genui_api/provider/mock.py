"""确定性 Mock Provider — 按 node type 选择合法文案字段。"""
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


class MockProvider:
    """确定性 Mock，无网络、无随机、无密钥。"""

    async def generate_patch(self, context: RefinementContext) -> dict:
        instruction = context.instruction
        # Value 计算
        if instruction.startswith("set_text:"):
            value = instruction[9:]
        else:
            value = instruction

        # 根据 node type 选择字段
        field = _NODE_TYPE_FIELD_MAP.get(context.selected_node_type, "text")

        return {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": context.selected_node_id,
                    "props": {field: value},
                }
            ],
        }
