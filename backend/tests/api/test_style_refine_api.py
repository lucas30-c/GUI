"""Refine API 的 style 契约测试（Spec 010 第 7 层 / AC-09 / AC-12 / AC-17 / AC-18 /
AC-24 / AC-25 / BC-7）。

覆盖五类事实：
1. 六个 style 场景与混合 ops 在 API 层的正向可观察行为（200 + integrity + 文档）；
2. `patchStyle` 的三态兼容与两个上界（键数、值类型）在 Provider 之前生效；
3. 上界常量只有一个事实来源，且 `history_char_size` 在 API 层与 Pipeline 层同值；
4. OpenAPI 如实暴露 `patchStyle` 与 `update_style`；
5. MockProvider 的新指令可用，且既有 `set_text:` / 裸文本输出逐字节不变。
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genui_api.api import schemas as api_schemas
from genui_api.api.routes import get_provider
from genui_api.api.schemas import (
    MAX_HISTORY_CHARS,
    MAX_HISTORY_TURNS,
    MAX_TURN_STYLE_KEYS,
    RefineRequest,
)
from genui_api.llm.prompts import build_refinement_messages
from genui_api.main import create_app
from genui_api.patch import PatchError, apply_patch
from genui_api.provider import base as provider_base
from genui_api.provider.base import RefinementContext, history_char_size
from tests.doubles.refinement import MockProvider

# ============================================================
# Fixtures & Helpers
# ============================================================


class StubProvider:
    """返回预设 operations 并记录 context 的 Provider。"""

    def __init__(self, operations: list | None = None):
        self.operations = operations
        self.contexts: list[RefinementContext] = []

    async def generate_patch(self, context: RefinementContext) -> dict:
        self.contexts.append(context)
        operations = self.operations
        if operations is None:
            operations = [
                {
                    "op": "update_style",
                    "targetNodeId": context.selected_node_id,
                    "style": {"color": "#c0392b"},
                }
            ]
        return {"version": "0.1", "operations": operations}


def _client(provider) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider
    return TestClient(app)


@pytest.fixture
def provider():
    return StubProvider()


@pytest.fixture
def client(provider):
    return _client(provider)


def _doc() -> dict:
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {"title": "Brew"},
            "children": [
                {
                    "id": "hero.title",
                    "type": "Heading",
                    "props": {"text": "Brew", "level": 1},
                    "style": {"fontSize": "2rem"},
                },
                {"id": "hero.sub", "type": "Text", "props": {"text": "sub"}},
                {
                    "id": "hero.cta",
                    "type": "Button",
                    "props": {"text": "预订", "variant": "primary"},
                    "style": {"borderRadius": "4px"},
                },
            ],
        },
    }


def _turn(**extra) -> dict:
    base = {
        "instruction": "字大一点",
        "selectedNodeId": "hero.title",
        "nodeType": "Heading",
        "patchProps": {},
    }
    base.update(extra)
    return base


def _payload(history=..., instruction: str = "改样式") -> dict:
    body = {
        "document": _doc(),
        "selectedNodeId": "hero.title",
        "instruction": instruction,
    }
    if history is not ...:
        body["history"] = history
    return body


def _post(client: TestClient, body: dict):
    return client.post(
        "/api/v1/dsl/refine",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )


def _node(doc: dict, node_id: str) -> dict:
    return next(c for c in doc["root"]["children"] if c["id"] == node_id)


def _effective(value):
    """递归剥掉 None：响应文档不带 exclude_none（M4-03 既有 dump 行为），
    而 DSL 中 `None` 与「缺失」语义等价，故比较有效值。"""
    if isinstance(value, dict):
        return {k: _effective(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_effective(v) for v in value]
    return value


def _style_of(doc: dict, node_id: str) -> dict:
    """节点的有效 style：`None` 与「缺失」等价，统一归一化为 `{}`。"""
    return _effective(_node(doc, node_id).get("style") or {})


def _style_op(style: dict, target: str = "hero.title") -> dict:
    return {"op": "update_style", "targetNodeId": target, "style": style}


# ============================================================
# A. 六个 style 场景 + 混合 ops（AC-17 / AC-18）
# ============================================================


_SCENARIOS = [
    pytest.param({"color": "#c0392b", "backgroundColor": "white"}, id="A_color"),
    pytest.param({"fontSize": "3rem"}, id="B_font_size"),
    pytest.param({"padding": "16px", "margin": "8px", "gap": "4px"}, id="C_spacing"),
    pytest.param({"borderRadius": "8px"}, id="D_radius"),
    pytest.param({"fontWeight": "bold", "textAlign": "center"}, id="E_weight_align"),
    pytest.param({"width": "100%", "height": "48px"}, id="F_size"),
]


@pytest.mark.parametrize("style", _SCENARIOS)
def test_style_scenario_succeeds_and_leaves_non_target_untouched(style: dict):
    body = _payload()
    response = _post(_client(StubProvider([_style_op(style)])), body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["integrity"] == {
        "selectedNodeId": "hero.title",
        "nonTargetNodesUnchanged": True,
    }

    target = _node(payload["document"], "hero.title")
    assert _style_of(payload["document"], "hero.title") == {"fontSize": "2rem", **style}
    assert target["props"] == {"text": "Brew", "level": 1}

    for node_id in ("hero.sub", "hero.cta"):
        assert _effective(_node(payload["document"], node_id)) == _effective(
            _node(body["document"], node_id)
        )
    assert payload["document"]["root"]["props"] == body["document"]["root"]["props"]


def test_mixed_operations_apply_both_dimensions():
    operations = [
        {"op": "update_props", "targetNodeId": "hero.title", "props": {"text": "Brew Co."}},
        _style_op({"color": "#c0392b"}),
    ]
    response = _post(_client(StubProvider(operations)), _payload())
    assert response.status_code == 200
    payload = response.json()
    assert _node(payload["document"], "hero.title")["props"]["text"] == "Brew Co."
    assert _style_of(payload["document"], "hero.title") == {
        "fontSize": "2rem",
        "color": "#c0392b",
    }
    assert payload["patch"] == {"version": "0.1", "operations": operations}
    assert payload["integrity"]["nonTargetNodesUnchanged"] is True


def test_response_envelope_unchanged_for_style_round(client):
    response = _post(client, _payload())
    assert response.status_code == 200
    assert set(response.json()) == {"success", "patch", "document", "integrity"}


# ============================================================
# B. patchStyle 三态兼容（AC-09 / BC-7）
# ============================================================


@pytest.mark.parametrize(
    "history,label",
    [
        (..., "omitted history"),
        ([_turn()], "turn without patchStyle"),
        ([_turn(patchStyle={})], "explicit empty patchStyle"),
        ([_turn(patchStyle={"fontSize": "2rem"})], "non-empty patchStyle"),
    ],
)
def test_patch_style_three_states_are_accepted(history, label: str):
    provider = StubProvider()
    response = _post(_client(provider), _payload(history=history))
    assert response.status_code == 200, (label, response.text[:200])
    assert response.json()["integrity"]["nonTargetNodesUnchanged"] is True


def test_absent_and_empty_patch_style_produce_byte_identical_messages():
    """AC-09：M4-03 形态（缺 patchStyle）与显式 `{}` 归一化为同一份 messages。"""
    captured = []
    for history in ([_turn()], [_turn(patchStyle={})]):
        provider = StubProvider()
        assert _post(_client(provider), _payload(history=history)).status_code == 200
        captured.append(build_refinement_messages(provider.contexts[0]))
    assert captured[0] == captured[1]
    assert captured[0][2]["role"] == "assistant"
    # 退化分支：无 props、无 style 的轮次重建为空 props 的 update_props（DD-16）
    assert json.loads(captured[0][2]["content"]) == {
        "version": "0.1",
        "operations": [
            {"op": "update_props", "targetNodeId": "hero.title", "props": {}}
        ],
    }


def test_patch_style_reaches_provider_as_domain_turn():
    provider = StubProvider()
    history = [_turn(patchStyle={"color": "#c0392b", "fontSize": None})]
    assert _post(_client(provider), _payload(history=history)).status_code == 200
    turn = provider.contexts[0].conversation_history[0]
    assert turn.patch_style == {"color": "#c0392b", "fontSize": None}
    assert turn.patch_props == {}


# ============================================================
# C. 轮级上界与值域（AC-12）
# ============================================================


@pytest.mark.parametrize(
    "patch_style,label",
    [
        ({f"k{i}": "1px" for i in range(MAX_TURN_STYLE_KEYS + 1)}, "12 keys"),
        ({"fontSize": 16}, "int value"),
        ({"fontSize": 1.5}, "float value"),
        ({"fontSize": True}, "bool value"),
        ({"fontSize": {"a": "1"}}, "object value"),
        ({"fontSize": ["1px"]}, "array value"),
    ],
)
def test_invalid_patch_style_rejected_before_provider(patch_style: dict, label: str):
    provider = StubProvider()
    body = _payload(history=[_turn(patchStyle=patch_style)])
    before = json.loads(json.dumps(body["document"]))
    response = _post(_client(provider), body)
    assert response.status_code == 422, (label, response.text[:200])
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request_structure"
    assert "document" not in payload and "patch" not in payload
    assert provider.contexts == []
    assert body["document"] == before


def test_max_style_keys_is_accepted():
    style = {f"k{i}": "1px" for i in range(MAX_TURN_STYLE_KEYS)}
    provider = StubProvider()
    response = _post(_client(provider), _payload(history=[_turn(patchStyle=style)]))
    assert response.status_code == 200
    assert len(provider.contexts[0].conversation_history[0].patch_style) == 31


def test_unknown_turn_field_still_forbidden():
    """extra="forbid" 不变：patchStyle 的加入没有放宽 turn 的键集。"""
    response = _post(
        _client(StubProvider()), _payload(history=[_turn(patchStyles={"color": "#000000"})])
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request_structure"


def test_twenty_turns_with_eleven_style_keys_still_accepted():
    """AC-24：预算变更是非破坏性的 —— 满额 history 仍 200。"""
    style = {f"k{i}": "1px" for i in range(MAX_TURN_STYLE_KEYS)}
    history = [_turn(patchStyle=style) for _ in range(MAX_HISTORY_TURNS)]
    provider = StubProvider()
    response = _post(_client(provider), _payload(history=history))
    assert response.status_code == 200
    assert len(provider.contexts[0].conversation_history) == MAX_HISTORY_TURNS


# ============================================================
# D. 常量单一事实来源与尺寸计算一致（AC-12 / AC-24）
# ============================================================


def test_max_turn_style_keys_value_and_identity():
    assert MAX_TURN_STYLE_KEYS == 31
    assert api_schemas.MAX_TURN_STYLE_KEYS is provider_base.MAX_TURN_STYLE_KEYS


def test_existing_budget_constants_unchanged():
    assert MAX_HISTORY_TURNS == 20
    assert MAX_HISTORY_CHARS == 50_000


def test_history_char_size_parity_between_api_and_pipeline_layers():
    """同一份逻辑 history 在两层得到同一个数（两侧都输出 5 键）。"""
    wire_history = [
        _turn(patchProps={"text": "A"}, patchStyle={"color": "#c0392b"}),
        _turn(patchProps={}, patchStyle={"fontSize": "2rem"}),
    ]
    req = RefineRequest.model_validate(_payload(history=wire_history))
    api_side = history_char_size([t.model_dump(by_alias=True) for t in req.history])

    provider = StubProvider()
    assert _post(_client(provider), _payload(history=wire_history)).status_code == 200
    pipeline_side = history_char_size(
        [t.as_wire_dict() for t in provider.contexts[0].conversation_history]
    )
    assert api_side == pipeline_side


def test_frontend_mirror_matches_max_turn_style_keys():
    """前端镜像常量不得漂移（Vitest 无法 import Python，故由后端反向断言）。"""
    app_tsx = Path(__file__).resolve().parents[3] / "frontend" / "src" / "App.tsx"
    source = app_tsx.read_text(encoding="utf-8")
    match = re.search(r"MAX_TURN_STYLE_KEYS\s*=\s*(\d+)", source)
    if match is None:
        pytest.skip("前端镜像常量由 Spec 010 P-6 落地；此处待 P-6 后自动生效")
    assert int(match.group(1)) == MAX_TURN_STYLE_KEYS


# ============================================================
# E. OpenAPI 暴露面（AC-12 / AC-17）
# ============================================================


def test_openapi_documents_patch_style(client):
    schema = client.get("/openapi.json").json()
    request_schema = schema["paths"]["/api/v1/dsl/refine"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    turn_schema = request_schema["$defs"]["RefineHistoryTurn"]
    assert "patchStyle" in turn_schema["properties"]
    assert "patchStyle" not in turn_schema.get("required", [])


def test_openapi_patch_document_declares_update_style(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert "UpdateStyleOperation" in schemas
    assert "update_style" in json.dumps(schemas["PatchDocument"]) or "update_style" in json.dumps(
        schemas["UpdateStyleOperation"]
    )
    assert schemas["PatchDocument"]["properties"]["version"]["const"] == "0.1"


# ============================================================
# F. 候选侧失败与 null 语义（AC-25）
# ============================================================


def test_empty_style_candidate_rejected_with_document_unchanged():
    body = _payload()
    before = json.loads(json.dumps(body["document"]))
    response = _post(_client(StubProvider([_style_op({})])), body)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_candidate_structure"
    assert "document" not in response.json()
    assert body["document"] == before


def test_empty_style_maps_to_empty_style_issue_code_at_patch_layer():
    """顶层错误码不新增（invalid_patch_structure），明细层给出 empty_style（DD-28）。"""
    with pytest.raises(PatchError) as exc_info:
        apply_patch(_doc(), {"version": "0.1", "operations": [_style_op({})]})
    assert exc_info.value.code == "invalid_patch_structure"
    assert "empty_style" in [issue.code for issue in exc_info.value.issues]


def test_null_style_value_removes_key_end_to_end():
    response = _post(
        _client(StubProvider([_style_op({"fontSize": None})])), _payload()
    )
    assert response.status_code == 200
    assert _style_of(response.json()["document"], "hero.title") == {}


def test_out_of_boundary_style_op_rejected_with_document_unchanged():
    body = _payload()
    before = json.loads(json.dumps(body["document"]))
    response = _post(
        _client(StubProvider([_style_op({"color": "#000000"}, target="hero.sub")])), body
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "candidate_boundary_violation"
    assert body["document"] == before


# ============================================================
# G. MockProvider 指令（BC-7 / AP-7）
# ============================================================


def test_mock_set_style_directive_applies_style():
    response = _post(
        _client(MockProvider()),
        _payload(instruction="set_style:color=#c0392b,fontSize=3rem"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert [op["op"] for op in payload["patch"]["operations"]] == ["update_style"]
    assert _style_of(payload["document"], "hero.title") == {
        "color": "#c0392b",
        "fontSize": "3rem",
    }


def test_mock_set_text_style_directive_emits_two_operations():
    response = _post(
        _client(MockProvider()),
        _payload(instruction="set_text_style:立即预订|fontWeight=bold"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert [op["op"] for op in payload["patch"]["operations"]] == [
        "update_props",
        "update_style",
    ]
    assert _node(payload["document"], "hero.title")["props"]["text"] == "立即预订"
    assert _style_of(payload["document"], "hero.title") == {
        "fontSize": "2rem",
        "fontWeight": "bold",
    }


def test_mock_set_style_null_clears_existing_key():
    response = _post(
        _client(MockProvider()), _payload(instruction="set_style:fontSize=null")
    )
    assert response.status_code == 200
    assert _style_of(response.json()["document"], "hero.title") == {}


@pytest.mark.parametrize(
    "instruction,expected",
    [
        ("set_text:新标题", "新标题"),
        ("裸文本指令", "裸文本指令"),
    ],
)
def test_mock_legacy_directives_are_byte_identical(instruction: str, expected: str):
    """BC-7：既有指令的候选输出与 M4-03 逐字节相同。"""
    response = _post(_client(MockProvider()), _payload(instruction=instruction))
    assert response.status_code == 200
    assert response.json()["patch"] == {
        "version": "0.1",
        "operations": [
            {
                "op": "update_props",
                "targetNodeId": "hero.title",
                "props": {"text": expected},
            }
        ],
    }


def test_mock_unknown_style_key_is_rejected_by_contract():
    """Mock 不做白名单过滤 —— 由契约层拒绝，证明 hard gate 在校验器而非 Mock。"""
    body = _payload(instruction="set_style:boxShadow=1px 1px")
    before = json.loads(json.dumps(body["document"]))
    response = _post(_client(MockProvider()), body)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_candidate_structure"
    assert body["document"] == before
