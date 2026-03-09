"""HTTP abstraction with retries and timeouts."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from paper_digest.config import AppSettings
from paper_digest.exceptions import NetworkError

LOGGER = logging.getLogger(__name__)


class HttpClientProtocol(Protocol):
    """Minimal interface needed by source and summarizer modules."""

    def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str: ...

    def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> bytes: ...

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def post_json(
        self,
        url: str,
        *,
        json_body: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]: ...


class ResilientHttpClient:
    """Thin sync HTTP client with retry handling."""

    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._client = httpx.Client(
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        )

    def close(self) -> None:
        self._client.close()

    def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        response = self._request("GET", url, params=params, headers=headers)
        return response.text

    def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> bytes:
        response = self._request("GET", url, params=params, headers=headers)
        return response.content

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request("GET", url, params=params, headers=headers)
        payload = response.json()
        if not isinstance(payload, dict):
            raise NetworkError(f"Expected JSON object from {url}, got {type(payload)!r}.")
        return payload

    def post_json(
        self,
        url: str,
        *,
        json_body: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request("POST", url, json=json_body, headers=headers)
        payload = response.json()
        if not isinstance(payload, dict):
            raise NetworkError(f"Expected JSON object from {url}, got {type(payload)!r}.")
        return payload

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        max_retries = max(1, self._settings.http_max_retries)
        backoff = max(0.1, self._settings.http_retry_backoff_seconds)
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
                last_error = error
                status = getattr(getattr(error, "response", None), "status_code", None)
                is_retryable_status = status is None or status >= 500 or status == 429
                if attempt >= max_retries or not is_retryable_status:
                    message = f"{method} {url} failed after {attempt} attempt(s): {error}"
                    raise NetworkError(message) from error
                sleep_seconds = backoff * (2 ** (attempt - 1))
                LOGGER.warning(
                    "Retrying %s %s after attempt %s/%s due to %s",
                    method,
                    url,
                    attempt,
                    max_retries,
                    error,
                )
                time.sleep(sleep_seconds)

        raise NetworkError(f"{method} {url} failed: {last_error}")
