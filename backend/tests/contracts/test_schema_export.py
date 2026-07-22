"""
DSL v0.1 Schema 导出测试 — 验证 JSON Schema 导出的正确性和确定性
"""

import json
from pathlib import Path

from genui_api.contracts.schema_export import export_json_schema

# 已提交的 schema.json 路径
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "dsl" / "v0.1" / "schema.json"


class TestSchemaExport:
    """JSON Schema 导出功能"""

    def test_export_returns_valid_json(self):
        """export_json_schema() 返回合法 JSON 字符串"""
        result = export_json_schema()
        # 应能被解析为合法 JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        # 应包含 JSON Schema 基本结构
        assert "properties" in parsed or "$defs" in parsed

    def test_export_contains_dsl_version(self):
        """导出的 schema 应包含 x-dsl-version 标记"""
        result = export_json_schema()
        parsed = json.loads(result)
        assert parsed.get("x-dsl-version") == "0.1"

    def test_export_is_deterministic(self):
        """两次调用返回完全相同的字符串（确定性）"""
        first = export_json_schema()
        second = export_json_schema()
        assert first == second

    def test_export_matches_committed_schema(self):
        """导出结果与已提交的 contracts/dsl/v0.1/schema.json 一致"""
        exported = export_json_schema()
        # 已提交文件末尾有换行符，导出结果没有，需要统一对比
        committed = _SCHEMA_PATH.read_text(encoding="utf-8")
        # schema.json 文件写入时是 schema_str + "\n"，所以去掉尾部换行比较
        assert exported == committed.rstrip("\n")
