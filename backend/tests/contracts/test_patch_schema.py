"""
Patch v0.1 Schema 一致性与回归测试

覆盖：
- Patch JSON Schema 确定性导出与一致性验证
- DSL schema.json 未被修改
- Gold Case 仍通过 DSL 校验
- GET /health 行为不变
- POST /api/v1/dsl/validate 行为不变
- OpenAPI 不含意外的 Patch 端点
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genui_api.contracts.dsl import DslDocument
from genui_api.contracts.validation import validate_dsl_document
from genui_api.main import create_app
from genui_api.patch import export_patch_schema

# ============================================================
# 路径常量
# ============================================================

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PATCH_SCHEMA_PATH = _PROJECT_ROOT / "contracts" / "patch" / "v0.1" / "schema.json"
_DSL_SCHEMA_PATH = _PROJECT_ROOT / "contracts" / "dsl" / "v0.1" / "schema.json"
_GOLD_CASE_PATH = _PROJECT_ROOT / "examples" / "dsl" / "coffee-shop-landing.json"


# ============================================================
# Schema 一致性测试
# ============================================================


class TestPatchSchemaConsistency:
    """Patch Schema 导出一致性"""

    def test_exported_schema_matches_committed_file(self):
        """当前模型导出 schema 与已提交文件逐字节一致"""
        exported = export_patch_schema()
        committed = _PATCH_SCHEMA_PATH.read_text(encoding="utf-8")
        # 文件末尾有换行
        assert exported + "\n" == committed

    def test_schema_export_deterministic(self):
        """两次导出结果完全相同（确定性）"""
        first = export_patch_schema()
        second = export_patch_schema()
        assert first == second

    def test_schema_contains_version_metadata(self):
        """Schema 包含 x-patch-version: "0.1" 元数据"""
        schema = json.loads(export_patch_schema())
        assert schema.get("x-patch-version") == "0.1"

    def test_schema_has_sort_keys_and_indent(self):
        """Schema 使用 sort_keys=True, indent=2 格式"""
        exported = export_patch_schema()
        # 验证 indent=2 — 检查换行后有 2 空格缩进
        lines = exported.split("\n")
        assert len(lines) > 3
        # 第二行应以 2 个空格开始
        indented_lines = [l for l in lines if l.startswith("  ")]
        assert len(indented_lines) > 0
        # sort_keys — 验证 properties 内键是有序的
        schema = json.loads(exported)
        if "properties" in schema:
            keys = list(schema["properties"].keys())
            assert keys == sorted(keys)

    def test_schema_is_valid_json(self):
        """导出 schema 是合法 JSON"""
        exported = export_patch_schema()
        parsed = json.loads(exported)
        assert isinstance(parsed, dict)


# ============================================================
# DSL Schema 未被修改（回归）
# ============================================================


class TestDslSchemaUnchanged:
    """DSL schema.json 未被修改"""

    def test_dsl_schema_json_unchanged(self):
        """DSL schema.json 与 export_json_schema() 导出一致"""
        from genui_api.contracts.schema_export import export_json_schema

        exported_str = export_json_schema()
        committed = _DSL_SCHEMA_PATH.read_text(encoding="utf-8")
        assert exported_str + "\n" == committed


# ============================================================
# Gold Case 回归
# ============================================================


class TestGoldCaseRegression:
    """Gold Case 仍通过 DSL 校验"""

    def test_gold_case_passes_dsl_validation(self):
        """Gold Case coffee-shop-landing.json 仍通过完整 DSL 校验"""
        data = json.loads(_GOLD_CASE_PATH.read_text())
        doc = validate_dsl_document(data)
        assert isinstance(doc, DslDocument)
        assert doc.version == "0.1"
        assert doc.root.type == "Page"


# ============================================================
# API 回归测试
# ============================================================


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestApiRegression:
    """API 行为不变（回归）"""

    def test_health_endpoint_unchanged(self, client: TestClient):
        """GET /health 行为不变"""
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body == {"status": "ok", "service": "genui-api"}

    def test_dsl_validate_endpoint_valid_doc(self, client: TestClient):
        """POST /api/v1/dsl/validate 对合法文档返回 200"""
        data = json.loads(_GOLD_CASE_PATH.read_text())
        response = client.post(
            "/api/v1/dsl/validate",
            content=json.dumps(data),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("valid") is True

    def test_dsl_validate_endpoint_invalid_doc(self, client: TestClient):
        """POST /api/v1/dsl/validate 对非法文档返回 422"""
        bad_data = {"version": "0.1", "root": {"id": "x", "type": "Unknown"}}
        response = client.post(
            "/api/v1/dsl/validate",
            content=json.dumps(bad_data),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        body = response.json()
        assert body.get("valid") is False
        assert "error" in body

    def test_openapi_no_patch_endpoints(self, client: TestClient):
        """OpenAPI 不包含意外的 Patch 端点"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        openapi = response.json()
        paths = openapi.get("paths", {})
        for path_key in paths:
            assert "patch" not in path_key.lower() or path_key == "/health"
            # 确保没有 /api/v1/patch 之类的端点
        # 更严格检查
        patch_paths = [p for p in paths if "patch" in p.lower()]
        assert len(patch_paths) == 0, f"发现意外 Patch 端点: {patch_paths}"
