"""MockProvider 单元测试 — 确定性规则、节点类型映射、Protocol 兼容性"""

import asyncio

import pytest

from genui_api.provider.base import RefinementContext, RefinementProvider
from genui_api.provider.mock import MockProvider


def _run(coro):
    return asyncio.run(coro)


def _make_context(
    instruction: str = "hello",
    node_id: str = "node-1",
    node_type: str = "Text",
    props: dict | None = None,
) -> RefinementContext:
    return RefinementContext(
        instruction=instruction,
        selected_node_id=node_id,
        selected_node_type=node_type,
        selected_node_props=props or {"text": "original"},
        document_version="0.1",
    )


class TestMockProviderProtocol:
    """AC-05, AC-06: MockProvider 满足 RefinementProvider Protocol"""

    def test_mock_provider_satisfies_protocol(self):
        """MockProvider 满足 RefinementProvider Protocol（结构化子类型）"""
        provider = MockProvider()
        # Protocol 兼容性：isinstance 不适用于 Protocol（除非 runtime_checkable）
        # 但我们验证方法签名存在
        assert hasattr(provider, "generate_patch")
        assert callable(provider.generate_patch)

    def test_mock_provider_is_runtime_compatible(self):
        """MockProvider 可以赋值给 RefinementProvider 类型注解"""
        provider: RefinementProvider = MockProvider()
        assert provider is not None


class TestMockProviderDeterminism:
    """AC-07: 确定性 — 相同输入始终相同输出"""

    def test_deterministic_same_input_same_output(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="测试文案", node_type="Text")
            result1 = await provider.generate_patch(ctx)
            result2 = await provider.generate_patch(ctx)
            assert result1 == result2
        _run(_test())

    def test_deterministic_multiple_calls(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="abc", node_type="Button")
            results = [await provider.generate_patch(ctx) for _ in range(5)]
            assert all(r == results[0] for r in results)
        _run(_test())


class TestMockProviderSetTextPrefix:
    """AC-08: set_text: 前缀处理"""

    def test_set_text_prefix_extracts_value(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="set_text:新文案", node_type="Text")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["text"] == "新文案"
        _run(_test())

    def test_set_text_prefix_empty_value(self):
        """set_text: 前缀后为空字符串"""
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="set_text:", node_type="Text")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["text"] == ""
        _run(_test())

    def test_no_prefix_uses_full_instruction(self):
        """AC-10: 无前缀时使用完整 instruction 作为 value"""
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="完整指令文本", node_type="Text")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["text"] == "完整指令文本"
        _run(_test())


class TestMockProviderNodeTypeMapping:
    """AC-09: 9 种节点类型的字段映射"""

    def test_heading_maps_to_text(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="标题", node_type="Heading")
            result = await provider.generate_patch(ctx)
            assert "text" in result["operations"][0]["props"]
            assert result["operations"][0]["props"]["text"] == "标题"
        _run(_test())

    def test_text_maps_to_text(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="内容", node_type="Text")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["text"] == "内容"
        _run(_test())

    def test_button_maps_to_text(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="点击", node_type="Button")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["text"] == "点击"
        _run(_test())

    def test_page_maps_to_title(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="页面标题", node_type="Page")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["title"] == "页面标题"
        _run(_test())

    def test_card_maps_to_title(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="卡片标题", node_type="Card")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["title"] == "卡片标题"
        _run(_test())

    def test_section_maps_to_aria_label(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="区域标签", node_type="Section")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["ariaLabel"] == "区域标签"
        _run(_test())

    def test_image_maps_to_alt(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="图片描述", node_type="Image")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["alt"] == "图片描述"
        _run(_test())

    def test_form_maps_to_name(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="表单名", node_type="Form")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["name"] == "表单名"
        _run(_test())

    def test_input_maps_to_label(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(instruction="输入标签", node_type="Input")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["props"]["label"] == "输入标签"
        _run(_test())


class TestMockProviderPatchStructure:
    """验证 MockProvider 返回的 Patch 结构合法"""

    def test_patch_has_correct_version(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context()
            result = await provider.generate_patch(ctx)
            assert result["version"] == "0.1"
        _run(_test())

    def test_patch_has_single_operation(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context()
            result = await provider.generate_patch(ctx)
            assert len(result["operations"]) == 1
        _run(_test())

    def test_patch_operation_uses_correct_target(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context(node_id="target-node")
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["targetNodeId"] == "target-node"
        _run(_test())

    def test_patch_operation_op_is_update_props(self):
        async def _test():
            provider = MockProvider()
            ctx = _make_context()
            result = await provider.generate_patch(ctx)
            assert result["operations"][0]["op"] == "update_props"
        _run(_test())

    def test_unknown_node_type_defaults_to_text(self):
        """未知节点类型默认使用 text 字段"""
        async def _test():
            provider = MockProvider()
            ctx = _make_context(node_type="UnknownType")
            result = await provider.generate_patch(ctx)
            assert "text" in result["operations"][0]["props"]
        _run(_test())
