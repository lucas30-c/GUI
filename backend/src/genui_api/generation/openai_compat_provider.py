"""OpenAI 兼容传输层的初稿生成 Provider（Spec 008 DD-6 / DD-7 / DD-8）。"""
from __future__ import annotations

from genui_api.llm.client import (
    ProviderResponseError,
    create_async_client,
    extract_json_object,
    load_model_config,
    log_llm_call,
)
from genui_api.llm.prompts import build_generation_messages

# 采样与预算常量（DD-19）：写死为模块常量，不外置为环境变量
TEMPERATURE = 0.0
MAX_TOKENS = 4096
RESPONSE_FORMAT = {"type": "json_object"}


class OpenAICompatGenerationProvider:
    """基于 OpenAI-compatible Chat Completions 的初稿生成 Provider。

    满足既有 GenerationProvider Protocol（签名不变）。
    「OpenAICompat」指的是传输协议，实际模型可为 Qwen / Kimi / DeepSeek / GLM
    等任一兼容实现。

    返回值是**不可信候选**：不做任何清洗、补字段或类型修正，由 Generation
    Pipeline 的确定性校验层裁决。
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
        由 Pipeline 统一映射为 502 provider_error；绝不抛 UnrecognizedIntentError
        （真实模型不做意图分类，把模型失败伪装成「意图无法识别」会误导用户）。
        """
        client, model = self._resolve()
        messages = build_generation_messages(prompt)

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format=dict(RESPONSE_FORMAT),
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception:
            # 净化：不携带 SDK 异常原文 / 凭证 / 端点 / traceback
            raise ProviderResponseError() from None

        log_llm_call(kind="generation", model=model, response=response)

        return extract_json_object(response)
