"""
Patch v0.1 JSON Schema 导出工具

提供确定性的 JSON Schema 导出功能：
- export_patch_schema() 返回格式化 JSON 字符串
- 可作为脚本直接运行，导出到 stdout 或指定文件
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .models import PatchDocument

# 默认导出路径（相对于项目根目录）
_DEFAULT_OUTPUT_PATH = Path("contracts/patch/v0.1/schema.json")


def export_patch_schema() -> str:
    """
    导出 PatchDocument 的 JSON Schema。

    返回确定性格式化的 JSON 字符串（sort_keys=True, indent=2），
    每次调用输出完全相同。含版本标记 x-patch-version。
    """
    schema = PatchDocument.model_json_schema()
    schema["x-patch-version"] = "0.1"
    return json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False)


def _find_project_root() -> Path:
    """从当前文件向上查找项目根目录（含 backend/ 目录的父级）"""
    # 本文件位于 backend/src/genui_api/patch/schema_export.py
    # 项目根目录是 backend 的父目录
    current = Path(__file__).resolve()
    # 向上 4 级：patch -> genui_api -> src -> backend -> 项目根
    return current.parents[4]


def main() -> None:
    """命令行入口：导出 JSON Schema 到文件或 stdout"""
    schema_str = export_patch_schema()

    if len(sys.argv) > 1 and sys.argv[1] == "--stdout":
        print(schema_str)
        return

    # 确定输出路径
    if len(sys.argv) > 1:
        output_path = Path(sys.argv[1])
    else:
        project_root = _find_project_root()
        output_path = project_root / _DEFAULT_OUTPUT_PATH

    # 确保目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入文件（末尾换行）
    output_path.write_text(schema_str + "\n", encoding="utf-8")
    print(f"Patch JSON Schema 已导出到: {output_path}")


if __name__ == "__main__":
    main()
