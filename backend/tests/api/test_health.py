"""健康检查端点测试"""

import pytest
from fastapi.testclient import TestClient

from genui_api.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestHealthEndpoint:
    """GET /health 端点测试"""

    def test_health_returns_200(self, client: TestClient):
        """健康检查返回 200 状态码"""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_body(self, client: TestClient):
        """响应体完全匹配预期 JSON"""
        response = client.get("/health")
        assert response.json() == {"status": "ok", "service": "genui-api"}

    def test_health_content_type(self, client: TestClient):
        """Content-Type 为 application/json"""
        response = client.get("/health")
        assert response.headers["content-type"] == "application/json"
