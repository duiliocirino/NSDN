"""LLMProvider ABC and implementations (from MilleniumAI)."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    def invoke(
        self, prompt: str, system_message: str | None = None, temperature: float = 0.7
    ) -> str:
        pass

    @abstractmethod
    def invoke_structured(
        self, prompt: str, schema: Type[T], system_message: str | None = None, temperature: float = 0.0
    ) -> T:
        pass


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "qwen2.5:3b", host: str = "http://localhost:11434"):
        self.model = model
        self.client = None
        try:
            import ollama

            self.client = ollama.Client(host=host)
            self.client.list()
            logger.info("Connected to Ollama at %s, model %s", host, model)
        except Exception as exc:
            logger.warning("Ollama unavailable: %s", exc)

    def invoke(
        self, prompt: str, system_message: str | None = None, temperature: float = 0.7
    ) -> str:
        if not self.client:
            raise RuntimeError("Ollama client not initialized")
        messages: list[dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat(model=self.model, messages=messages, options={"temperature": temperature})
        return resp["message"]["content"]

    def invoke_structured(
        self, prompt: str, schema: Type[T], system_message: str | None = None, temperature: float = 0.0
    ) -> T:
        if not self.client:
            raise RuntimeError("Ollama client not initialized")
        messages: list[dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat(
            model=self.model,
            messages=messages,
            format=schema.model_json_schema(),
            options={"temperature": temperature},
        )
        content = resp.message.content  # type: ignore[union-attr]
        if not content:
            raise ValueError("Ollama returned empty structured content")
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        return schema.model_validate_json(content)


class LlamaCppProvider(LLMProvider):
    def __init__(
        self,
        model_path: str,
        n_ctx: int = 32768,
        n_threads: int | None = None,
        n_gpu_layers: int = 999,
    ):
        self.model_path = model_path
        self.llm = None
        try:
            import llama_cpp

            self.llm = llama_cpp.Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            logger.info("Loaded llama.cpp model: %s", model_path)
        except Exception as exc:
            logger.warning("llama.cpp unavailable: %s", exc)

    def invoke(
        self, prompt: str, system_message: str | None = None, temperature: float = 0.7
    ) -> str:
        if not self.llm:
            raise RuntimeError("llama.cpp model not initialized")
        messages: list = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        resp = self.llm.create_chat_completion(messages=messages, temperature=temperature, stream=False)
        if isinstance(resp, dict):
            if resp and resp["choices"] and resp["choices"][0]["message"]["content"]:
                return resp["choices"][0]["message"]["content"]
        raise RuntimeError("Empty llama.cpp response")

    def invoke_structured(
        self, prompt: str, schema: Type[T], system_message: str | None = None, temperature: float = 0.0
    ) -> T:
        if not self.llm:
            raise RuntimeError("llama.cpp model not initialized")
        messages: list = []
        sys_msg = system_message or "You are a helpful assistant that outputs valid JSON."
        if system_message:
            sys_msg = system_message + "\n\nYou must output raw JSON only."
        messages.append({"role": "system", "content": sys_msg})
        json_prompt = (
            f"{prompt}\n\nRespond with a valid JSON object matching this schema:\n"
            f"{schema.model_json_schema()}\nDo not include markdown code blocks."
        )
        messages.append({"role": "user", "content": json_prompt})
        resp = self.llm.create_chat_completion(messages=messages, temperature=temperature, stream=False)
        if not isinstance(resp, dict):
            raise RuntimeError("Empty llama.cpp structured response")
        if not resp or not resp["choices"]:
            raise RuntimeError("Empty llama.cpp structured response")
        content = resp["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError("Empty llama.cpp structured content")
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        return schema.model_validate_json(content)


class LlamaServerProvider(LLMProvider):
    """Connects to a llama.cpp server via OpenAI-compatible API."""

    def __init__(self, model: str | None = None, base_url: str | None = None):
        self.model = model or os.getenv("LLAMA_SERVER_MODEL", "gemma4-e4b")
        base_url = base_url or os.getenv("LLAMA_SERVER_URL", "http://localhost:8181")
        self.client = None
        try:
            from openai import OpenAI

            self.client = OpenAI(base_url=base_url, api_key="llama-cpp")
            logger.info("Connected to llama-server at %s", base_url)
        except Exception as exc:
            logger.warning("llama-server unavailable: %s", exc)

    def invoke(
        self, prompt: str, system_message: str | None = None, temperature: float = 0.7
    ) -> str:
        if not self.client:
            raise RuntimeError("llama-server client not initialized")
        messages: list = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=False,
        )
        return str(resp.choices[0].message.content)

    def invoke_structured(
        self, prompt: str, schema: Type[T], system_message: str | None = None, temperature: float = 1.0
    ) -> T:
        if not self.client:
            raise RuntimeError("llama-server client not initialized")
        messages: list = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            temperature=temperature,
            top_p=0.95,
            presence_penalty=1.5,
            response_format=schema,
        )
        return resp.choices[0].message.parsed  # type: ignore[union-attr]


def create_provider(config, model_name: str | None = None) -> LLMProvider:
    """Factory: create an LLMProvider from config.

    Args:
        config: Either a ProviderConfig (direct) or LLMConfig (with model lookup).
        model_name: If config is LLMConfig, look up model by name from models dict.
    """
    from nsdn.config import LLMConfig, ProviderConfig

    if isinstance(config, LLMConfig) and model_name:
        cfg = config.get(model_name)
    elif isinstance(config, ProviderConfig):
        cfg = config
    else:
        raise ValueError("Invalid config type for LLM provider")

    provider_type = cfg.provider
    if provider_type == "ollama":
        return OllamaProvider(model=cfg.model, host=cfg.base_url)
    elif provider_type == "llama_cpp":
        return LlamaCppProvider(model_path=cfg.model)
    elif provider_type == "llama_server":
        return LlamaServerProvider(model=cfg.model or None, base_url=cfg.base_url)
    else:
        raise ValueError(f"Unknown LLM provider: {provider_type}")
