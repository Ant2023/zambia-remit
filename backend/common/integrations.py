from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings


integration_logger = logging.getLogger("mbongopay.integrations")
MAX_LOG_BODY_CHARS = 2000
SENSITIVE_KEY_PARTS = (
    "app_id",
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
)


class ProviderConfigurationError(ValueError):
    pass


class ProviderRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    code: str
    display_name: str = ""
    base_url: str = ""
    api_key: str = ""
    webhook_secret: str = ""
    timeout_seconds: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def public_metadata(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "display_name": self.display_name or self.code,
            "base_url_configured": bool(self.base_url),
            "api_key_configured": bool(self.api_key),
            "webhook_secret_configured": bool(self.webhook_secret),
            "metadata": redact_sensitive(self.metadata),
        }

    def url_for(self, path: str) -> str:
        if not self.base_url:
            raise ProviderConfigurationError(
                f"{self.code} requires a configured base_url.",
            )
        return urljoin(f"{self.base_url.rstrip('/')}/", path.lstrip("/"))


def redact_sensitive(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key.endswith("_configured"):
                redacted[key] = redact_sensitive(item)
            elif any(part in normalized_key for part in SENSITIVE_KEY_PARTS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted

    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]

    return value


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    redacted_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = key.lower()
        if any(part in normalized_key for part in SENSITIVE_KEY_PARTS):
            redacted_query.append((key, "[redacted]"))
        else:
            redacted_query.append((key, value))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(redacted_query),
            parts.fragment,
        ),
    )


def _trim_body_for_log(body: str) -> str:
    if len(body) <= MAX_LOG_BODY_CHARS:
        return body
    return f"{body[:MAX_LOG_BODY_CHARS]}...[truncated]"


def _env_json(name: str) -> dict[str, Any]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        integration_logger.error(
            "Provider config env var is invalid JSON env_var=%s",
            name,
            extra={"env_var": name},
        )
        return {}
    if not isinstance(parsed, dict):
        integration_logger.error(
            "Provider config env var must be a JSON object env_var=%s",
            name,
            extra={"env_var": name},
        )
        return {}
    return parsed


def get_provider_config(
    setting_name: str,
    code: str,
    *,
    default_display_name: str = "",
    defaults: dict[str, Any] | None = None,
) -> ProviderConfig:
    provider_configs = getattr(settings, setting_name, None)
    if provider_configs is None:
        provider_configs = _env_json(setting_name)

    if not isinstance(provider_configs, dict):
        integration_logger.error(
            "Provider config setting must be a dictionary setting_name=%s",
            setting_name,
            extra={"setting_name": setting_name},
        )
        provider_configs = {}

    raw_config = provider_configs.get(code, {}) or {}
    if not isinstance(raw_config, dict):
        raw_config = {}

    merged = {**(defaults or {}), **raw_config}
    known_fields = {
        "display_name",
        "base_url",
        "api_key",
        "webhook_secret",
        "timeout_seconds",
    }
    metadata = {
        key: value
        for key, value in merged.items()
        if key not in known_fields
    }

    return ProviderConfig(
        code=code,
        display_name=str(merged.get("display_name") or default_display_name or code),
        base_url=str(merged.get("base_url") or "").rstrip("/"),
        api_key=str(merged.get("api_key") or ""),
        webhook_secret=str(merged.get("webhook_secret") or ""),
        timeout_seconds=int(merged.get("timeout_seconds") or 10),
        metadata=metadata,
    )


def request_json(
    *,
    config: ProviderConfig,
    path: str,
    payload: dict[str, Any] | None = None,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    include_api_key_auth: bool = True,
) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    if config.api_key and include_api_key_auth:
        request_headers["Authorization"] = f"Bearer {config.api_key}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    try:
        target_url = config.url_for(path)
    except ProviderConfigurationError:
        integration_logger.error(
            "Provider request missing base URL provider=%s path=%s request_url=",
            config.code,
            path,
            extra={
                "provider": config.code,
                "path": path,
                "request_url": "",
            },
        )
        raise

    request_url = _redact_url(target_url)
    request = Request(
        target_url,
        data=data,
        headers=request_headers,
        method=method.upper(),
    )

    integration_logger.info(
        "Provider request started provider=%s method=%s request_url=%s",
        config.code,
        method.upper(),
        request_url,
        extra={
            "provider": config.code,
            "method": method.upper(),
            "request_url": request_url,
        },
    )

    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
            integration_logger.info(
                "Provider response received provider=%s request_url=%s "
                "response_status=%s response_body=%s",
                config.code,
                request_url,
                getattr(response, "status", ""),
                _trim_body_for_log(response_body),
                extra={
                    "provider": config.code,
                    "request_url": request_url,
                    "response_status": getattr(response, "status", ""),
                    "response_body": _trim_body_for_log(response_body),
                },
            )
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        integration_logger.error(
            "Provider returned HTTP error provider=%s request_url=%s "
            "response_status=%s response_body=%s",
            config.code,
            request_url,
            exc.code,
            _trim_body_for_log(error_body),
            extra={
                "provider": config.code,
                "request_url": request_url,
                "response_status": exc.code,
                "response_body": _trim_body_for_log(error_body),
            },
        )
        raise ProviderRequestError(
            f"{config.code} returned HTTP {exc.code}: {error_body}",
        ) from exc
    except URLError as exc:
        integration_logger.error(
            "Provider request failed provider=%s request_url=%s "
            "response_status= response_body=%s",
            config.code,
            request_url,
            str(exc),
            extra={
                "provider": config.code,
                "request_url": request_url,
                "response_status": "",
                "response_body": str(exc),
            },
        )
        raise ProviderRequestError(f"{config.code} request failed: {exc}") from exc

    if not response_body:
        return {}

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError:
        return {"raw": response_body}

    if isinstance(parsed, dict):
        return parsed

    return {"data": parsed}
