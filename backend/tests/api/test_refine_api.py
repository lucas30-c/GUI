"""Refine API 端点集成测试 — 正向/反向、Content-Type、脱敏、OpenAPI、Provider 注入"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genui_api.api.routes import get_provider
from genui_api.api.schemas import RefineRequest
from genui_api.main import create_app
from genui_api.provider.base import RefinementContext
from genui_api.provider.mock import MockProvider


# ============================================================
# Fixtures & Helpers
# ============================================================


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def _minimal_valid_dsl() -> dict:
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


def _refine_request(
    doc: dict | None = None,
    node_id: str = "heading-1",
    instruction: str = "新标题",
) -> dict:
    return {
        "document": doc or _minimal_valid_dsl(),
        "selectedNodeId": node_id,
        "instruction": instruction,
    }


def _post_refine(client: TestClient, payload, content_type="application/json"):
    if isinstance(payload, (dict, list)):
        body = json.dumps(payload)
    else:
        body = payload
    return client.post(
        "/api/v1/dsl/refine",
        content=body,
        headers={"Content-Type": content_type},
    )


@pytest.fixture
def gold_case_json():
    path = Path(__file__).resolve().parents[3] / "examples" / "dsl" / "coffee-shop-landing.json"
    return json.loads(path.read_text())


# ============================================================
# Test Providers for negative cases
# ============================================================


class BrokenStructureProvider:
    async def generate_patch(self, context: RefinementContext) -> dict:
        return {"bad": "data"}


class WrongTargetProvider:
    async def generate_patch(self, context: RefinementContext) -> dict:
        return {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": "wrong-node-id",
                    "props": {"text": "hacked"},
                }
            ],
        }


class MultiTargetProvider:
    async def generate_patch(self, context: RefinementContext) -> dict:
        return {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": context.selected_node_id,
                    "props": {"text": "ok"},
                },
                {
                    "op": "update_props",
                    "targetNodeId": "other-node",
                    "props": {"text": "bad"},
                },
            ],
        }


class InvalidResultProvider:
    async def generate_patch(self, context: RefinementContext) -> dict:
        return {
            "version": "0.1",
            "operations": [
                {
                    "op": "update_props",
                    "targetNodeId": context.selected_node_id,
                    "props": {"level": 99},
                }
            ],
        }


class ExceptionProvider:
    async def generate_patch(self, context: RefinementContext) -> dict:
        raise RuntimeError("Provider crashed with secret info /path/to/file")


def _make_client_with_provider(provider) -> TestClient:
    app = create_app(refinement_provider=provider)
    return TestClient(app)


# ============================================================
# API 正向测试
# ============================================================


class TestRefineApiPositive:
    """AC-31~AC-35: API 正向"""

    def test_endpoint_exists(self, client: TestClient):
        """AC-31: POST /api/v1/dsl/refine 端点存在"""
        response = _post_refine(client, _refine_request())
        assert response.status_code != 404

    def test_success_response(self, client: TestClient):
        """AC-32: 合法请求返回 200"""
        response = _post_refine(client, _refine_request())
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "patch" in data
        assert "document" in data
        assert "integrity" in data

    def test_response_document_valid(self, client: TestClient):
        """AC-33: 响应中 document 通过校验"""
        response = _post_refine(client, _refine_request())
        data = response.json()
        from genui_api.contracts.validation import validate_dsl_document
        doc = validate_dsl_document(data["document"])
        assert doc is not None

    def test_response_patch_valid(self, client: TestClient):
        """AC-34: 响应中 patch 通过 PatchDocument 校验"""
        response = _post_refine(client, _refine_request())
        data = response.json()
        from genui_api.patch.models import PatchDocument
        patch = PatchDocument.model_validate(data["patch"])
        assert patch is not None

    def test_integrity_non_target_unchanged(self, client: TestClient):
        """AC-35: integrity.nonTargetNodesUnchanged 为 true"""
        response = _post_refine(client, _refine_request())
        data = response.json()
        assert data["integrity"]["nonTargetNodesUnchanged"] is True
        assert data["integrity"]["selectedNodeId"] == "heading-1"

    def test_gold_case(self, gold_case_json, client: TestClient):
        """AC-27: Gold Case 端到端"""
        first_child = gold_case_json["root"]["children"][0]
        payload = _refine_request(
            doc=gold_case_json,
            node_id=first_child["id"],
            instruction="set_text:Gold Test",
        )
        response = _post_refine(client, payload)
        assert response.status_code == 200

    def test_selected_node_id_alias_underscore(self, client: TestClient):
        """AC-41: selected_node_id (下划线) 也能解析"""
        payload = {
            "document": _minimal_valid_dsl(),
            "selected_node_id": "heading-1",
            "instruction": "test",
        }
        response = _post_refine(client, payload)
        assert response.status_code == 200


# ============================================================
# API 反向测试
# ============================================================


class TestRefineApiNegative:
    """AC-36~AC-55: API 反向"""

    def test_unsupported_media_type(self, client: TestClient):
        """AC-36: Content-Type 非 JSON → 415"""
        response = _post_refine(client, json.dumps(_refine_request()), "text/plain")
        assert response.status_code == 415
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "unsupported_media_type"

    def test_empty_body(self, client: TestClient):
        """AC-37: 空 body → 400"""
        response = client.post(
            "/api/v1/dsl/refine",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_json"

    def test_invalid_json_body(self, client: TestClient):
        """AC-38: 非法 JSON → 400"""
        response = _post_refine(client, "{not valid json}", "application/json")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_json"

    def test_missing_required_field(self, client: TestClient):
        """AC-39: 缺少必填字段 → 422"""
        payload = {"document": _minimal_valid_dsl()}  # 缺少 selectedNodeId, instruction
        response = _post_refine(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request_structure"

    def test_extra_field_rejected(self, client: TestClient):
        """AC-40: 额外字段 → 422"""
        payload = _refine_request()
        payload["extraField"] = "not allowed"
        response = _post_refine(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request_structure"

    def test_empty_instruction(self, client: TestClient):
        """AC-42: 空 instruction → 422"""
        response = _post_refine(client, _refine_request(instruction=""))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_instruction"

    def test_long_instruction(self, client: TestClient):
        """AC-43: 超 1000 字符 → 422"""
        response = _post_refine(client, _refine_request(instruction="x" * 1001))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_instruction"

    def test_invalid_source_document(self, client: TestClient):
        """AC-44: 非法源文档 → 422"""
        bad_doc = {"version": "0.1", "root": {"id": "bad", "type": "NotAType"}}
        response = _post_refine(client, _refine_request(doc=bad_doc))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_source_document"

    def test_target_node_not_found(self, client: TestClient):
        """AC-45: 节点不存在 → 422"""
        response = _post_refine(client, _refine_request(node_id="nonexistent"))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "target_node_not_found"

    def test_provider_error(self):
        """AC-46: Provider 异常 → 502"""
        client = _make_client_with_provider(ExceptionProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "provider_error"

    def test_invalid_candidate_structure(self):
        """AC-47: BrokenStructureProvider → 502"""
        client = _make_client_with_provider(BrokenStructureProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "invalid_candidate_structure"

    def test_candidate_boundary_violation_wrong(self):
        """AC-48: WrongTargetProvider → 502"""
        client = _make_client_with_provider(WrongTargetProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "candidate_boundary_violation"

    def test_candidate_boundary_violation_multi(self):
        """AC-49: MultiTargetProvider → 502"""
        client = _make_client_with_provider(MultiTargetProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "candidate_boundary_violation"

    def test_patch_application_failed(self):
        """AC-50: apply_patch 因候选问题失败 → 502"""
        client = _make_client_with_provider(InvalidResultProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "patch_application_failed"

    def test_error_response_format(self, client: TestClient):
        """AC-54: 错误响应格式"""
        response = _post_refine(client, _refine_request(instruction=""))
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "issues" in data["error"]


# ============================================================
# 脱敏验证
# ============================================================


class TestSanitization:
    """AC-66~AC-69: Provider 错误响应脱敏"""

    def test_provider_error_no_instruction_leak(self):
        """AC-66: 错误响应不含 instruction"""
        client = _make_client_with_provider(ExceptionProvider())
        secret_instruction = "SECRET_INSTRUCTION_12345"
        payload = _refine_request(instruction=secret_instruction)
        response = _post_refine(client, payload)
        body_text = response.text
        assert secret_instruction not in body_text

    def test_provider_error_no_document_leak(self):
        """AC-67: 错误响应不含完整 document"""
        client = _make_client_with_provider(ExceptionProvider())
        response = _post_refine(client, _refine_request())
        body_text = response.text
        # 不应包含文档标题（作为文档泄露信号）
        assert "Hello" not in body_text or response.status_code == 200

    def test_provider_error_no_path_leak(self):
        """AC-69: 错误响应不含异常原文或本地路径"""
        client = _make_client_with_provider(ExceptionProvider())
        response = _post_refine(client, _refine_request())
        body_text = response.text
        assert "/path/to/file" not in body_text
        assert "Provider crashed" not in body_text


# ============================================================
# Provider 注入隔离测试
# ============================================================


class TestProviderInjection:
    """AC-62~AC-65: Provider 注入"""

    def test_default_uses_mock_provider(self):
        """AC-62: 默认使用 MockProvider"""
        app = create_app()
        client = TestClient(app)
        response = _post_refine(client, _refine_request())
        assert response.status_code == 200

    def test_custom_provider_injection(self):
        """AC-63: create_app(custom_provider) 使用指定 Provider"""
        client = _make_client_with_provider(BrokenStructureProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502

    def test_two_apps_independent(self):
        """AC-64: app A 的 overrides 不影响 app B"""
        app_a = create_app(refinement_provider=BrokenStructureProvider())
        app_b = create_app()  # 默认 MockProvider
        client_a = TestClient(app_a)
        client_b = TestClient(app_b)

        resp_a = _post_refine(client_a, _refine_request())
        resp_b = _post_refine(client_b, _refine_request())

        assert resp_a.status_code == 502
        assert resp_b.status_code == 200

    def test_clearing_overrides_independent(self):
        """AC-65: 清理一个 app 的 overrides 不影响其他实例"""
        app_a = create_app(refinement_provider=BrokenStructureProvider())
        app_b = create_app(refinement_provider=BrokenStructureProvider())

        # 清除 app_a 的 override
        app_a.dependency_overrides.clear()

        client_a = TestClient(app_a)
        client_b = TestClient(app_b)

        # app_a 回到默认 MockProvider
        resp_a = _post_refine(client_a, _refine_request())
        resp_b = _post_refine(client_b, _refine_request())

        assert resp_a.status_code == 200  # 默认 MockProvider
        assert resp_b.status_code == 502  # 仍然是 BrokenStructureProvider


# ============================================================
# OpenAPI 测试
# ============================================================


class TestOpenApi:
    """AC-77~AC-82: OpenAPI"""

    @pytest.fixture
    def openapi_spec(self):
        app = create_app()
        return app.openapi()

    def test_refine_endpoint_in_openapi(self, openapi_spec):
        """AC-77: OpenAPI 包含 /api/v1/dsl/refine"""
        assert "/api/v1/dsl/refine" in openapi_spec["paths"]
        assert "post" in openapi_spec["paths"]["/api/v1/dsl/refine"]

    def test_request_body_required(self, openapi_spec):
        """AC-78: requestBody required=true"""
        post = openapi_spec["paths"]["/api/v1/dsl/refine"]["post"]
        rb = post["requestBody"]
        assert rb.get("required") is True

    def test_request_body_schema_fields(self, openapi_spec):
        """AC-78: schema 包含必要字段"""
        post = openapi_spec["paths"]["/api/v1/dsl/refine"]["post"]
        schema = post["requestBody"]["content"]["application/json"]["schema"]
        props = schema.get("properties", {})
        assert "selectedNodeId" in props
        assert "instruction" in props
        assert "document" in props

    def test_request_body_required_fields(self, openapi_spec):
        """AC-78: selectedNodeId 和 instruction 在 required 中"""
        post = openapi_spec["paths"]["/api/v1/dsl/refine"]["post"]
        schema = post["requestBody"]["content"]["application/json"]["schema"]
        required = schema.get("required", [])
        assert "selectedNodeId" in required
        assert "instruction" in required

    def test_request_body_additional_properties_false(self, openapi_spec):
        """AC-78: additionalProperties false"""
        post = openapi_spec["paths"]["/api/v1/dsl/refine"]["post"]
        schema = post["requestBody"]["content"]["application/json"]["schema"]
        assert schema.get("additionalProperties") is False

    def test_200_response_references_refine_success(self, openapi_spec):
        """AC-79: 200 响应 schema 引用 RefineSuccess"""
        post = openapi_spec["paths"]["/api/v1/dsl/refine"]["post"]
        resp_200 = post["responses"]["200"]["content"]["application/json"]["schema"]
        assert "RefineSuccess" in str(resp_200)

    def test_error_responses_reference_refine_failure(self, openapi_spec):
        """AC-80: 错误响应引用 RefineFailure"""
        post = openapi_spec["paths"]["/api/v1/dsl/refine"]["post"]
        for code in ["400", "415", "422", "500", "502"]:
            resp = post["responses"][code]["content"]["application/json"]["schema"]
            assert "RefineFailure" in str(resp), f"Status {code} missing RefineFailure"

    def test_integrity_constrained(self, openapi_spec):
        """AC-82: nonTargetNodesUnchanged 在 schema 中被约束为常量 true"""
        schemas = openapi_spec.get("components", {}).get("schemas", {})
        integrity_schema = schemas.get("RefinementIntegrity", {})
        props = integrity_schema.get("properties", {})
        ntnu = props.get("nonTargetNodesUnchanged", {})
        assert ntnu.get("const") is True or ntnu.get("enum") == [True]

    def test_openapi_refine_success_schema(self, openapi_spec):
        """AC-81: patch、document、integrity 在 OpenAPI schema 中不是无约束 object"""
        schemas = openapi_spec.get("components", {}).get("schemas", {})
        success = schemas["RefineSuccess"]
        props = success["properties"]

        # patch 不能是无约束 object
        patch_schema = props["patch"]
        assert not (
            patch_schema.get("type") == "object"
            and patch_schema.get("additionalProperties") is True
        ), "patch must not be unconstrained object"
        # patch 应该通过 $ref 指向 PatchDocument
        assert "$ref" in patch_schema or "allOf" in patch_schema, \
            "patch should reference PatchDocument schema"

        # document 不能是无约束 object
        doc_schema = props["document"]
        assert not (
            doc_schema.get("type") == "object"
            and doc_schema.get("additionalProperties") is True
        ), "document must not be unconstrained object"
        # document 应该通过 $ref 指向 DslDocument
        assert "$ref" in doc_schema or "allOf" in doc_schema, \
            "document should reference DslDocument schema"

        # integrity 引用 RefinementIntegrity
        integrity_schema = props["integrity"]
        assert "$ref" in integrity_schema or "allOf" in integrity_schema

        # nonTargetNodesUnchanged 约束为 true
        integrity_def = schemas["RefinementIntegrity"]
        ntnu = integrity_def["properties"]["nonTargetNodesUnchanged"]
        assert ntnu.get("const") is True or ntnu.get("enum") == [True]


# ============================================================
# AC-51/52/53 补充测试：内部错误路径
# ============================================================


class TestInternalErrorPaths:
    """AC-51, AC-52, AC-53: 内部错误 → HTTP 500"""

    def test_non_target_mutation_detected_500(self, monkeypatch):
        """AC-51: non_target_mutation_detected → HTTP 500"""
        from unittest.mock import patch as mock_patch

        app = create_app()
        client = TestClient(app)

        # 让 verify_non_target_unchanged 返回 False，模拟完整性破坏
        with mock_patch(
            "genui_api.refinement.pipeline.verify_non_target_unchanged",
            return_value=False,
        ):
            response = _post_refine(client, _refine_request())

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "non_target_mutation_detected"

    def test_internal_patch_error_500(self, monkeypatch):
        """AC-52: internal_patch_error → HTTP 500 + internal_error"""
        from genui_api.patch.apply import PatchError
        from unittest.mock import patch as mock_patch

        app = create_app()
        client = TestClient(app)

        def fake_apply_patch(doc, patch):
            raise PatchError(
                code="internal_patch_error",
                message="Internal patch engine failure",
                issues=[],
            )

        with mock_patch(
            "genui_api.refinement.pipeline.apply_patch",
            side_effect=fake_apply_patch,
        ):
            response = _post_refine(client, _refine_request())

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "internal_error"

    def test_unexpected_exception_500(self, monkeypatch):
        """AC-53: 未预期异常 → HTTP 500 + internal_error"""
        from unittest.mock import patch as mock_patch

        app = create_app()
        client = TestClient(app)

        def fake_apply_patch(doc, patch):
            raise RuntimeError("Totally unexpected!")

        with mock_patch(
            "genui_api.refinement.pipeline.apply_patch",
            side_effect=fake_apply_patch,
        ):
            response = _post_refine(client, _refine_request())

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "internal_error"
        # 不得泄露异常原文
        assert "Totally unexpected" not in response.text


# ============================================================
# AC-68 补充测试：错误响应不包含候选 Patch
# ============================================================


class TestNoCandidateInErrorResponse:
    """AC-68: 错误响应不得包含候选 Patch"""

    def test_broken_structure_no_candidate_leak(self):
        """AC-68: BrokenStructureProvider 错误响应不含候选"""
        client = _make_client_with_provider(BrokenStructureProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502
        body_text = response.text
        # BrokenStructureProvider 返回 {"bad": "data"}
        assert '"bad"' not in body_text

    def test_wrong_target_no_candidate_leak(self):
        """AC-68: WrongTargetProvider 错误响应不含候选 Patch 内容"""
        client = _make_client_with_provider(WrongTargetProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502
        body_text = response.text
        # WrongTargetProvider 返回含 "wrong-node-id" 的候选
        assert "wrong-node-id" not in body_text
        assert "hacked" not in body_text

    def test_invalid_result_no_candidate_leak(self):
        """AC-68: InvalidResultProvider 错误响应不含候选 Patch 值"""
        client = _make_client_with_provider(InvalidResultProvider())
        response = _post_refine(client, _refine_request())
        assert response.status_code == 502
        body_text = response.text
        # InvalidResultProvider 返回 level=99 的操作
        assert "99" not in body_text
