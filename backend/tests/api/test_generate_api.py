"""Generate API 端点集成测试 — 正向/反向、Content-Type、脱敏、OpenAPI、Provider 注入"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genui_api.api.routes import get_generation_provider
from genui_api.api.schemas import GenerateRequest
from genui_api.generation.base import UnrecognizedIntentError
from genui_api.generation.mock import MockGenerationProvider
from genui_api.generation.pipeline import MAX_PROMPT_LENGTH
from genui_api.main import create_app


# ============================================================
# Fixtures & Helpers
# ============================================================


@pytest.fixture
def client():
    return TestClient(create_app())


def _post_generate(client: TestClient, payload, content_type="application/json"):
    if isinstance(payload, (dict, list)):
        body = json.dumps(payload)
    else:
        body = payload
    return client.post(
        "/api/v1/dsl/generate",
        content=body,
        headers={"Content-Type": content_type},
    )


def _find(node: dict, node_id: str) -> dict | None:
    if node.get("id") == node_id:
        return node
    for child in node.get("children", []):
        found = _find(child, node_id)
        if found is not None:
            return found
    return None


@pytest.fixture
def gold_case_json():
    path = (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "dsl"
        / "coffee-shop-landing.json"
    )
    return json.loads(path.read_text())


# ============================================================
# 恶意 / 异常 Provider
# ============================================================


class NonDictProvider:
    async def generate_draft(self, prompt: str):
        return "not-a-document"


class NoneProvider:
    async def generate_draft(self, prompt: str):
        return None


SECRET_TEXT = "泄露标记 LEAKED_DOCUMENT_CONTENT"


class DuplicateIdProvider:
    async def generate_draft(self, prompt: str) -> dict:
        return {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {"title": SECRET_TEXT},
                "children": [
                    {"id": "dup", "type": "Text", "props": {"text": SECRET_TEXT}},
                    {"id": "dup", "type": "Text", "props": {"text": SECRET_TEXT}},
                ],
            },
        }


class IllegalNestingProvider:
    async def generate_draft(self, prompt: str) -> dict:
        return {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {},
                "children": [
                    {
                        "id": "loose-input",
                        "type": "Input",
                        "props": {"name": "n", "label": SECRET_TEXT},
                    }
                ],
            },
        }


class CrashingProvider:
    async def generate_draft(self, prompt: str) -> dict:
        raise RuntimeError(
            f"Traceback boom /Users/secret/path.py api_key=<API_KEY> {SECRET_TEXT}"
        )


class AlwaysUnrecognizedProvider:
    async def generate_draft(self, prompt: str) -> dict:
        raise UnrecognizedIntentError("nope")


class EchoPromptProvider:
    """把 prompt 原文塞进候选文档的非法字段，用于验证响应不回显 prompt。"""

    async def generate_draft(self, prompt: str) -> dict:
        return {"version": "0.1", "root": {"id": "page", "type": "Page"}, "leak": prompt}


# ============================================================
# A. 三类意图成功路径
# ============================================================


def test_coffee_prompt_returns_coffee_draft(client):
    resp = _post_generate(client, {"prompt": "我要一个咖啡店的落地页"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    document = body["document"]
    assert document["version"] == "0.1"
    assert document["root"]["type"] == "Page"
    assert document["root"]["id"] == "page"
    title = _find(document["root"], "hero.title")
    subtitle = _find(document["root"], "hero.subtitle")
    assert title is not None and title["type"] == "Heading"
    assert subtitle is not None and subtitle["type"] == "Text"


def test_event_prompt_returns_signup_draft(client):
    resp = _post_generate(client, {"prompt": "帮我做一个活动报名页"})
    assert resp.status_code == 200
    document = resp.json()["document"]
    form = _find(document["root"], "signup.form")
    assert form is not None and form["type"] == "Form"
    assert _find(document["root"], "signup.form.name") is not None
    assert _find(document["root"], "signup.form.email") is not None
    assert _find(document["root"], "signup.form.submit") is not None


def test_product_prompt_returns_product_draft(client):
    resp = _post_generate(client, {"prompt": "我要一个产品介绍页"})
    assert resp.status_code == 200
    document = resp.json()["document"]
    assert _find(document["root"], "hero.tagline") is not None
    features = _find(document["root"], "features")
    assert features is not None
    cards = [c for c in features["children"] if c["type"] == "Card"]
    assert len(cards) >= 2


def test_success_envelope_has_no_patch_or_integrity(client):
    body = _post_generate(client, {"prompt": "咖啡店"}).json()
    assert set(body.keys()) == {"success", "document"}


def test_generated_coffee_title_differs_from_gold_case(client, gold_case_json):
    document = _post_generate(client, {"prompt": "咖啡店"}).json()["document"]
    generated = _find(document["root"], "hero.title")
    gold = _find(gold_case_json["root"], "hero.title")
    assert generated is not None and gold is not None
    assert generated["props"]["text"] != gold["props"]["text"]


def test_repeated_requests_return_identical_documents(client):
    first = _post_generate(client, {"prompt": "咖啡店"}).json()["document"]
    second = _post_generate(client, {"prompt": "咖啡店"}).json()["document"]
    assert first == second


def test_generated_document_can_be_revalidated_by_validate_endpoint(client):
    document = _post_generate(client, {"prompt": "活动报名"}).json()["document"]
    resp = client.post(
        "/api/v1/dsl/validate",
        content=json.dumps(document),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


# ============================================================
# B. 请求层错误：415 / 400 / 422
# ============================================================


def test_non_json_content_type_returns_415(client):
    resp = _post_generate(client, {"prompt": "咖啡店"}, content_type="text/plain")
    assert resp.status_code == 415
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "unsupported_media_type"


def test_json_content_type_with_charset_is_accepted(client):
    resp = _post_generate(
        client, {"prompt": "咖啡店"}, content_type="application/json; charset=utf-8"
    )
    assert resp.status_code == 200


def test_empty_body_returns_400(client):
    resp = _post_generate(client, "")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_json"


def test_malformed_json_returns_400(client):
    resp = _post_generate(client, "{prompt: ")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_json"


def test_missing_prompt_returns_422_structure_error(client):
    resp = _post_generate(client, {})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request_structure"


def test_non_string_prompt_returns_422_structure_error(client):
    resp = _post_generate(client, {"prompt": 123})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request_structure"


def test_unknown_field_returns_422_structure_error(client):
    resp = _post_generate(client, {"prompt": "咖啡店", "temperature": 0.7})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request_structure"


def test_top_level_array_returns_422_structure_error(client):
    resp = _post_generate(client, [{"prompt": "咖啡店"}])
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request_structure"


@pytest.mark.parametrize("prompt", ["", "   ", "\n\t"])
def test_blank_prompt_returns_422_invalid_prompt(client, prompt):
    resp = _post_generate(client, {"prompt": prompt})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_prompt"


def test_overlong_prompt_returns_422_invalid_prompt(client):
    resp = _post_generate(client, {"prompt": "咖啡" * 300})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_prompt"


def test_prompt_at_exact_limit_is_accepted(client):
    prompt = "咖啡" + "a" * (MAX_PROMPT_LENGTH - 2)
    assert len(prompt) == MAX_PROMPT_LENGTH
    resp = _post_generate(client, {"prompt": prompt})
    assert resp.status_code == 200


def test_unrecognized_prompt_returns_422_unrecognized_intent(client):
    resp = _post_generate(client, {"prompt": "随便来点什么"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "unrecognized_intent"
    assert "document" not in body


# ============================================================
# C. 恶意 / 崩溃 Provider 注入
# ============================================================


def test_non_dict_candidate_returns_502(client):
    app = create_app(generation_provider=NonDictProvider())
    resp = _post_generate(TestClient(app), {"prompt": "咖啡店"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "invalid_generated_document"


def test_none_candidate_returns_502(client):
    app = create_app(generation_provider=NoneProvider())
    resp = _post_generate(TestClient(app), {"prompt": "咖啡店"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "invalid_generated_document"


def test_duplicate_id_candidate_returns_502_without_document_content():
    app = create_app(generation_provider=DuplicateIdProvider())
    resp = _post_generate(TestClient(app), {"prompt": "咖啡店"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == "invalid_generated_document"
    assert SECRET_TEXT not in resp.text
    assert "document" not in body
    codes = {issue["code"] for issue in body["error"]["issues"]}
    assert "duplicate_id" in codes


def test_illegal_nesting_candidate_returns_502_without_document_content():
    app = create_app(generation_provider=IllegalNestingProvider())
    resp = _post_generate(TestClient(app), {"prompt": "咖啡店"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == "invalid_generated_document"
    assert SECRET_TEXT not in resp.text
    codes = {issue["code"] for issue in body["error"]["issues"]}
    assert "invalid_nesting" in codes


def test_crashing_provider_returns_502_provider_error_sanitized():
    app = create_app(generation_provider=CrashingProvider())
    resp = _post_generate(TestClient(app), {"prompt": "咖啡店"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == "provider_error"
    for leak in ("Traceback", "/Users/secret/path.py", "api_key", SECRET_TEXT):
        assert leak not in resp.text


def test_injected_unrecognized_provider_returns_422():
    app = create_app(generation_provider=AlwaysUnrecognizedProvider())
    resp = _post_generate(TestClient(app), {"prompt": "咖啡店落地页"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "unrecognized_intent"


def test_error_response_never_echoes_prompt_text():
    app = create_app(generation_provider=EchoPromptProvider())
    marker = "咖啡店 PROMPT_ECHO_MARKER"
    resp = _post_generate(TestClient(app), {"prompt": marker})
    assert resp.status_code == 502
    assert "PROMPT_ECHO_MARKER" not in resp.text


def test_error_responses_have_no_traceback_or_env_leak(client):
    for payload in ({"prompt": ""}, {"prompt": "随便来点什么"}, {}):
        resp = _post_generate(client, payload)
        text = resp.text
        for leak in ("Traceback", "site-packages", "genui_api/", "PYTHONPATH", ".venv"):
            assert leak not in text


def test_dependency_override_is_used_for_generation_provider():
    app = create_app(generation_provider=NonDictProvider())
    assert get_generation_provider in app.dependency_overrides
    override = app.dependency_overrides[get_generation_provider]
    assert isinstance(override(), NonDictProvider)


def test_default_provider_is_mock_generation_provider():
    assert isinstance(get_generation_provider(), MockGenerationProvider)


# ============================================================
# D. 契约与 OpenAPI
# ============================================================


def test_openapi_contains_generate_endpoint(client):
    schema = client.app.openapi()
    assert "/api/v1/dsl/generate" in schema["paths"]
    operation = schema["paths"]["/api/v1/dsl/generate"]["post"]
    assert operation["requestBody"]["required"] is True
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert "prompt" in json.dumps(request_schema)
    for status in ("400", "415", "422", "500", "502"):
        assert status in operation["responses"]


def test_generate_request_model_forbids_extra_fields():
    assert GenerateRequest.model_config.get("extra") == "forbid"
    assert set(GenerateRequest.model_fields) == {"prompt"}


def test_get_method_is_not_allowed(client):
    assert client.get("/api/v1/dsl/generate").status_code == 405


# ============================================================
# E. 既有端点无回归
# ============================================================


def test_refine_endpoint_still_works_after_generate_added(client):
    document = _post_generate(client, {"prompt": "咖啡店"}).json()["document"]
    resp = client.post(
        "/api/v1/dsl/refine",
        content=json.dumps(
            {
                "document": document,
                "selectedNodeId": "hero.title",
                "instruction": "set_text:精修后的标题",
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["integrity"]["nonTargetNodesUnchanged"] is True
    refined = _find(body["document"]["root"], "hero.title")
    assert refined is not None
    assert refined["props"]["text"] == "精修后的标题"


def test_health_endpoint_still_works(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_generate_and_refine_providers_are_independent():
    """只注入生成侧恶意 Provider 时，精修端点行为不受影响。"""
    app = create_app(generation_provider=NonDictProvider())
    client = TestClient(app)
    document = {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {"title": "T"},
            "children": [
                {"id": "heading-1", "type": "Heading", "props": {"text": "H", "level": 1}}
            ],
        },
    }
    resp = client.post(
        "/api/v1/dsl/refine",
        content=json.dumps(
            {
                "document": document,
                "selectedNodeId": "heading-1",
                "instruction": "set_text:仍然可用",
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
