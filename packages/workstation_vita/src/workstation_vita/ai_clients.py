from __future__ import annotations

import json
import logging
from typing import Any

import requests

from .config import get_settings


logger = logging.getLogger("workstation_vita.ai")


class AIClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.session = requests.Session()

    def _llm_endpoints(self) -> list[tuple[str, str, str]]:
        endpoints = [(self.settings.llm_url, self.settings.llm_key, self.settings.llm_model)]
        if self.settings.llm_fallback_url:
            endpoints.append((self.settings.llm_fallback_url, self.settings.llm_fallback_key, self.settings.llm_fallback_model))
        return endpoints

    @staticmethod
    def _strip_thinking(text: str) -> str:
        if "</think>" in text:
            return text.split("</think>")[-1].strip()
        return text.strip()

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        cleaned = AIClient._strip_thinking(text)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("模型返回内容中未找到合法的 JSON 对象")
        return json.loads(cleaned[start : end + 1])

    @staticmethod
    def _chat_completions_url(api_url: str) -> str:
        normalized = api_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    def call_llm_text(
        self,
        prompt: str,
        temperature: float = 0.2,
        timeout: int = 90,
        max_completion_tokens: int = 4096,
        enable_thinking: bool = False,
    ) -> str:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": max_completion_tokens,
            "temperature": temperature,
            "top_p": 1,
            "enable_thinking": enable_thinking,
        }
        last_error: Exception | None = None
        for api_url, api_key, model in self._llm_endpoints():
            payload["model"] = model
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            try:
                response = self.session.post(
                    self._chat_completions_url(api_url),
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=timeout,
                )
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return self._strip_thinking(content)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("LLM call failed on %s: %s", api_url, exc)
        raise RuntimeError(f"所有大模型接口均调用失败：{last_error}")

    def call_llm_json(
        self,
        prompt: str,
        temperature: float = 0.0,
        timeout: int = 90,
        max_completion_tokens: int = 1200,
        enable_thinking: bool = False,
    ) -> dict[str, Any]:
        text = self.call_llm_text(
            prompt=prompt,
            temperature=temperature,
            timeout=timeout,
            max_completion_tokens=max_completion_tokens,
            enable_thinking=enable_thinking,
        )
        return self._extract_json_object(text)

    def get_embedding(self, text: str, timeout: int = 30) -> list[float]:
        response = self.session.post(
            self.settings.embedding_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"inputs": text}),
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            return payload[0]
        return payload

    def rerank_results(self, query: str, texts: list[str], top_k: int = 20, timeout: int = 30) -> list[int]:
        if not texts:
            return []
        response = self.session.post(
            self.settings.rerank_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"query": query, "texts": texts, "top_k": min(top_k, len(texts))}),
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict) and "index" in first:
                return [int(item["index"]) for item in payload if "index" in item]
            if isinstance(first, (list, tuple)):
                return [int(item[0]) for item in payload]
        if isinstance(payload, dict) and "results" in payload:
            return [int(item["index"]) for item in payload["results"] if "index" in item]
        return []
