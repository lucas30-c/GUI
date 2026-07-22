"""DSL 校验 API 端点测试 — 正向与反向"""

import json

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from genui_api.main import create_app


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def gold_case_json():
    path = Path(__file__).resolve().parents[3] / "examples" / "dsl" / "coffee-shop-landing.json"
    return path.read_text()


def _minimal_valid_dsl() -> dict:
    """最小合法 DSL — 只有一个 Page 节点"""
    return {
        "version": "0.1",
        "root": {
            "id": "page",
            "type": "Page",
            "props": {},
            "children": [],
        },
    }


def _post_dsl(client: TestClient, payload, content_type="application/json"):
    """辅助方法：POST DSL 校验请求"""
    if isinstance(payload, (dict, list)):
        body = json.dumps(payload)
    else:
        body = payload
    return client.post(
        "/api/v1/dsl/validate",
        content=body,
        headers={"Content-Type": content_type},
    )


# ============================================================
# 正向测试
# ============================================================


class TestDslValidationPositive:
    """DSL 校验正向测试"""

    def test_minimal_valid_dsl_returns_200(self, client: TestClient):
        """最小合法 DSL（只有 Page）返回 200"""
        response = _post_dsl(client, _minimal_valid_dsl())
        assert response.status_code == 200

    def test_gold_case_returns_200(self, client: TestClient, gold_case_json: str):
        """Gold Case 文件提交返回 200"""
        response = client.post(
            "/api/v1/dsl/validate",
            content=gold_case_json,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200

    def test_success_response_valid_true(self, client: TestClient):
        """成功响应中 valid == true"""
        response = _post_dsl(client, _minimal_valid_dsl())
        data = response.json()
        assert data["valid"] is True

    def test_success_response_contains_document(self, client: TestClient):
        """成功响应的 document 包含 version 和 root"""
        response = _post_dsl(client, _minimal_valid_dsl())
        doc = response.json()["document"]
        assert "version" in doc
        assert "root" in doc

    def test_document_is_normalized(self, client: TestClient):
        """document 来自 model_dump，root.type == 'Page'"""
        response = _post_dsl(client, _minimal_valid_dsl())
        doc = response.json()["document"]
        assert doc["root"]["type"] == "Page"
        assert doc["root"]["id"] == "page"
        assert doc["version"] == "0.1"

    def test_accepts_charset_utf8(self, client: TestClient):
        """Content-Type: application/json; charset=utf-8 也被接受"""
        body = json.dumps(_minimal_valid_dsl())
        response = client.post(
            "/api/v1/dsl/validate",
            content=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        assert response.status_code == 200

    def test_create_app_independent(self):
        """create_app() 多次调用生成独立应用实例"""
        app1 = create_app()
        app2 = create_app()
        assert app1 is not app2

    def test_openapi_contains_endpoints(self, client: TestClient):
        """GET /openapi.json 包含 /health 和 /api/v1/dsl/validate"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/health" in paths
        assert "/api/v1/dsl/validate" in paths


# ============================================================
# 反向测试
# ============================================================


class TestDslValidationNegative:
    """DSL 校验反向测试"""

    def test_wrong_content_type_returns_415(self, client: TestClient):
        """Content-Type: text/plain → 415, error.code == 'unsupported_media_type'"""
        response = client.post(
            "/api/v1/dsl/validate",
            content="{}",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 415
        assert response.json()["error"]["code"] == "unsupported_media_type"

    def test_empty_body_returns_400(self, client: TestClient):
        """空 body → 400, error.code == 'invalid_json'"""
        response = client.post(
            "/api/v1/dsl/validate",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_json"

    def test_invalid_json_returns_400(self, client: TestClient):
        """无效 JSON → 400, error.code == 'invalid_json'"""
        response = client.post(
            "/api/v1/dsl/validate",
            content="not json{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_json"

    def test_json_array_returns_422_structure(self, client: TestClient):
        """JSON 数组 → 422, error.code == 'invalid_dsl_structure'"""
        response = _post_dsl(client, [1, 2, 3])
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_structure"

    def test_wrong_version_returns_422_structure(self, client: TestClient):
        """version: '2.0' → 422, error.code == 'invalid_dsl_structure'"""
        payload = _minimal_valid_dsl()
        payload["version"] = "2.0"
        response = _post_dsl(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_structure"

    def test_root_not_page_returns_422_structure(self, client: TestClient):
        """root 为 Section → 422, error.code == 'invalid_dsl_structure'"""
        payload = {
            "version": "0.1",
            "root": {
                "id": "section",
                "type": "Section",
                "props": {},
                "children": [],
            },
        }
        response = _post_dsl(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_structure"

    def test_unknown_component_returns_422_structure(self, client: TestClient):
        """未知组件类型 → 422, error.code == 'invalid_dsl_structure'"""
        payload = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {},
                "children": [
                    {
                        "id": "unknown",
                        "type": "UnknownWidget",
                        "props": {},
                    }
                ],
            },
        }
        response = _post_dsl(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_structure"

    def test_unknown_node_field_returns_422_structure(self, client: TestClient):
        """节点有额外字段 → 422, error.code == 'invalid_dsl_structure'"""
        payload = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {},
                "children": [],
                "extraField": "not allowed",
            },
        }
        response = _post_dsl(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_structure"

    def test_unknown_props_field_returns_422_structure(self, client: TestClient):
        """props 有额外字段 → 422, error.code == 'invalid_dsl_structure'"""
        payload = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {"unknownProp": "value"},
                "children": [],
            },
        }
        response = _post_dsl(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_structure"

    def test_duplicate_id_returns_422_business(self, client: TestClient):
        """重复 ID → 422, error.code == 'invalid_dsl_business_rule'"""
        payload = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {},
                "children": [
                    {
                        "id": "same-id",
                        "type": "Section",
                        "props": {},
                        "children": [],
                    },
                    {
                        "id": "same-id",
                        "type": "Section",
                        "props": {},
                        "children": [],
                    },
                ],
            },
        }
        response = _post_dsl(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_business_rule"

    def test_duplicate_id_preserves_issue_code(self, client: TestClient):
        """issues 中保留 code == 'duplicate_id'"""
        payload = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {},
                "children": [
                    {
                        "id": "dup",
                        "type": "Section",
                        "props": {},
                        "children": [],
                    },
                    {
                        "id": "dup",
                        "type": "Section",
                        "props": {},
                        "children": [],
                    },
                ],
            },
        }
        response = _post_dsl(client, payload)
        issues = response.json()["error"]["issues"]
        codes = [issue["code"] for issue in issues]
        assert "duplicate_id" in codes

    def test_input_outside_form_returns_422_business(self, client: TestClient):
        """Input 在 Form 外 → 422, error.code == 'invalid_dsl_business_rule'"""
        payload = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {},
                "children": [
                    {
                        "id": "loose-input",
                        "type": "Input",
                        "props": {"name": "email", "label": "Email"},
                    }
                ],
            },
        }
        response = _post_dsl(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_business_rule"

    def test_page_nested_returns_422_business(self, client: TestClient):
        """Page 嵌套 → 422, error.code == 'invalid_dsl_business_rule'"""
        payload = {
            "version": "0.1",
            "root": {
                "id": "page",
                "type": "Page",
                "props": {},
                "children": [
                    {
                        "id": "nested-page",
                        "type": "Page",
                        "props": {},
                        "children": [],
                    }
                ],
            },
        }
        response = _post_dsl(client, payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dsl_business_rule"

    def test_error_response_has_valid_false(self, client: TestClient):
        """所有错误响应中 valid == false"""
        # 400 错误
        r1 = client.post(
            "/api/v1/dsl/validate",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert r1.json()["valid"] is False

        # 415 错误
        r2 = client.post(
            "/api/v1/dsl/validate",
            content="{}",
            headers={"Content-Type": "text/plain"},
        )
        assert r2.json()["valid"] is False

        # 422 错误
        payload = _minimal_valid_dsl()
        payload["version"] = "2.0"
        r3 = _post_dsl(client, payload)
        assert r3.json()["valid"] is False

    def test_error_response_has_path(self, client: TestClient):
        """issues 中有 path 字段"""
        payload = _minimal_valid_dsl()
        payload["version"] = "2.0"
        response = _post_dsl(client, payload)
        issues = response.json()["error"]["issues"]
        assert len(issues) > 0
        for issue in issues:
            assert "path" in issue

    def test_error_no_traceback(self, client: TestClient):
        """错误响应不含 'Traceback'、'File '、'.py'"""
        # 提交各种无效请求
        invalid_payloads = [
            ("not json{", "application/json"),
            (json.dumps({"version": "2.0", "root": {}}), "application/json"),
            (json.dumps([1, 2, 3]), "application/json"),
        ]
        for body, ct in invalid_payloads:
            response = client.post(
                "/api/v1/dsl/validate",
                content=body,
                headers={"Content-Type": ct},
            )
            text = response.text
            assert "Traceback" not in text
            assert "File " not in text
            assert ".py" not in text
