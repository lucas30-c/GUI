"""OpenAI 兼容传输层的局部精修 Provider（Spec 008 DD-6 / DD-9 / DD-10）。"""
from __future__ import annotations

from genui_api.llm.client import (
    ProviderResponseError,
    create_async_client,
    extract_json_object,
    load_model_config,
    log_llm_call,
)
from genui_api.llm.prompts import build_refinement_messages
from genui_api.provider.base import RefinementContext

# 采样与预算常量（DD-19）：精修候选远小于整页文档，预算相应收紧
TEMPERATURE = 0.0
MAX_TOKENS = 1024
RESPONSE_FORMAT = {"type": "json_object"}


class OpenAICompatRefinementProvider:
    """基于 OpenAI-compatible Chat Completions 的局部精修 Provider。

    满足既有 RefinementProvider Protocol（签名不变）。

    只看得到 RefinementContext 提供的 selected-node 最小上下文：不读取、不请求、
    不推断完整文档。对候选中的 targetNodeId 不做任何修正——即使模型写错也原样
    上报，由 Pipeline 的边界检查拒绝（修正会掩盖 prompt 缺陷）。
    """

    def __init__(
        self,
        client: object | None = None,
        model: str | None = None,
        temperature: float = TEMPERATURE,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        """client / model 为 None 时在首次调用时惰性经 llm.client 工厂解析。"""
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
                self._model = config.refinement_model
        return self._client, self._model

    async def generate_patch(self, context: RefinementContext) -> dict:
        """SP/UP 构造 → chat.completions.create → JSON 解析 → 不可信候选 Patch dict。"""
        client, model = self._resolve()
        messages = build_refinement_messages(context)

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

        log_llm_call(kind="refinement", model=model, response=response)

        return extract_json_object(response)
