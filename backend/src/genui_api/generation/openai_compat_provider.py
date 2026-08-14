"""OpenAI 兼容传输层的初稿生成 Provider（Spec 008 DD-6 / DD-7 / DD-8）。

第一层收敛（生成时结构化约束，RC4 修复）：
response_format 使用由 `DslDocument.model_json_schema()` 派生的完整 Schema
（单一事实来源——不存在手写的第二份结构描述）。模式梯度：

1. `json_schema`（非 strict）：端点已实测接受含 $defs 递归的完整 Schema，
   候选结构在解码期即被约束，且实测保留 style 字段（strict 模式实测会产出
   无 style 的页面，故不启用）。
2. `json_object`：若端点拒绝 json_schema（400），进程内永久降级并记录日志；
   结构约束退化为 SP 文本契约 + Pipeline 校验兜底。

模式判定在首次真实调用时完成并缓存（fail-soft 协商），之后所有请求使用
同一模式，保证行为可预测。
"""
from __future__ import annotations

import logging

from genui_api.contracts.dsl import DslDocument
from genui_api.llm.client import (
    ProviderResponseError,
    create_async_client,
    extract_json_object,
    load_model_config,
    log_llm_call,
)
from genui_api.llm.prompts import build_generation_messages

logger = logging.getLogger("genui.generation")

# 采样与预算常量（DD-19）：写死为模块常量，不外置为环境变量
TEMPERATURE = 0.0
# 复杂页面（多 Section + Form + 卡片网格）的 JSON 输出实测可达数千 token；
# 8000 经真实端点验证可用，为截断导致的半成品 JSON 留出余量。
MAX_TOKENS = 8000

MODE_JSON_SCHEMA = "json_schema"
MODE_JSON_OBJECT = "json_object"

# 进程内结构化输出模式（首次调用时协商，随后固定）
_active_mode: str = MODE_JSON_SCHEMA

# Schema 派生自唯一契约事实来源（DslDocument Pydantic 模型）
_SCHEMA: dict = DslDocument.model_json_schema()


def _response_format(mode: str) -> dict:
    if mode == MODE_JSON_SCHEMA:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "genui_dsl_document",
                "schema": _SCHEMA,
            },
        }
    return {"type": "json_object"}


def _looks_like_format_rejection(exc: Exception) -> bool:
    """判断 400 是否由 response_format/json_schema 不被接受引起。

    只有明确的格式协商失败才触发降级；其余 400（非法模型名、余额等）
    保持原样上报，避免降级掩盖真实配置问题。
    """
    status = getattr(exc, "status_code", None)
    if status != 400:
        return False
    text = str(exc).lower()
    return any(
        token in text
        for token in ("response_format", "json_schema", "json schema", "schema")
    )


def current_response_mode() -> str:
    """当前生效的结构化输出模式（测试与观测用）。"""
    return _active_mode


class OpenAICompatGenerationProvider:
    """基于 OpenAI-compatible Chat Completions 的初稿生成 Provider。

    满足既有 GenerationProvider Protocol（签名不变）。
    「OpenAICompat」指的是传输协议，实际模型可为 Qwen / Kimi / DeepSeek / GLM
    等任一兼容实现。

    返回值是**不可信候选**：不做任何清洗、补字段或类型修正，由 Generation
    Pipeline 的规范化与确定性校验层裁决。
    """

    def __init__(
        self,
        client: object | None = None,
        model: str | None = None,
        temperature: float = TEMPERATURE,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        """client / model 为 None 时在首次调用时惰性经 llm.client 工厂解析。

        构造阶段不读凭证、不建连接，因此可在无凭证环境完成实例化（DD-16）。
        """
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _resolve(self) -> tuple[object, str | None]:
        """惰性解析 client 与模型名，并缓存结果。"""
        if self._client is None or self._model is None:
            config = load_model_config()
            if self._client is None:
                self._client = create_async_client(config)
            if self._model is None:
                self._model = config.generation_model
        return self._client, self._model

    async def generate_draft(self, prompt: str) -> dict:
        """SP/UP 构造 → chat.completions.create → JSON 解析 → 不可信候选 dict。

        SDK 的网络 / 认证 / 限流异常一律转换为固定文案的 ProviderResponseError，
        由 Pipeline 统一映射为 502 provider_error。真实模型不做意图分类，
        不存在 UnrecognizedIntent 分支。
        """
        global _active_mode
        client, model = self._resolve()
        messages = build_generation_messages(prompt)

        mode = _active_mode
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format=_response_format(mode),
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:
            if mode == MODE_JSON_SCHEMA and _looks_like_format_rejection(exc):
                # 端点不接受 json_schema：进程内永久降级并记录（RC4 证据链）
                _active_mode = MODE_JSON_OBJECT
                logger.warning(
                    "event=structured_output_downgrade from=json_schema to=json_object"
                )
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        response_format=_response_format(MODE_JSON_OBJECT),
                        temperature=self._temperature,
                        max_tokens=self._max_tokens,
                    )
                except Exception:
                    raise ProviderResponseError() from None
            else:
                # 净化：不携带 SDK 异常原文 / 凭证 / 端点 / traceback
                raise ProviderResponseError() from None

        log_llm_call(kind="generation", model=model, response=response)

        return extract_json_object(response)
