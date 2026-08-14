"""契约一致性测试 — Style 白名单的单一事实来源守护（根因修复 RC2）。

断言以下副本全部派生自同一个事实来源（contracts.dsl.Style 模型），
任何一份漂移都会在此红灯：

1. Style 模型 ↔ style_registry（导入期校验之外的显式断言）；
2. Style 模型 ↔ 提交的 contracts/dsl/v0.1/schema.json（JSON Schema 快照）；
3. Style 模型 ↔ 提交的 contracts/patch/v0.1/schema.json（Patch 复用同一 Style）；
4. Style 模型 ↔ 生成侧 System Prompt 的白名单段落（由 registry 渲染）；
5. Style 模型 ↔ 精修侧 System Prompt 的白名单段落（同一段落，两处一致）；
6. repair 机器可读契约（machine_contract）覆盖全部字段且带值域文法；
7. 枚举值域：registry 内省值 == 模型 Literal 注解 == schema.json enum。
"""

import json
from pathlib import Path

import pytest

from genui_api.contracts.dsl import Style
from genui_api.contracts.style_registry import (
    field_enum_values,
    machine_contract,
    render_style_contract_text,
    style_field_count,
    style_field_names,
)
from genui_api.llm.prompts import (
    build_generation_system_prompt,
    build_refinement_system_prompt,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DSL_SCHEMA_PATH = _PROJECT_ROOT / "contracts" / "dsl" / "v0.1" / "schema.json"
_PATCH_SCHEMA_PATH = _PROJECT_ROOT / "contracts" / "patch" / "v0.1" / "schema.json"


def _load_style_props(schema_path: Path) -> dict:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return schema["$defs"]["Style"]["properties"]


# ============================================================
# 1. 模型 ↔ registry
# ============================================================


def test_registry_matches_model_fields_exactly():
    assert set(style_field_names()) == set(Style.model_fields)
    assert style_field_count() == len(Style.model_fields) == 31


def test_machine_contract_covers_every_field_with_grammar():
    contract = machine_contract()
    assert set(contract) == set(Style.model_fields)
    for name, entry in contract.items():
        assert entry["grammar"], name
        assert entry["valueType"], name
        assert isinstance(entry["examples"], list), name


# ============================================================
# 2 / 3. 模型 ↔ 提交的 JSON Schema 快照
# ============================================================


def test_dsl_schema_json_style_matches_model():
    props = _load_style_props(_DSL_SCHEMA_PATH)
    assert set(props) == set(Style.model_fields)


def test_patch_schema_json_style_matches_model():
    props = _load_style_props(_PATCH_SCHEMA_PATH)
    assert set(props) == set(Style.model_fields)


def test_schema_json_style_is_closed_whitelist():
    schema = json.loads(_DSL_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$defs"]["Style"].get("additionalProperties") is False


# ============================================================
# 4 / 5. 模型 ↔ 两份 System Prompt
# ============================================================


@pytest.mark.parametrize("builder", [build_generation_system_prompt, build_refinement_system_prompt])
def test_system_prompts_list_every_style_field(builder):
    sp = builder()
    for name in style_field_names():
        assert name in sp, f"{name} missing in {builder.__name__}"


@pytest.mark.parametrize("builder", [build_generation_system_prompt, build_refinement_system_prompt])
def test_system_prompts_state_correct_field_count(builder):
    sp = builder()
    assert f"共 {style_field_count()} 个字段" in sp


def test_generation_and_refinement_share_identical_style_section():
    """两份 SP 的 style 段落逐字节相同——同一渲染函数，永不互相漂移。"""
    section = render_style_contract_text()
    assert section in build_generation_system_prompt()
    assert section in build_refinement_system_prompt()


# ============================================================
# 7. 枚举值域：registry ↔ 模型 ↔ schema.json
# ============================================================

_ENUM_FIELDS_IN_SCHEMA = ("fontWeight", "textAlign", "display", "flexDirection",
                          "justifyContent", "alignItems", "borderStyle")


@pytest.mark.parametrize("field_name", _ENUM_FIELDS_IN_SCHEMA)
def test_registry_enum_values_match_model_literal(field_name):
    import typing

    from genui_api.contracts.dsl import Style as StyleModel

    annotation = StyleModel.model_fields[field_name].annotation
    literal_values = None
    for arg in typing.get_args(annotation):
        if typing.get_origin(arg) is typing.Literal:
            literal_values = [str(v) for v in typing.get_args(arg)]
    assert literal_values is not None, field_name
    assert list(field_enum_values(field_name)) == literal_values


@pytest.mark.parametrize("field_name", _ENUM_FIELDS_IN_SCHEMA)
def test_registry_enum_values_match_schema_json(field_name):
    props = _load_style_props(_DSL_SCHEMA_PATH)
    node = props[field_name]
    # Optional[Literal[...]] 导出为 anyOf: [{enum...}, {type: null}]，先解包
    if "anyOf" in node:
        enum_branches = [b for b in node["anyOf"] if "enum" in b]
        assert len(enum_branches) == 1, field_name
        enum_in_schema = enum_branches[0]["enum"]
    else:
        enum_in_schema = node.get("enum")
    assert enum_in_schema is not None, field_name
    assert list(field_enum_values(field_name)) == enum_in_schema


def test_margin_shorthand_grammar_mentions_auto():
    """Owner 复现值的值域必须出现在 SP 与 repair 契约中（模型可见）。"""
    section = render_style_contract_text()
    assert '"0 auto"' in section
    contract = machine_contract()
    assert contract["margin"]["valueType"] == "margin_shorthand"
    assert "auto" in contract["margin"]["grammar"]
    assert contract["padding"]["valueType"] == "padding_shorthand"
    assert "不允许 auto" in contract["padding"]["grammar"]
