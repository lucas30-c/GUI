"""Refine API 的 history 契约测试（Spec 009）。

覆盖四类事实：
1. 三态等价（缺省 / null / []）在 API 层的可观察行为完全一致；
2. 结构性校验的每一条 bound 都真的会拒绝（422，复用既有错误码）；
3. 两个上界（条数、序列化字符数）在 Provider 之前生效，且文档零变更；
4. 上界常量只有一个事实来源，前后端不漂移。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genui_api.api import schemas as api_schemas
from genui_api.api.routes import get_provider
from genui_api.api.schemas import (
    MAX_HISTORY_CHARS,
    MAX_HISTORY_TURNS,
    MAX_TURN_PROPS_KEYS,
    RefineRequest,
)
from genui_api.main import create_app
from genui_api.provider import base as provider_base
from genui_api.provider.base import RefinementContext, history_char_size


# ============================================================
# Fixtures & Helpers
# ============================================================


class RecordingProvider:
    """记录调用次数与收到的 context。"""

    def __init__(self):
        self.contexts: list[RefinementContext] = []

    async def generate_patch(self, context: RefinementContext) -> dict:
        self.contexts.append(context)
        return {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": context.selected_node_id,
                    "props": {"text": "新标题"},
                }
            ],
        }


@pytest.fixture
def provider():
    return RecordingProvider()


@pytest.fixture
def client(provider):
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider
    return TestClient(app)


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
                }
            ],
        },
    }


def _turn(text: str = "旧标题", node_id: str = "heading-1") -> dict:
    return {
        "instruction": "把标题改短",
        "selectedNodeId": node_id,
        "nodeType": "Heading",
        "patchProps": {"text": text},
    }


def _post(client: TestClient, body: dict):
    return client.post(
        "/api/v1/dsl/refine",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )


def _payload(history=..., node_id: str = "heading-1") -> dict:
    body = {
        "document": _doc(),
        "selectedNodeId": node_id,
        "instruction": "改标题",
    }
    if history is not ...:
        body["history"] = history
    return body


# ============================================================
# 三态等价（DD-10）
# ============================================================


def test_history_absent_succeeds(client, provider):
    response = _post(client, _payload())
    assert response.status_code == 200
    assert provider.contexts[0].conversation_history == ()


def test_history_null_succeeds(client, provider):
    response = _post(client, _payload(history=None))
    assert response.status_code == 200
    assert provider.contexts[0].conversation_history == ()


def test_history_empty_list_succeeds(client, provider):
    response = _post(client, _payload(history=[]))
    assert response.status_code == 200
    assert provider.contexts[0].conversation_history == ()


def test_three_absent_forms_produce_identical_responses(client):
    bodies = [_payload(), _payload(history=None), _payload(history=[])]
    responses = [_post(client, body) for body in bodies]
    assert {r.status_code for r in responses} == {200}
    first = responses[0].json()
    assert all(r.json() == first for r in responses[1:])


def test_response_schema_unchanged_with_history(client):
    response = _post(client, _payload(history=[_turn()]))
    assert response.status_code == 200
    assert set(response.json().keys()) == {"success", "patch", "document", "integrity"}


# ============================================================
# 正常路径
# ============================================================


def test_history_reaches_provider_as_confirmed_turns(client, provider):
    history = [_turn(text="第一版"), _turn(text="第二版")]
    assert _post(client, _payload(history=history)).status_code == 200

    received = provider.contexts[0].conversation_history
    assert [t.patch_props["text"] for t in received] == ["第一版", "第二版"]
    assert [t.selected_node_type for t in received] == ["Heading", "Heading"]


def test_history_at_turn_limit_accepted(client, provider):
    history = [_turn() for _ in range(MAX_HISTORY_TURNS)]
    assert _post(client, _payload(history=history)).status_code == 200
    assert len(provider.contexts[0].conversation_history) == MAX_HISTORY_TURNS


def test_history_node_not_in_document_is_accepted(client):
    """history 不做语义校验（DD-13）。"""
    assert _post(client, _payload(history=[_turn(node_id="ghost")])).status_code == 200


# ============================================================
# 结构性校验（全部 → 422 invalid_request_structure）
# ============================================================


@pytest.mark.parametrize(
    "history",
    [
        pytest.param([_turn() for _ in range(MAX_HISTORY_TURNS + 1)], id="over_count"),
        pytest.param([{**_turn(), "extra": 1}], id="unknown_key"),
        pytest.param([{k: v for k, v in _turn().items() if k != "nodeType"}], id="missing_key"),
        pytest.param([{**_turn(), "nodeType": "Script"}], id="unregistered_node_type"),
        pytest.param([{**_turn(), "patchProps": {"text": {"nested": 1}}}], id="non_scalar_value"),
        pytest.param([{**_turn(), "patchProps": {"text": [1, 2]}}], id="list_value"),
        pytest.param([{**_turn(), "instruction": ""}], id="empty_instruction"),
        pytest.param([{**_turn(), "instruction": "x" * 1001}], id="over_long_instruction"),
        pytest.param([{**_turn(), "selectedNodeId": ""}], id="empty_node_id"),
        pytest.param(
            [{**_turn(), "patchProps": {f"k{i}": "v" for i in range(MAX_TURN_PROPS_KEYS + 1)}}],
            id="too_many_prop_keys",
        ),
        pytest.param("not-a-list", id="wrong_type"),
        pytest.param([["not-an-object"]], id="turn_not_object"),
    ],
)
def test_invalid_history_rejected_with_422(client, provider, history):
    response = _post(client, _payload(history=history))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request_structure"
    assert provider.contexts == []


def test_prop_keys_at_limit_accepted(client):
    history = [{**_turn(), "patchProps": {f"k{i}": "v" for i in range(MAX_TURN_PROPS_KEYS)}}]
    assert _post(client, _payload(history=history)).status_code == 200


def test_oversize_history_rejected_and_document_unchanged(client, provider):
    """字符上界：Provider 不被调用，且不返回任何 document。"""
    history = [_turn(text="字" * 30_000) for _ in range(2)]
    response = _post(client, _payload(history=history))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request_structure"
    assert "document" not in response.json()
    assert provider.contexts == []


def test_history_at_char_limit_accepted(client):
    """恰好等于字符上限 → 放行（边界包含）。"""
    pad = MAX_HISTORY_CHARS - history_char_size([_turn(text="z")])
    history = [_turn(text="z" * (1 + pad))]
    assert history_char_size(history) == MAX_HISTORY_CHARS
    assert _post(client, _payload(history=history)).status_code == 200


def test_error_response_does_not_echo_history(client):
    """错误响应为固定净化文案，不回显 history 内容（S-7）。"""
    secret = "SECRET-HISTORY-MARKER"
    history = [_turn(text=secret + "字" * 30_000) for _ in range(2)]
    response = _post(client, _payload(history=history))
    assert secret not in response.text


# ============================================================
# 上界常量的单一事实来源（DD-21）
# ============================================================


@pytest.mark.parametrize(
    "name", ["MAX_HISTORY_TURNS", "MAX_HISTORY_CHARS", "MAX_TURN_PROPS_KEYS"]
)
def test_schema_constants_are_the_same_objects_as_provider_base(name):
    assert getattr(api_schemas, name) is getattr(provider_base, name)


def test_schemas_module_imports_rather_than_redefines_limits():
    source = Path(api_schemas.__file__).read_text(encoding="utf-8")
    assert "from genui_api.provider.base import" in source
    assert "50_000" not in source
    assert "50000" not in source


def test_frontend_mirror_matches_backend_constant():
    """前端镜像常量不得漂移（Vitest 无法 import Python，故由后端反向断言）。"""
    app_tsx = Path(__file__).resolve().parents[3] / "frontend" / "src" / "App.tsx"
    source = app_tsx.read_text(encoding="utf-8")

    import re

    turns = re.search(r"MAX_HISTORY_TURNS\s*=\s*(\d+)", source)
    keys = re.search(r"MAX_TURN_PROPS_KEYS\s*=\s*(\d+)", source)
    assert turns is not None and keys is not None
    assert int(turns.group(1)) == MAX_HISTORY_TURNS
    assert int(keys.group(1)) == MAX_TURN_PROPS_KEYS


# ============================================================
# OpenAPI 与请求模型
# ============================================================


def test_openapi_documents_history_field(client):
    schema = client.get("/openapi.json").json()
    request_schema = schema["paths"]["/api/v1/dsl/refine"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert "history" in request_schema["properties"]
    assert "$defs" in request_schema
    assert "RefineHistoryTurn" in request_schema["$defs"]


def test_request_model_accepts_camel_case_history():
    req = RefineRequest.model_validate(_payload(history=[_turn()]))
    assert req.history is not None
    assert req.history[0].selected_node_id == "heading-1"
    assert req.history[0].node_type == "Heading"


def test_request_model_rejects_conversation_id():
    """不引入 conversationId / sessionId 之类的状态字段。"""
    with pytest.raises(Exception):
        RefineRequest.model_validate({**_payload(), "conversationId": "abc"})
