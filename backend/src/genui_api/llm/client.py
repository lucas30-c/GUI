"""模型客户端工厂与配置读取（Spec 008 DD-4 / DD-13 / DD-19）。

本模块是**唯一**读取模型相关环境变量的地方；Provider 只从工厂拿到已构造好的
client，不直接接触凭证。「OpenAICompat」指传输协议（OpenAI-compatible Chat
Completions），与模型来自哪家厂商无关。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from openai import AsyncOpenAI

logger = logging.getLogger("genui.llm")

# 生产链路唯一的 Provider 传输模式（描述协议形态，不是厂商名）。
# Real-Provider-only（Owner 决策）：mock 不是运行时模式——测试替身只能位于
# 测试范围内，通过 create_app(dependency_overrides) 显式注入，不经由此配置。
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
ALLOWED_PROVIDERS = (PROVIDER_OPENAI_COMPATIBLE,)

# 环境变量名（Provider-neutral，不绑定任何厂商）
ENV_PROVIDER = "GENUI_MODEL_PROVIDER"
ENV_API_KEY = "GENUI_LLM_API_KEY"
ENV_BASE_URL = "GENUI_LLM_BASE_URL"
ENV_GENERATION_MODEL = "GENUI_GENERATION_MODEL"
ENV_REFINEMENT_MODEL = "GENUI_REFINEMENT_MODEL"

# 采样与传输常量（DD-19）：写死为模块常量，不外置为环境变量
# P0 修复：增加超时到 120 秒，支持复杂页面生成（bounded retry 最多 2 次，总时间可达 360 秒）
DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 0

# 固定净化文案（DD-12）：不插值异常原文 / 凭证 / 端点 / 路径 / prompt / 模型输出
PROVIDER_RESPONSE_ERROR_MESSAGE = "Model provider returned an unusable response"


class ProviderConfigError(RuntimeError):
    """模型 Provider 配置非法（未知模式、缺失凭证/端点/模型名）。

    消息只列出「缺哪一项」与允许值，绝不包含任何凭证片段。
    继承 RuntimeError 以便调用方按运行期配置错误捕获。
    """


class ProviderResponseError(RuntimeError):
    """模型调用或响应不可用（网络、超时、空内容、非 JSON、SDK 异常）。

    消息为固定净化文案，不插值任何上下文。
    """

    def __init__(self, message: str = PROVIDER_RESPONSE_ERROR_MESSAGE) -> None:
        super().__init__(message)


@dataclass(frozen=True)
class ModelConfig:
    """模型配置快照（Real-Provider-only：provider 恒为 openai_compatible）。"""

    provider: str
    api_key: str | None = None
    base_url: str | None = None
    generation_model: str | None = None
    refinement_model: str | None = None


def _read(name: str) -> str | None:
    """读取环境变量并 strip；缺失或纯空白视为未设置。"""
    raw = os.environ.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def load_model_config() -> ModelConfig:
    """从环境变量读取并校验模型配置；非法时抛 ProviderConfigError。

    这是唯一读取 GENUI_MODEL_PROVIDER / GENUI_LLM_* / GENUI_*_MODEL 的函数（AC-05）。

    Real-Provider-only：生产链路只接受 GENUI_MODEL_PROVIDER=openai_compatible。
    未设置或设置为 mock 都会 fail fast——Mock 从 M4-05 起不再是运行时模式，
    测试替身只能经 create_app 显式注入（不经过本配置）。
    """
    raw_provider = os.environ.get(ENV_PROVIDER, "")
    provider = raw_provider.strip().lower()

    if provider != PROVIDER_OPENAI_COMPATIBLE:
        raise ProviderConfigError(
            f"{ENV_PROVIDER} must be '{PROVIDER_OPENAI_COMPATIBLE}' "
            f"(got {raw_provider!r} or unset). Real-Provider-only: Mock 不再是运行时模式，"
            f"测试替身请通过 create_app 显式注入。"
        )

    api_key = _read(ENV_API_KEY)
    base_url = _read(ENV_BASE_URL)
    generation_model = _read(ENV_GENERATION_MODEL)

    missing = [
        name
        for name, value in (
            (ENV_API_KEY, api_key),
            (ENV_BASE_URL, base_url),
            (ENV_GENERATION_MODEL, generation_model),
        )
        if value is None
    ]
    if missing:
        raise ProviderConfigError(
            "Missing required configuration for "
            f"{ENV_PROVIDER}={PROVIDER_OPENAI_COMPATIBLE}: {', '.join(missing)}"
        )

    # 精修侧模型未设置时继承生成侧
    refinement_model = _read(ENV_REFINEMENT_MODEL) or generation_model

    return ModelConfig(
        provider=PROVIDER_OPENAI_COMPATIBLE,
        api_key=api_key,
        base_url=base_url,
        generation_model=generation_model,
        refinement_model=refinement_model,
    )


def create_openai_client(
    api_key: str,
    base_url: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> AsyncOpenAI:
    """纯工厂函数：由参数构造 AsyncOpenAI，不读取任何环境变量。

    max_retries=0 使「fail fast」成为真实行为而非纸面承诺（DD-13）。
    """
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=DEFAULT_MAX_RETRIES,
    )


def create_async_client(config: ModelConfig | None = None) -> AsyncOpenAI:
    """按配置构造 AsyncOpenAI；config 为 None 时先 load_model_config()。

    config.provider 不是 openai_compatible 时抛 ProviderConfigError，
    防止 mock 模式下被误调用而实例化 SDK。
    """
    resolved = config if config is not None else load_model_config()

    if resolved.provider != PROVIDER_OPENAI_COMPATIBLE:
        raise ProviderConfigError(
            f"create_async_client requires {ENV_PROVIDER}={PROVIDER_OPENAI_COMPATIBLE}, "
            f"current mode is {resolved.provider}"
        )

    if not resolved.api_key or not resolved.base_url:
        raise ProviderConfigError(
            "Missing required configuration for "
            f"{ENV_PROVIDER}={PROVIDER_OPENAI_COMPATIBLE}: "
            f"{ENV_API_KEY}, {ENV_BASE_URL}"
        )

    return create_openai_client(api_key=resolved.api_key, base_url=resolved.base_url)


def extract_json_object(response: object) -> dict:
    """从 Chat Completions 响应中提取 message.content 并解析为 JSON 对象。

    任何不可用形态（choices 为空 / content 缺失或空白 / 非 JSON / 顶层非对象）
    一律抛 ProviderResponseError（固定净化文案）。

    不实现「剥离 markdown 代码围栏」的容错逻辑：JSON Mode 下不应出现围栏，
    出现即视为该模型不合格（DD-11）。返回值不做任何清洗、补字段或类型修正——
    原样交给 Pipeline 的确定性校验层。
    """
    choices = getattr(response, "choices", None)
    if not choices:
        raise ProviderResponseError()

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError()

    try:
        candidate = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        raise ProviderResponseError() from None

    if not isinstance(candidate, dict):
        raise ProviderResponseError()

    return candidate


def log_provider_summary(config: ModelConfig) -> None:
    """以 INFO 记录一行 Provider 摘要：只含模式与模型名，绝不含 Key / base_url。"""
    logger.info(
        "provider_config provider=%s generation_model=%s refinement_model=%s",
        config.provider,
        config.generation_model,
        config.refinement_model,
    )


def log_llm_call(
    kind: str,
    model: str | None,
    response: object,
) -> None:
    """记录一次真实调用的安全摘要（DD-15）。

    usage 字段缺失或跨厂商形态不一致时记 None 并继续；本函数自身的任何异常
    都被吞掉，绝不影响业务结果。不记录 Key / base_url / prompt / 模型输出。
    """
    try:
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        if not isinstance(prompt_tokens, int):
            prompt_tokens = None
        if not isinstance(completion_tokens, int):
            completion_tokens = None
        logger.info(
            "event=llm_call provider=%s kind=%s model=%s "
            "prompt_tokens=%s completion_tokens=%s",
            PROVIDER_OPENAI_COMPATIBLE,
            kind,
            model,
            prompt_tokens,
            completion_tokens,
        )
    except Exception:  # pragma: no cover - 日志永不影响主流程
        pass
