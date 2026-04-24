from __future__ import annotations

import logging
from typing import Any

import requests

from .config import get_settings


logger = logging.getLogger("workstation_vita.api")


class EndpointUnavailableError(RuntimeError):
    pass


def _raise_http_error(response: requests.Response) -> None:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = None

    detail = None
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message")
    if not detail:
        detail = response.text.strip() or f"状态码 {response.status_code}"
    raise RuntimeError(f"服务端返回 {response.status_code}：{detail}")


class MaximoApiClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "Accept-Encoding": "gzip"})
        if self.settings.server_api_token:
            self.session.headers["X-Vita-Token"] = self.settings.server_api_token

    def healthz(self) -> dict[str, Any]:
        response = self.session.get(f"{self.settings.server_api_url}/healthz", timeout=10)
        if not response.ok:
            _raise_http_error(response)
        return response.json()

    def run_statistics(self, entities: dict[str, Any], query_type: str) -> dict[str, Any]:
        response = self.session.post(
            f"{self.settings.server_api_url}/statistics/run",
            json={"entities": entities, "query_type": query_type},
            timeout=60,
        )
        if not response.ok:
            _raise_http_error(response)
        return response.json()

    def run_responsibility(self, entities: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.settings.server_api_url}/responsibility/run",
            json={"entities": entities},
            timeout=60,
        )
        if not response.ok:
            _raise_http_error(response)
        return response.json()

    def run_diagnosis_support(self, user_query: str, entities: dict[str, Any], vector_candidate_ids: list[str], limit: int) -> dict[str, Any]:
        response = self.session.post(
            f"{self.settings.server_api_url}/diagnosis/support",
            json={
                "user_query": user_query,
                "entities": entities,
                "vector_candidate_ids": vector_candidate_ids,
                "limit": limit,
            },
            timeout=120,
        )
        if not response.ok:
            _raise_http_error(response)
        return response.json()

    def run_diagnosis_support_batch(self, user_query: str, layers: list[dict[str, Any]]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.settings.server_api_url}/diagnosis/support-batch",
            json={
                "user_query": user_query,
                "layers": layers,
            },
            timeout=180,
        )
        if response.status_code in {404, 405}:
            raise EndpointUnavailableError("服务端未部署批量诊断接口")
        if not response.ok:
            _raise_http_error(response)
        return response.json()
