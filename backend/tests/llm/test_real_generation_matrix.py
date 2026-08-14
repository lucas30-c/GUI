"""Real Provider 生成矩阵 — 真实模型 + 完整 HTTP 链路（显式 opt-in，默认 skip）。

闸门与 test_real_smoke.py 相同：
1. GENUI_RUN_REAL_LLM=1（conftest 夹具强制）；
2. GENUI_MODEL_PROVIDER=openai_compatible + Key / BaseURL / Model 齐备。

验收语义（Owner §6.3）：
- 5 组 Prompt 全覆盖，其中摄影师 Prompt 连续执行 5 次；
- 统计：首次成功率 / repair 触发次数 / repair 成功率 / 最终成功率 /
  每次 request ID / Provider、模型、耗时（全部由响应 meta 携带）；
- 硬性断言：任何一次响应都不得把内部 Style 校验原文（Pydantic 路径 / Value
  error / Extra inputs are not permitted）直接暴露给用户；失败响应的
  error.message 必须是用户可读文案。
- 不输出 API Key。
"""

import json
import uuid

import httpx
import pytest

from genui_api.contracts.validation import validate_dsl_document
from genui_api.llm.client import (
    PROVIDER_OPENAI_COMPATIBLE,
    ProviderConfigError,
    load_model_config,
)
from genui_api.main import create_app

pytestmark = pytest.mark.real_llm

BASE_URL = "http://real-matrix"

# 内部校验原文的泄漏指纹：出现任何一个即说明分层错误边界被击穿。
_INTERNAL_ERROR_FINGERPRINTS = (
    "Value error",
    "Extra inputs are not permitted",
    "root.children",
    "schema_error",
    "pydantic",
    "ValidationError",
)

# 5 组验收 Prompt（Owner §6.3）
SINGLE_RUN_PROMPTS = [
    ("做一个简单的个人主页", 8),
    (
        "生成一个北京旅游介绍页，包含 Hero、景点卡片、三日行程、美食推荐、FAQ 和 CTA",
        15,
    ),
    (
        "生成一个企业服务落地页，包含 Hero 介绍、核心服务、客户案例、"
        "常见问题 FAQ 和联系咨询表单（姓名、邮箱、公司名称、需求描述输入框和提交按钮）",
        12,
    ),
    (
        "生成一个后台管理页面，包含顶部筛选栏、数据概览卡片网格和数据展示区域",
        10,
    ),
]

PHOTOGRAPHER_PROMPT = (
    "为独立摄影师创建一个深色作品集主页，包含项目分类、客户评价和联系入口"
)
PHOTOGRAPHER_RUNS = 5
PHOTOGRAPHER_MIN_NODES = 12


@pytest.fixture(scope="module")
def config():
    try:
        loaded = load_model_config()
    except ProviderConfigError as exc:
        pytest.skip(f"credentials not configured: {exc}")
    if loaded.provider != PROVIDER_OPENAI_COMPATIBLE:
        pytest.skip("credentials not configured: real provider not set")
    return loaded


@pytest.fixture(scope="module")
def app(config):
    """真实 Provider 由环境变量装配；不注入任何 stub。"""
    return create_app()


def _new_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=BASE_URL, timeout=300.0
    )


def _count_nodes(node: dict) -> int:
    return 1 + sum(_count_nodes(child) for child in node.get("children", []))


def _collect_styles(node: dict, acc: list) -> list:
    if node.get("style"):
        acc.append(node["style"])
    for child in node.get("children", []):
        _collect_styles(child, acc)
    return acc


def _assert_no_internal_error_leak(body: dict, request_id: str) -> None:
    """分层错误边界：用户可见响应中不得出现内部校验原文。"""
    text = json.dumps(body, ensure_ascii=False)
    for fingerprint in _INTERNAL_ERROR_FINGERPRINTS:
        assert fingerprint not in text, (
            f"request_id={request_id}: internal error text leaked to user: {fingerprint}"
        )


async def _run_once(client: httpx.AsyncClient, prompt: str, min_nodes: int) -> dict:
    """执行一次生成并返回统计记录；断言最终成功且无内部错误泄漏。"""
    request_id = uuid.uuid4().hex
    response = await client.post(
        "/api/v1/dsl/generate",
        json={"prompt": prompt},
        headers={"X-Request-ID": request_id},
    )
    body = response.json()

    # 无论成败：响应 header 必须回带 request ID（可观测性串联）
    assert response.headers.get("x-request-id") == request_id
    _assert_no_internal_error_leak(body, request_id)

    assert response.status_code == 200, (
        f"request_id={request_id} prompt={prompt!r} "
        f"status={response.status_code} body={json.dumps(body, ensure_ascii=False)[:800]}"
    )
    assert body["success"] is True

    document = body["document"]
    meta = body["meta"]
    assert meta["requestId"] == request_id

    # 文档必须通过与 Mock 相同的完整校验器（响应即已校验，这里双重验证）
    validate_dsl_document(document)

    node_count = _count_nodes(document["root"])
    assert node_count >= min_nodes, (
        f"request_id={request_id}: page too small ({node_count} nodes) for prompt {prompt!r}"
    )
    assert document["root"]["children"], "Page must contain sections"

    styles = _collect_styles(document["root"], [])

    return {
        "prompt": prompt,
        "request_id": request_id,
        "http_status": response.status_code,
        "attempts": meta["attempts"],
        "repair_used": meta["repairUsed"],
        "normalization_count": len(meta["normalization"]),
        "structured_output": meta["structuredOutput"],
        "provider": meta["provider"],
        "model": meta["model"],
        "duration_ms": meta["durationMs"],
        "node_count": node_count,
        "style_node_count": len(styles),
    }


def _print_stats(title: str, records: list[dict]) -> None:
    total = len(records)
    first_pass = sum(1 for r in records if r["attempts"] == 1)
    repair_triggered = sum(1 for r in records if r["repair_used"])
    final_success = total  # _run_once 内已断言成功
    print(f"\n=== Real Matrix: {title} ===")
    for r in records:
        print(
            f"  request_id={r['request_id']} attempts={r['attempts']} "
            f"repair={r['repair_used']} normalization={r['normalization_count']} "
            f"nodes={r['node_count']} styles={r['style_node_count']} "
            f"structured_output={r['structured_output']} "
            f"duration_ms={r['duration_ms']} model={r['model']}"
        )
    print(
        f"  统计: runs={total} first_pass={first_pass}/{total} "
        f"repair_triggered={repair_triggered} final_success={final_success}/{total}"
    )


@pytest.mark.parametrize(
    "prompt,min_nodes", SINGLE_RUN_PROMPTS, ids=[p[0][:12] for p in SINGLE_RUN_PROMPTS]
)
def test_real_generation_single_run_prompts(app, prompt, min_nodes):
    import asyncio

    async def run():
        async with _new_client(app) as client:
            return await _run_once(client, prompt, min_nodes)

    record = asyncio.run(run())
    _print_stats("single-run", [record])


def test_real_generation_photographer_five_consecutive_runs(app):
    """摄影师 Prompt 连续 5 次：全部最终成功且无同类 Style 错误暴露。"""
    import asyncio

    async def run():
        records = []
        async with _new_client(app) as client:
            for _ in range(PHOTOGRAPHER_RUNS):
                records.append(
                    await _run_once(client, PHOTOGRAPHER_PROMPT, PHOTOGRAPHER_MIN_NODES)
                )
        return records

    records = asyncio.run(run())
    _print_stats("photographer x5", records)
    assert len(records) == PHOTOGRAPHER_RUNS
    assert all(r["http_status"] == 200 for r in records)
    # 深色主题诉求必须落到样式上：至少一部分节点带 style
    assert all(r["style_node_count"] > 0 for r in records)
