"""对抗性候选测试 — 模型输出必须无法绕过确定性校验层（Spec 008 AC-28 ~ AC-35）。

结构：真实 Provider（OpenAICompat*）+ stub client。请求走完整 HTTP → Pipeline →
校验器链路，唯一被替换的是网络调用本身。因此这里验证的是「信任边界在本地校验器，
不在模型侧 structured output」这条断言，而不是 Provider 自己的自证。

安全边界按**能力**定义而非字符：合法文本里出现 "<div>" 或 "javascript:" 字样并不
构成风险（DSL 不渲染 HTML、不执行内容），因此正向对照必须被接受——否则就是把
字符 grep 当安全断言，既误伤正常内容又给不出真实保护。
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from genui_api.generation.openai_compat_provider import OpenAICompatGenerationProvider
from genui_api.main import create_app
from genui_api.provider.openai_compat_provider import OpenAICompatRefinementProvider

TEST_MODEL = "test-model"
PLACEHOLDER_KEY = "test-api-key-placeholder"
PLACEHOLDER_BASE_URL = "https://example.invalid/v1"

SOURCE_DOCUMENT = {
    "version": "0.1",
    "root": {
        "id": "page",
        "type": "Page",
        "props": {"title": "Demo"},
        "children": [
            {
                "id": "hero",
                "type": "Section",
                "props": {},
                "children": [
                    {
                        "id": "hero.title",
                        "type": "Heading",
                        "props": {"text": "欢迎", "level": 1},
                    },
                    {"id": "hero.body", "type": "Text", "props": {"text": "正文"}},
                ],
            }
        ],
    },
}


class StubClient:
    """返回预设内容的 AsyncOpenAI 替身；不做任何 I/O。"""

    def __init__(self, content):
        self.content = content
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )


def _generation_client(candidate):
    content = candidate if isinstance(candidate, str) else json.dumps(candidate)
    provider = OpenAICompatGenerationProvider(
        client=StubClient(content), model=TEST_MODEL
    )
    return TestClient(create_app(generation_provider=provider))


def _refinement_client(candidate):
    content = candidate if isinstance(candidate, str) else json.dumps(candidate)
    provider = OpenAICompatRefinementProvider(
        client=StubClient(content), model=TEST_MODEL
    )
    return TestClient(create_app(refinement_provider=provider))


def _generate(client, prompt="做一个落地页"):
    return client.post(
        "/api/v1/dsl/generate",
        content=json.dumps({"prompt": prompt}),
        headers={"Content-Type": "application/json"},
    )


def _refine(client, node_id="hero.title", instruction="改一下这个节点"):
    return client.post(
        "/api/v1/dsl/refine",
        content=json.dumps(
            {
                "document": SOURCE_DOCUMENT,
                "selectedNodeId": node_id,
                "instruction": instruction,
            }
        ),
        headers={"Content-Type": "application/json"},
    )


def _document(root, **extra):
    doc = {"version": "0.1", "root": root}
    doc.update(extra)
    return doc


def _page(children, **props):
    return {"id": "page", "type": "Page", "props": props, "children": children}


# ============================================================
# 生成侧：越界候选一律被拒（AC-28 / AC-30）
# ============================================================


def test_extra_top_level_field_is_rejected():
    client = _generation_client(
        _document(_page([]), evil="ignore-previous-instructions")
    )
    response = _generate(client)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


def test_extra_node_field_is_rejected():
    node = {
        "id": "hero.title",
        "type": "Heading",
        "props": {"text": "Hi", "level": 1},
        "script": "alert(1)",
    }
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


def test_event_handler_prop_is_rejected():
    node = {
        "id": "hero.cta",
        "type": "Button",
        "props": {"text": "点我", "onClick": "alert(1)"},
    }
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


@pytest.mark.parametrize(
    "src",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "  javascript:alert(1)",
        "vbscript:msgbox(1)",
    ],
)
def test_dangerous_image_src_is_rejected(src):
    node = {"id": "hero.img", "type": "Image", "props": {"src": src, "alt": "x"}}
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


@pytest.mark.parametrize("node_type", ["script", "div", "iframe", "HtmlBlock"])
def test_unregistered_component_type_is_rejected(node_type):
    node = {"id": "evil", "type": node_type, "props": {}}
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


def test_arbitrary_css_in_style_is_rejected():
    node = {
        "id": "hero.title",
        "type": "Heading",
        "props": {"text": "Hi", "level": 1},
        "style": {"position": "absolute"},
    }
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


def test_duplicate_ids_are_rejected():
    children = [
        {"id": "dup", "type": "Text", "props": {"text": "a"}},
        {"id": "dup", "type": "Text", "props": {"text": "b"}},
    ]
    response = _generate(_generation_client(_document(_page(children))))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


def test_non_page_root_is_rejected():
    root = {"id": "sec", "type": "Section", "props": {}, "children": []}
    response = _generate(_generation_client(_document(root)))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


def test_input_outside_form_is_rejected():
    node = {
        "id": "email",
        "type": "Input",
        "props": {"name": "email", "label": "邮箱"},
    }
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


def test_wrong_dsl_version_is_rejected():
    doc = {"version": "9.9", "root": _page([])}
    response = _generate(_generation_client(doc))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_generated_document"


def test_non_json_model_output_becomes_provider_error():
    response = _generate(_generation_client("好的，这是你的页面：<html>...</html>"))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"


def test_prose_wrapped_json_is_not_salvaged():
    """不实现「从自然语言里抠 JSON」的容错：那会把不合格模型伪装成合格。"""
    response = _generate(
        _generation_client('这是结果：\n```json\n{"version": "0.1"}\n```')
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"


def test_json_array_output_is_rejected():
    response = _generate(_generation_client("[]"))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"


# ============================================================
# 生成侧正向对照：合法文本必须被接受（DD-14）
# ============================================================


def test_html_looking_text_content_is_accepted():
    """Text.text = "<div>Hello</div>" 是普通字符串，不是能力泄漏，必须原样通过。"""
    payload = "<div>Hello</div>"
    node = {"id": "hero.body", "type": "Text", "props": {"text": payload}}
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["document"]["root"]["children"][0]["props"]["text"] == payload


def test_script_like_text_content_is_accepted():
    payload = "如何防止 <script>alert(1)</script> 注入？"
    node = {"id": "hero.body", "type": "Text", "props": {"text": payload}}
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 200, response.text
    assert response.json()["document"]["root"]["children"][0]["props"]["text"] == payload


def test_heading_text_mentioning_javascript_scheme_is_accepted():
    payload = "别用 javascript: 链接"
    node = {"id": "hero.title", "type": "Heading", "props": {"text": payload, "level": 2}}
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 200, response.text


def test_https_image_src_is_accepted():
    node = {
        "id": "hero.img",
        "type": "Image",
        "props": {"src": "https://example.com/a.png", "alt": "示意图"},
    }
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 200, response.text


# ============================================================
# 精修侧：越界候选一律被拒（AC-28 / AC-30）
# ============================================================


def test_patch_targeting_non_selected_node_is_rejected():
    candidate = {
        "version": "0.1",
        "operations": [
            {"op": "update_props", "targetNodeId": "hero.body", "props": {"text": "被改"}}
        ],
    }
    response = _refine(_refinement_client(candidate), node_id="hero.title")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "candidate_boundary_violation"


def test_patch_with_extra_out_of_boundary_operation_is_rejected():
    candidate = {
        "version": "0.1",
        "operations": [
            {"op": "update_props", "targetNodeId": "hero.title", "props": {"text": "新"}},
            {"op": "update_props", "targetNodeId": "hero.body", "props": {"text": "偷改"}},
        ],
    }
    response = _refine(_refinement_client(candidate), node_id="hero.title")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "candidate_boundary_violation"


@pytest.mark.parametrize("op", ["remove", "add", "move", "replace", "delete_node"])
def test_unsupported_patch_operation_is_rejected(op):
    candidate = {
        "version": "0.1",
        "operations": [{"op": op, "targetNodeId": "hero.title", "props": {}}],
    }
    response = _refine(_refinement_client(candidate))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_candidate_structure"


@pytest.mark.parametrize("forbidden", ["id", "type", "children"])
def test_patch_modifying_identity_or_structure_is_rejected(forbidden):
    candidate = {
        "version": "0.1",
        "operations": [
            {
                "op": "update_props",
                "targetNodeId": "hero.title",
                "props": {forbidden: "hijacked"},
            }
        ],
    }
    response = _refine(_refinement_client(candidate))
    assert response.status_code >= 400
    assert response.json()["error"]["code"] != "provider_error"
    assert response.json().get("success") is False


def test_patch_with_event_handler_prop_is_rejected():
    candidate = {
        "version": "0.1",
        "operations": [
            {
                "op": "update_props",
                "targetNodeId": "hero.title",
                "props": {"onClick": "alert(1)"},
            }
        ],
    }
    response = _refine(_refinement_client(candidate))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "patch_application_failed"


def test_patch_with_arbitrary_css_is_rejected():
    candidate = {
        "version": "0.1",
        "operations": [
            {
                "op": "update_props",
                "targetNodeId": "hero.title",
                "props": {"style": {"position": "fixed"}},
            }
        ],
    }
    response = _refine(_refinement_client(candidate))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "patch_application_failed"


def test_patch_returning_full_document_is_rejected():
    response = _refine(_refinement_client(SOURCE_DOCUMENT))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_candidate_structure"


def test_non_json_patch_output_becomes_provider_error():
    response = _refine(_refinement_client("好的，我已经把标题改成红色了。"))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"


# ============================================================
# 精修侧正向对照
# ============================================================


def test_style_inside_props_is_rejected():
    """node 级 style 不是 props 的键：即使值本身合法也必须被拒（契约事实）。"""
    candidate = {
        "version": "0.1",
        "operations": [
            {
                "op": "update_props",
                "targetNodeId": "hero.title",
                "props": {"style": {"color": "#ff0000"}},
            }
        ],
    }
    response = _refine(_refinement_client(candidate))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "patch_application_failed"


def test_legal_props_patch_is_accepted():
    candidate = {
        "version": "0.1",
        "operations": [
            {
                "op": "update_props",
                "targetNodeId": "hero.title",
                "props": {"text": "全新标题", "level": 2},
            }
        ],
    }
    response = _refine(_refinement_client(candidate))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["integrity"]["nonTargetNodesUnchanged"] is True
    assert body["integrity"]["selectedNodeId"] == "hero.title"
    heading = body["document"]["root"]["children"][0]["children"][0]
    assert heading["props"] == {"text": "全新标题", "level": 2}
    # 非目标兄弟节点逐项未变
    sibling = body["document"]["root"]["children"][0]["children"][1]
    assert sibling["props"] == {"text": "正文"}


def test_html_looking_text_patch_is_accepted():
    payload = "<div>Hello</div>"
    candidate = {
        "version": "0.1",
        "operations": [
            {
                "op": "update_props",
                "targetNodeId": "hero.title",
                "props": {"text": payload},
            }
        ],
    }
    response = _refine(_refinement_client(candidate))
    assert response.status_code == 200, response.text
    document = response.json()["document"]
    heading = document["root"]["children"][0]["children"][0]
    assert heading["props"]["text"] == payload


# ============================================================
# 错误响应脱敏（AC-31 / AC-32 / AC-33）
# ============================================================


def _assert_sanitized(text: str):
    lowered = text.lower()
    for leaked in (
        PLACEHOLDER_KEY.lower(),
        "example.invalid",
        "api_key",
        "traceback",
        "/users/",
        "site-packages",
        "genui_api/llm",
        "受控 ui 页面生成器",
        "抗改写",
    ):
        assert leaked not in lowered, f"response leaked: {leaked}"


def test_generation_error_response_is_sanitized(monkeypatch):
    monkeypatch.setenv("GENUI_LLM_API_KEY", PLACEHOLDER_KEY)
    monkeypatch.setenv("GENUI_LLM_BASE_URL", PLACEHOLDER_BASE_URL)
    response = _generate(_generation_client("这不是 JSON"))
    assert response.status_code == 502
    _assert_sanitized(response.text)


def test_generation_validation_error_response_is_sanitized():
    node = {"id": "evil", "type": "script", "props": {}}
    response = _generate(_generation_client(_document(_page([node]))))
    assert response.status_code == 502
    _assert_sanitized(response.text)


def test_refinement_error_response_is_sanitized(monkeypatch):
    monkeypatch.setenv("GENUI_LLM_API_KEY", PLACEHOLDER_KEY)
    response = _refine(_refinement_client("我改好了"))
    assert response.status_code == 502
    _assert_sanitized(response.text)


def test_error_response_does_not_echo_model_output():
    marker = "LEAKY-MODEL-OUTPUT-MARKER"
    response = _generate(_generation_client(f"{marker} not json"))
    assert response.status_code == 502
    assert marker not in response.text


def test_error_response_does_not_echo_prompt():
    marker = "LEAKY-PROMPT-MARKER"
    response = _generate(_generation_client("not json"), prompt=marker)
    assert response.status_code == 502
    assert marker not in response.text


def test_refinement_error_response_does_not_echo_instruction():
    marker = "LEAKY-INSTRUCTION-MARKER"
    response = _refine(_refinement_client("not json"), instruction=marker)
    assert response.status_code == 502
    assert marker not in response.text
