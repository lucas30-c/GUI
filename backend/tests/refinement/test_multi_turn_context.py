"""多轮上下文 Pipeline 行为测试（Spec 009）。

核心口径：history 只是**送给模型的上下文**，不参与 Pipeline 的任何判定。
因此本文件的断言分两类：
1. history 确实被完整、按序、深拷贝地送达 Provider；
2. history 无论是空的、被污染的还是指向别的节点，都不改变 Pipeline 的判定结果。
"""

import asyncio
import copy

import pytest

from genui_api.provider.base import (
    MAX_HISTORY_CHARS,
    MAX_HISTORY_TURNS,
    ConfirmedTurn,
    RefinementContext,
    history_char_size,
)
from genui_api.refinement.pipeline import RefinementError, refine


def _run(coro):
    return asyncio.run(coro)


# ============================================================
# Fixtures & Helpers
# ============================================================


def _doc() -> dict:
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {"title": "Test"},
            "children": [
                {
                    "id": "heading-1",
                    "type": "Heading",
                    "props": {"text": "Hello", "level": 1},
                },
                {
                    "id": "cta",
                    "type": "Button",
                    "props": {"text": "Buy"},
                },
            ],
        },
    }


def _turn(
    instruction: str = "把标题改短",
    node_id: str = "heading-1",
    node_type: str = "Heading",
    props: dict | None = None,
) -> ConfirmedTurn:
    return ConfirmedTurn(
        instruction=instruction,
        selected_node_id=node_id,
        selected_node_type=node_type,
        patch_props=props if props is not None else {"text": "旧标题"},
    )


class CapturingProvider:
    """记录收到的 context，并返回一个合法的最小 Patch。"""

    def __init__(self, target: str = "heading-1"):
        self.contexts: list[RefinementContext] = []
        self._target = target

    async def generate_patch(self, context: RefinementContext) -> dict:
        self.contexts.append(context)
        return {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": self._target,
                    "props": {"text": "新标题"},
                }
            ],
        }


class NeverCalledProvider:
    """一旦被调用即让测试失败（用于证明超限请求不触达模型）。"""

    def __init__(self):
        self.calls = 0

    async def generate_patch(self, context: RefinementContext) -> dict:
        self.calls += 1
        raise AssertionError("Provider must not be invoked")


# ============================================================
# history 送达语义
# ============================================================


def test_history_absent_yields_empty_tuple_context():
    """不传 history → context.conversation_history 为空 tuple（默认态）。"""
    provider = CapturingProvider()
    _run(refine(_doc(), "heading-1", "改标题", provider))
    assert provider.contexts[0].conversation_history == ()


def test_empty_history_argument_equals_absent():
    """显式传空序列与不传等价。"""
    a, b = CapturingProvider(), CapturingProvider()
    _run(refine(_doc(), "heading-1", "改标题", a))
    _run(refine(_doc(), "heading-1", "改标题", b, history=[]))
    assert a.contexts[0].conversation_history == b.contexts[0].conversation_history == ()


def test_history_reaches_provider_in_order():
    """多轮 history 按 oldest → newest 原序送达。"""
    provider = CapturingProvider()
    history = [_turn(instruction=f"第 {i} 轮") for i in range(3)]
    _run(refine(_doc(), "heading-1", "改标题", provider, history=history))

    received = provider.contexts[0].conversation_history
    assert [t.instruction for t in received] == ["第 0 轮", "第 1 轮", "第 2 轮"]


def test_history_is_normalized_to_tuple():
    """入参可以是任意 Sequence，context 上恒为不可变 tuple。"""
    provider = CapturingProvider()
    _run(refine(_doc(), "heading-1", "改标题", provider, history=[_turn()]))
    assert isinstance(provider.contexts[0].conversation_history, tuple)


def test_history_patch_props_deep_copied():
    """Provider 侧修改 patch_props 不影响调用方持有的对象。"""
    provider = CapturingProvider()
    original = {"text": "旧标题"}
    turn = _turn(props=original)
    _run(refine(_doc(), "heading-1", "改标题", provider, history=[turn]))

    received = provider.contexts[0].conversation_history[0]
    received.patch_props["text"] = "被 Provider 改写"
    assert original == {"text": "旧标题"}
    assert turn.patch_props == {"text": "旧标题"}


def test_confirmed_turn_is_frozen():
    """ConfirmedTurn 不可变：Provider 无法替换字段。"""
    turn = _turn()
    with pytest.raises(Exception):
        turn.instruction = "改写"  # type: ignore[misc]


def test_history_argument_not_mutated():
    """refine() 不修改调用方传入的 history 列表本身。"""
    provider = CapturingProvider()
    history = [_turn(instruction="第 1 轮"), _turn(instruction="第 2 轮")]
    before = copy.deepcopy(history)
    _run(refine(_doc(), "heading-1", "改标题", provider, history=history))
    assert history == before


# ============================================================
# history 不参与判定（TB-1）
# ============================================================


def test_history_does_not_change_success_result():
    """带 history 与不带 history 的成功结果逐字段相同。"""
    without = _run(refine(_doc(), "heading-1", "改标题", CapturingProvider()))
    with_history = _run(
        refine(
            _doc(),
            "heading-1",
            "改标题",
            CapturingProvider(),
            history=[_turn(), _turn(node_id="cta", node_type="Button")],
        )
    )
    assert without.document == with_history.document
    assert without.patch == with_history.patch
    assert without.integrity == with_history.integrity


def test_history_node_id_does_not_authorize_target():
    """history 中出现的节点 id 不授予权限：候选指向它仍越界失败。"""
    provider = CapturingProvider(target="cta")  # 越过 selected_node_id
    with pytest.raises(RefinementError) as exc:
        _run(
            refine(
                _doc(),
                "heading-1",
                "改标题",
                provider,
                history=[_turn(node_id="cta", node_type="Button")],
            )
        )
    assert exc.value.code == "candidate_boundary_violation"


def test_history_referencing_missing_node_is_accepted():
    """history 不做语义校验：其节点在文档中不存在也照常成功（DD-13）。"""
    result = _run(
        refine(
            _doc(),
            "heading-1",
            "改标题",
            CapturingProvider(),
            history=[_turn(node_id="ghost-node")],
        )
    )
    assert result.success is True


def test_history_does_not_affect_target_not_found():
    """目标节点不存在时的错误码不因 history 而变。"""
    with pytest.raises(RefinementError) as exc:
        _run(
            refine(
                _doc(),
                "nope",
                "改标题",
                CapturingProvider(),
                history=[_turn()],
            )
        )
    assert exc.value.code == "target_node_not_found"


def test_history_does_not_affect_instruction_validation():
    """空 instruction 仍先被拒；history 不能补足缺失的指令。"""
    provider = NeverCalledProvider()
    with pytest.raises(RefinementError) as exc:
        _run(refine(_doc(), "heading-1", "   ", provider, history=[_turn()]))
    assert exc.value.code == "invalid_instruction"
    assert provider.calls == 0


def test_current_props_come_from_document_not_history():
    """当前 props 恒取自已校验文档，history 中的旧值不参与（CS-4）。"""
    provider = CapturingProvider()
    _run(
        refine(
            _doc(),
            "heading-1",
            "改标题",
            provider,
            history=[_turn(props={"text": "历史里的假值", "level": 6})],
        )
    )
    assert provider.contexts[0].selected_node_props == {"text": "Hello", "level": 1}


# ============================================================
# 两项上界的防御性复核（DD-16 / DD-22）
# ============================================================


def test_turn_count_over_limit_rejected_before_provider():
    """条数超限 → 422 语义错误码，Provider 不被调用。"""
    provider = NeverCalledProvider()
    history = [_turn() for _ in range(MAX_HISTORY_TURNS + 1)]
    with pytest.raises(RefinementError) as exc:
        _run(refine(_doc(), "heading-1", "改标题", provider, history=history))
    assert exc.value.code == "invalid_request_structure"
    assert provider.calls == 0


def test_turn_count_at_limit_accepted():
    """恰好等于上限 → 放行（边界包含）。"""
    provider = CapturingProvider()
    history = [_turn() for _ in range(MAX_HISTORY_TURNS)]
    result = _run(refine(_doc(), "heading-1", "改标题", provider, history=history))
    assert result.success is True
    assert len(provider.contexts[0].conversation_history) == MAX_HISTORY_TURNS


def test_char_size_over_limit_rejected_before_provider():
    """字符上界超限 → 422 语义错误码，Provider 不被调用，文档不变。"""
    provider = NeverCalledProvider()
    doc = _doc()
    before = copy.deepcopy(doc)
    history = [_turn(props={"text": "字" * 30_000}) for _ in range(2)]
    with pytest.raises(RefinementError) as exc:
        _run(refine(doc, "heading-1", "改标题", provider, history=history))
    assert exc.value.code == "invalid_request_structure"
    assert provider.calls == 0
    assert doc == before


def test_char_size_at_limit_accepted():
    """恰好等于字符上限 → 放行（边界包含）。"""
    pad = MAX_HISTORY_CHARS - history_char_size([_turn(props={"text": "z"}).as_wire_dict()])
    history = [_turn(props={"text": "z" * (1 + pad)})]
    assert history_char_size([history[0].as_wire_dict()]) == MAX_HISTORY_CHARS

    result = _run(refine(_doc(), "heading-1", "改标题", CapturingProvider(), history=history))
    assert result.success is True


def test_char_size_helper_is_deterministic():
    """尺寸函数是纯函数：同一输入恒得同一结果，且与键序无关。"""
    turn = _turn().as_wire_dict()
    reordered = {k: turn[k] for k in reversed(list(turn.keys()))}
    assert history_char_size([turn]) == history_char_size([turn])
    assert history_char_size([turn]) == history_char_size([reordered])


def test_non_target_unchanged_across_many_turns():
    """连续多轮精修，每轮都保持非目标零变更（多轮稳定性）。"""
    doc = _doc()
    history: list[ConfirmedTurn] = []
    for i in range(5):
        result = _run(
            refine(doc, "heading-1", f"第 {i} 轮", CapturingProvider(), history=history)
        )
        assert result.integrity["nonTargetNodesUnchanged"] is True
        doc = result.document
        history.append(_turn(instruction=f"第 {i} 轮", props={"text": "新标题"}))

    # 只有目标节点变化：兄弟节点逐字段不变
    children = doc["root"]["children"]
    assert children[0]["props"]["text"] == "新标题"
    assert children[1]["props"]["text"] == "Buy"
