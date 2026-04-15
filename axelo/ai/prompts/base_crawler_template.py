"""
Generated crawler - Axelo JSReverse (Deterministic bridge mode)
This file is rendered from axelo/ai/prompts/base_crawler_template.py.
"""

from __future__ import annotations

import abc
import json
import logging
import os
import subprocess
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

# G1.1: 添加logger初始化 - 修复 "name 'log' is not defined" 错误
# 在生成的爬虫脚本中初始化logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=__import__('sys').stdout
)
logger = logging.getLogger(__name__)

# 兼容旧代码中的log引用
log = logger

from axelo.browser.bridge_client import BridgeDriver

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover - optional dependency
    curl_requests = None


TransportBackend = Literal["httpx", "curl_cffi"]
ChallengePolicy = Literal["fail_fast", "pause_and_report", "wait_for_test_bypass_token"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _impersonate_from_ua(ua: str) -> str:
    """Select a curl_cffi impersonate target that matches the given User-Agent.

    Ensures TLS fingerprint (JA3) and UA string are coherent — a Chrome 124 UA
    should use the Chrome 124 TLS handshake, not a fixed global default.
    No site-specific logic; purely pattern-based on the UA string.
    """
    if not ua:
        return "chrome124"
    ua_lower = ua.lower()
    if "firefox/" in ua_lower:
        return "firefox121"
    if "safari/" in ua_lower and "chrome" not in ua_lower:
        return "safari17_0"
    if "chrome/124" in ua_lower:
        return "chrome124"
    if "chrome/123" in ua_lower or "chrome/122" in ua_lower:
        return "chrome120"
    if "chrome/120" in ua_lower or "chrome/121" in ua_lower:
        return "chrome120"
    return "chrome124"


def _inject_sec_ch_ua_headers(headers: dict[str, str], user_agent: str) -> None:
    """Fill missing sec-ch-ua* headers derived from the User-Agent string.

    A sec-ch-ua header inconsistent with the UA is a reliable automation signal.
    This fills only absent headers — never overwrites values already set by the caller.
    """
    import re as _re
    lowered_keys = {k.lower() for k in headers}
    if not any(k.startswith("sec-ch-ua") for k in lowered_keys):
        m = _re.search(r"Chrome/(\d+)", user_agent)
        if m:
            major = m.group(1)
            headers["sec-ch-ua"] = f'"Chromium";v="{major}", "Google Chrome";v="{major}", "Not-A.Brand";v="99"'
    if "sec-ch-ua-mobile" not in lowered_keys:
        is_mobile = any(x in user_agent.lower() for x in ("android", "iphone", "ipad", "mobile"))
        headers["sec-ch-ua-mobile"] = "?1" if is_mobile else "?0"
    if "sec-ch-ua-platform" not in lowered_keys:
        ua_lower = user_agent.lower()
        if "win" in ua_lower:
            platform = "Windows"
        elif "mac os x" in ua_lower or "macintosh" in ua_lower:
            platform = "macOS"
        elif "android" in ua_lower:
            platform = "Android"
        elif "linux" in ua_lower:
            platform = "Linux"
        else:
            platform = "Windows"
        headers["sec-ch-ua-platform"] = f'"{platform}"'


def _deep_merge_dicts(base: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    merged = json.loads(json.dumps(base))
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_http_version(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    text = str(value)
    return text or None


def _extract_response_cookies(response: Any) -> dict[str, str]:
    cookies = getattr(response, "cookies", None)
    if cookies is None:
        return {}
    try:
        return {str(key): str(value) for key, value in cookies.items()}
    except Exception:
        return {}


def _extract_protocol_details(response: Any) -> dict[str, Any]:
    details: dict[str, Any] = {
        "httpVersion": _normalize_http_version(getattr(response, "http_version", None)),
        "tlsVersion": None,
        "alpnProtocol": None,
        "cipherSuite": None,
        "connectionReused": None,
        "negotiationSource": "unknown",
    }

    extensions = getattr(response, "extensions", None) or {}
    if "http_version" in extensions and details["httpVersion"] is None:
        details["httpVersion"] = _normalize_http_version(extensions.get("http_version"))

    network_stream = extensions.get("network_stream")
    ssl_object = None
    if network_stream is not None and hasattr(network_stream, "get_extra_info"):
        try:
            ssl_object = network_stream.get_extra_info("ssl_object")
            details["alpnProtocol"] = network_stream.get_extra_info("alpn_protocol")
            details["cipherSuite"] = network_stream.get_extra_info("cipher")
            details["negotiationSource"] = "httpx.network_stream"
        except Exception:
            ssl_object = None
    if ssl_object is not None:
        try:
            details["tlsVersion"] = ssl_object.version()
        except Exception:
            details["tlsVersion"] = None

    infos = getattr(response, "infos", None)
    if isinstance(infos, dict):
        details["negotiationSource"] = "curl_cffi.infos"
        for key, value in infos.items():
            key_text = str(key).lower()
            if details["httpVersion"] is None and "http_version" in key_text:
                details["httpVersion"] = _normalize_http_version(value)
            elif details["tlsVersion"] is None and ("ssl_version" in key_text or "tls_version" in key_text):
                details["tlsVersion"] = _normalize_http_version(value)
            elif details["alpnProtocol"] is None and "alpn" in key_text:
                details["alpnProtocol"] = _normalize_http_version(value)
            elif details["connectionReused"] is None and "reused" in key_text:
                details["connectionReused"] = bool(value)

    return details


@dataclass
class TransportExecution:
    response: Any
    telemetry: dict[str, Any]


class TransportAdapter(abc.ABC):
    def __init__(self, profile: dict[str, Any] | None = None) -> None:
        self.profile = dict(profile or {})

    @property
    @abc.abstractmethod
    def backend(self) -> TransportBackend:
        raise NotImplementedError

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> TransportExecution:
        started_at = _utc_now_iso()
        started = time.perf_counter()
        retries = max(0, int(self.profile.get("retries", 0)))
        retry_statuses = {int(item) for item in self.profile.get("retry_statuses", []) if str(item).isdigit()}
        follow_redirects = bool(self.profile.get("follow_redirects", True))
        verify = self.profile.get("verify", True)
        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None

        for attempt in range(1, retries + 2):
            attempt_started = time.perf_counter()
            try:
                response = self._single_request(
                    method=method,
                    url=url,
                    headers=headers,
                    body=body,
                    timeout=timeout,
                    follow_redirects=follow_redirects,
                    verify=verify,
                )
                duration_ms = round((time.perf_counter() - attempt_started) * 1000, 2)
                protocol = _extract_protocol_details(response)
                attempts.append(
                    {
                        "attempt": attempt,
                        "durationMs": duration_ms,
                        "statusCode": getattr(response, "status_code", None),
                        "httpVersion": protocol.get("httpVersion"),
                    }
                )
                if getattr(response, "status_code", 0) in retry_statuses and attempt <= retries:
                    continue
                telemetry = {
                    "backend": self.backend,
                    "startedAt": started_at,
                    "finishedAt": _utc_now_iso(),
                    "durationMs": round((time.perf_counter() - started) * 1000, 2),
                    "attemptCount": attempt,
                    "retries": attempt - 1,
                    "attempts": attempts,
                    "protocol": protocol,
                    "profile": dict(self.profile),
                    "statusCode": getattr(response, "status_code", None),
                    "redirectCount": len(getattr(response, "history", []) or []),
                    "error": None,
                }
                return TransportExecution(response=response, telemetry=telemetry)
            except Exception as exc:
                last_error = exc
                duration_ms = round((time.perf_counter() - attempt_started) * 1000, 2)
                error_text = str(exc)
                attempts.append(
                    {
                        "attempt": attempt,
                        "durationMs": duration_ms,
                        "statusCode": None,
                        "errorType": exc.__class__.__name__,
                        "error": error_text,
                        "handshakeFailure": "ssl" in error_text.lower() or "tls" in error_text.lower(),
                    }
                )
                if attempt > retries:
                    break

        telemetry = {
            "backend": self.backend,
            "startedAt": started_at,
            "finishedAt": _utc_now_iso(),
            "durationMs": round((time.perf_counter() - started) * 1000, 2),
            "attemptCount": len(attempts),
            "retries": max(0, len(attempts) - 1),
            "attempts": attempts,
            "protocol": {
                "httpVersion": None,
                "tlsVersion": None,
                "alpnProtocol": None,
                "cipherSuite": None,
                "connectionReused": None,
                "negotiationSource": "error",
            },
            "profile": dict(self.profile),
            "statusCode": None,
            "redirectCount": 0,
            "error": {
                "type": last_error.__class__.__name__ if last_error else "RuntimeError",
                "message": str(last_error or "transport failed"),
            },
        }
        raise RuntimeError(json.dumps(telemetry, ensure_ascii=False))

    @abc.abstractmethod
    def _single_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
        follow_redirects: bool,
        verify: Any,
    ) -> Any:
        raise NotImplementedError


class HttpxTransportAdapter(TransportAdapter):
    @property
    def backend(self) -> TransportBackend:
        return "httpx"

    def _single_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
        follow_redirects: bool,
        verify: Any,
    ) -> httpx.Response:
        client_kwargs: dict[str, Any] = {
            "http2": bool(self.profile.get("http2", False)),
            "verify": verify,
            "timeout": timeout,
        }
        limits = self.profile.get("limits")
        if isinstance(limits, dict):
            client_kwargs["limits"] = httpx.Limits(
                max_connections=limits.get("max_connections"),
                max_keepalive_connections=limits.get("max_keepalive_connections"),
                keepalive_expiry=limits.get("keepalive_expiry"),
            )
        with httpx.Client(**client_kwargs) as client:
            return client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
                follow_redirects=follow_redirects,
            )


class CurlCffiTransportAdapter(TransportAdapter):
    @property
    def backend(self) -> TransportBackend:
        return "curl_cffi"

    def _single_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
        follow_redirects: bool,
        verify: Any,
    ) -> Any:
        if curl_requests is None:
            raise RuntimeError("curl_cffi transport backend is unavailable; install curl_cffi to enable it")

        session = curl_requests.Session()
        # Derive impersonate from the User-Agent header for TLS+UA coherence.
        # Falls back to the profile default if no UA is present.
        ua = headers.get("user-agent") or headers.get("User-Agent") or ""
        impersonate = self.profile.get("impersonate") or _impersonate_from_ua(ua)
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "data": body,
            "timeout": timeout,
            "allow_redirects": follow_redirects,
            "verify": verify,
            "impersonate": impersonate,
        }
        http_version = self.profile.get("http_version")
        if http_version is not None:
            request_kwargs["http_version"] = http_version
        if "curl_options" in self.profile:
            request_kwargs["curl_options"] = dict(self.profile["curl_options"])
        try:
            return session.request(**request_kwargs)
        finally:
            close = getattr(session, "close", None)
            if callable(close):
                close()


class __AXELO_CRAWLER_CLASS__:
    BRIDGE_PORT = __AXELO_BRIDGE_PORT__
    BRIDGE_PATH = "bridge_server.js"
    DEFAULT_NODE_BIN = __AXELO_NODE_BIN__

    PAGE_ORIGIN = __AXELO_PAGE_ORIGIN__
    START_URL = __AXELO_START_URL__
    KNOWN_ENDPOINT = __AXELO_KNOWN_ENDPOINT__
    API_BASE = __AXELO_PREFERRED_API_BASE__
    BRIDGE_LOCALE = __AXELO_BRIDGE_LOCALE__
    BRIDGE_TIMEZONE = __AXELO_BRIDGE_TIMEZONE__
    DEFAULT_STORAGE_STATE_PATH = __AXELO_STORAGE_STATE_PATH__
    DEFAULT_ENVIRONMENT = __AXELO_DEFAULT_ENVIRONMENT__
    DEFAULT_INTERACTION = __AXELO_DEFAULT_INTERACTION__
    DEFAULT_WASM_TELEMETRY = {
        "enabled": True,
        "snapshotMode": "full",
        "overloadPolicy": "preserve_realism",
        "maxFullSnapshotBytes": 2097152,
        "sliceBytes": 4096,
        "persistRawBinary": True,
        "artifactDir": "wasm_artifacts",
    }
    DEFAULT_SESSION_PROFILE = {'profileName': 'desktop_consistent',
 'locale': __AXELO_BRIDGE_LOCALE__,
 'timezoneId': __AXELO_BRIDGE_TIMEZONE__,
 'userAgent': '',
 'viewport': {'width': 1366, 'height': 768},
 'deviceClass': 'desktop',
 'colorScheme': 'light',
 'reducedMotion': 'no-preference',
 'deviceScaleFactor': 1.0,
 'hasTouch': False,
 'isMobile': False,
 'deviceMemory': 8,
 'hardwareConcurrency': 8,
 'maxTouchPoints': 0,
 'battery': {'enabled': True,
             'charging': True,
             'chargingTime': 0.0,
             'dischargingTime': None,
             'level': 1.0},
 'connection': {'effectiveType': '4g', 'rtt': 50, 'downlink': 10.0, 'saveData': False},
 'webgl': {'enabled': True,
           'minimumParameters': {'ALIASED_LINE_WIDTH_RANGE': [1, 1],
                                 'ALIASED_POINT_SIZE_RANGE': [1, 1],
                                 'MAX_COMBINED_TEXTURE_IMAGE_UNITS': 8,
                                 'MAX_CUBE_MAP_TEXTURE_SIZE': 1024,
                                 'MAX_FRAGMENT_UNIFORM_VECTORS': 16,
                                 'MAX_RENDERBUFFER_SIZE': 1024,
                                 'MAX_TEXTURE_IMAGE_UNITS': 8,
                                 'MAX_TEXTURE_SIZE': 2048,
                                 'MAX_VARYING_VECTORS': 8,
                                 'MAX_VERTEX_ATTRIBS': 8,
                                 'MAX_VERTEX_TEXTURE_IMAGE_UNITS': 0,
                                 'MAX_VERTEX_UNIFORM_VECTORS': 128}},
 'geolocation': None,
 'geoPolicy': {'mode': 'consistency_check_only',
               'expectedTimezoneId': __AXELO_BRIDGE_TIMEZONE__,
               'warnOnMismatch': True},
 'automationLabel': {'enabled': False,
                     'automationMode': False,
                     'headerName': 'x-axelo-automation',
                     'headerValue': 'authorized-test',
                     'cookieName': 'axelo_automation',
                     'cookieValue': 'authorized-test',
                     'queryName': 'axeloAutomation',
                     'queryValue': 'true'}}
    DEFAULT_INTERACTION_ENGINE = {'enabled': True,
 'profileName': 'synthetic_performance',
 'mode': 'playwright_mouse',
 'highFrequencyDispatch': False,
 'defaultSeed': None,
 'pointer': {'defaultSeed': None,
             'sampleRateHz': 60,
             'durationMs': 1200,
             'jitterPx': 1.25,
             'curvature': 0.18,
             'hoverPauseMs': 0},
 'scroll': {'enabled': True, 'jitterPx': 18, 'stepDelayMs': 24},
 'click': {'enabled': True, 'baseDelayMs': 100, 'jitterMs': 55}}
    BRIDGE_TARGETS = __AXELO_BRIDGE_TARGETS__
    PREFERRED_BRIDGE_TARGET = __AXELO_PREFERRED_BRIDGE_TARGET__

    DEFAULT_HEADERS = __AXELO_DEFAULT_HEADERS__
    OBSERVED_TARGETS = __AXELO_OBSERVED_TARGETS__

    def __init__(
        self,
        bridge: bool = True,
        cookies: dict[str, str] | None = None,
        bridge_headless: bool = True,
        bridge_signers: list[dict[str, Any]] | None = None,
        storage_state_path: str | None = None,
        bridge_environment: dict[str, Any] | None = None,
        bridge_interaction: dict[str, Any] | None = None,
        wasm_telemetry: dict[str, Any] | None = None,
        session_profile: dict[str, Any] | None = None,
        interaction_engine: dict[str, Any] | None = None,
        transport_backend: TransportBackend = "curl_cffi",
        transport_profile: dict[str, Any] | None = None,
        challenge_policy: ChallengePolicy = "fail_fast",
        telemetry_sink: str | None = None,
    ) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._cookies: dict[str, str] = dict(cookies or {})
        self._last_headers: dict[str, str] = {}
        self._last_request_url: str = ""
        self._bridge_event_cursor = 0
        self._session_id = uuid.uuid4().hex
        self._runtime_seed = int.from_bytes(os.urandom(4), "big") or 1
        self._bridge_headless = bridge_headless
        self._bridge_signers = bridge_signers or list(self.BRIDGE_TARGETS or [])
        self._transport_backend: TransportBackend = transport_backend
        self._transport_profile = dict(transport_profile or {})
        self._challenge_policy: ChallengePolicy = challenge_policy
        self._telemetry_sink = Path(telemetry_sink).expanduser() if telemetry_sink else None
        self._telemetry_records: list[dict[str, Any]] = []
        self._session_profile = self._build_session_profile(session_profile, bridge_environment)
        if not self._session_profile.get("userAgent"):
            self._session_profile["userAgent"] = (
                self.DEFAULT_HEADERS.get("User-Agent")
                or self.DEFAULT_HEADERS.get("user-agent")
                or ""
            )
        self._interaction_engine = self._build_interaction_engine(interaction_engine, bridge_interaction)
        if not self._interaction_engine.get("defaultSeed"):
            self._interaction_engine["defaultSeed"] = self._runtime_seed
        if isinstance(self._interaction_engine.get("pointer"), dict) and not self._interaction_engine["pointer"].get("defaultSeed"):
            self._interaction_engine["pointer"]["defaultSeed"] = self._runtime_seed
        self._bridge_wasm_telemetry = _deep_merge_dicts(dict(self.DEFAULT_WASM_TELEMETRY or {}), dict(wasm_telemetry or {}))
        self._bridge_environment = self._build_environment_simulation(self._session_profile)
        self._bridge_interaction = self._build_interaction_simulation(self._interaction_engine)
        self._bridge_base_url = f"http://127.0.0.1:{self.BRIDGE_PORT}"
        self._bridge_driver = BridgeDriver(self._bridge_base_url)
        self._file_dir = Path(__file__).resolve().parent
        self._session_dir = self._file_dir.parent
        self._repo_root = self._find_repo_root()
        self._transport = self._create_transport_adapter()

        default_storage_state = self.DEFAULT_STORAGE_STATE_PATH or str(self._session_dir / "browser_storage_state.json")
        self._storage_state_path = Path(storage_state_path or default_storage_state)
        self._bootstrap_cookies_from_storage_state()
        self._emit_telemetry(
            "session_started",
            {
                "transportBackend": self._transport_backend,
                "transportProfile": self._transport_profile,
                "challengePolicy": self._challenge_policy,
                "sessionProfile": self._session_profile,
                "interactionEngine": self._interaction_engine,
                "automationMode": bool((self._session_profile.get("automationLabel") or {}).get("automationMode")),
            },
        )

        if bridge:
            self._start_bridge()
            self._bridge_init()
            self._bridge_register_targets()
            if self._cookies:
                self._bridge_set_cookies(self._cookies)

    def _find_repo_root(self) -> Path:
        cursor = Path(__file__).resolve().parent
        for candidate in [cursor, *cursor.parents]:
            if (candidate / "axelo").exists() and (candidate / "workspace").exists():
                return candidate
        return cursor

    def _create_transport_adapter(self) -> TransportAdapter:
        if self._transport_backend == "httpx":
            return HttpxTransportAdapter(self._transport_profile)
        if self._transport_backend == "curl_cffi":
            return CurlCffiTransportAdapter(self._transport_profile)
        raise ValueError(f"Unsupported transport backend: {self._transport_backend}")

    def _build_session_profile(
        self,
        session_profile: dict[str, Any] | None,
        bridge_environment: dict[str, Any] | None,
    ) -> dict[str, Any]:
        environment_defaults = dict(bridge_environment or self.DEFAULT_ENVIRONMENT or {})
        default_profile = _deep_merge_dicts(
            dict(self.DEFAULT_SESSION_PROFILE or {}),
            {
                "locale": self.BRIDGE_LOCALE,
                "timezoneId": self.BRIDGE_TIMEZONE,
                "colorScheme": environment_defaults.get("colorScheme", "light"),
                "reducedMotion": environment_defaults.get("reducedMotion", "no-preference"),
                "deviceScaleFactor": environment_defaults.get("deviceScaleFactor", 1.0),
                "hasTouch": environment_defaults.get("hasTouch", False),
                "isMobile": environment_defaults.get("isMobile", False),
                "battery": environment_defaults.get("battery", {}),
                "deviceMemory": environment_defaults.get("media", {}).get("deviceMemory", 8),
                "hardwareConcurrency": environment_defaults.get("media", {}).get("hardwareConcurrency", 8),
                "maxTouchPoints": environment_defaults.get("media", {}).get("maxTouchPoints", 0),
                "connection": environment_defaults.get("media", {}).get("connection", {}),
                "webgl": environment_defaults.get("webgl", {}),
            },
        )
        return _deep_merge_dicts(default_profile, session_profile)

    def _build_interaction_engine(
        self,
        interaction_engine: dict[str, Any] | None,
        bridge_interaction: dict[str, Any] | None,
    ) -> dict[str, Any]:
        default_engine = _deep_merge_dicts(
            dict(self.DEFAULT_INTERACTION_ENGINE or {}),
            dict(bridge_interaction or self.DEFAULT_INTERACTION or {}),
        )
        return _deep_merge_dicts(default_engine, interaction_engine)

    def _build_environment_simulation(self, session_profile: dict[str, Any]) -> dict[str, Any]:
        connection = dict(session_profile.get("connection") or {})
        return {
            "enabled": True,
            "profileName": session_profile.get("profileName") or "session_profile",
            "colorScheme": session_profile.get("colorScheme"),
            "reducedMotion": session_profile.get("reducedMotion"),
            "deviceScaleFactor": session_profile.get("deviceScaleFactor"),
            "hasTouch": session_profile.get("hasTouch"),
            "isMobile": session_profile.get("isMobile"),
            "battery": dict(session_profile.get("battery") or {}),
            "media": {
                "enabled": True,
                "pointer": "coarse" if session_profile.get("hasTouch") else "fine",
                "hover": "none" if session_profile.get("hasTouch") else "hover",
                "anyPointer": "coarse" if session_profile.get("hasTouch") else "fine",
                "anyHover": "none" if session_profile.get("hasTouch") else "hover",
                "hardwareConcurrency": session_profile.get("hardwareConcurrency"),
                "deviceMemory": session_profile.get("deviceMemory"),
                "maxTouchPoints": session_profile.get("maxTouchPoints"),
                "connection": connection,
            },
            "webgl": dict(session_profile.get("webgl") or {}),
        }

    def _build_interaction_simulation(self, interaction_engine: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": bool(interaction_engine.get("enabled", True)),
            "profileName": interaction_engine.get("profileName"),
            "mode": interaction_engine.get("mode", "playwright_mouse"),
            "highFrequencyDispatch": bool(interaction_engine.get("highFrequencyDispatch", False)),
            "pointer": dict(interaction_engine.get("pointer") or {}),
        }

    def _emit_telemetry(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "eventType": event_type,
            "ts": _utc_now_iso(),
            "sessionId": self._session_id,
            "automationMode": bool((self._session_profile.get("automationLabel") or {}).get("automationMode")),
            "payload": payload,
        }
        self._telemetry_records.append(record)
        if self._telemetry_sink:
            self._telemetry_sink.parent.mkdir(parents=True, exist_ok=True)
            with self._telemetry_sink.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")
        return record

    def telemetry_snapshot(self) -> dict[str, Any]:
        return {
            "sessionId": self._session_id,
            "transportBackend": self._transport_backend,
            "transportProfile": dict(self._transport_profile),
            "challengePolicy": self._challenge_policy,
            "sessionProfile": self._session_profile,
            "interactionEngine": self._interaction_engine,
            "records": list(self._telemetry_records),
        }

    def _node_path(self) -> str:
        candidates = [
            self._repo_root / "node_modules",
            self._repo_root / "axelo" / "js_tools" / "scripts" / "node_modules",
        ]
        existing = os.environ.get("NODE_PATH", "")
        parts = [str(path) for path in candidates if path.exists()]
        if existing:
            parts.append(existing)
        return os.pathsep.join(parts)

    def _resolve_node_bin(self) -> str:
        configured = os.environ.get("AXELO_NODE_BIN") or self.DEFAULT_NODE_BIN
        return str(configured or "node")

    def _start_bridge(self) -> None:
        env = os.environ.copy()
        node_path = self._node_path()
        if node_path:
            env["NODE_PATH"] = node_path

        self._proc = subprocess.Popen(
            [self._resolve_node_bin(), self.BRIDGE_PATH],
            cwd=str(self._file_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        deadline = time.time() + 20.0
        last_error = "bridge did not start"
        while time.time() < deadline:
            try:
                health = self._bridge_health()
                if health:
                    return
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.5)
        raise RuntimeError(f"Bridge health check failed: {last_error}")

    def _bridge_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        return self._bridge_driver.request(method, path, payload, timeout=timeout)

    def _bridge_health(self) -> dict[str, Any]:
        return self._bridge_request("GET", "/health", timeout=5.0)

    def _bridge_events(self) -> list[dict[str, Any]]:
        data = self._bridge_request("GET", f"/events?since={self._bridge_event_cursor}", timeout=5.0)
        events = data.get("events", [])
        self._bridge_event_cursor = int(data.get("nextCursor", self._bridge_event_cursor))
        return events

    def _bridge_init(self) -> dict[str, Any]:
        payload = {
            "startUrl": self.START_URL or self.PAGE_ORIGIN,
            "storageStatePath": str(self._storage_state_path) if self._storage_state_path.exists() else "",
            "headless": self._bridge_headless,
            "locale": self._session_profile.get("locale", self.BRIDGE_LOCALE),
            "timezoneId": self._session_profile.get("timezoneId", self.BRIDGE_TIMEZONE),
            "viewport": dict(self._session_profile.get("viewport") or {}),
            "defaultSigner": (
                self.PREFERRED_BRIDGE_TARGET
                or (self._bridge_signers[0]["name"] if self._bridge_signers else "")
            ),
            "sessionProfile": self._session_profile,
            "interactionEngine": self._interaction_engine,
            "challengePolicy": self._challenge_policy,
            "environmentSimulation": self._bridge_environment,
            "interactionSimulation": self._bridge_interaction,
            "wasmTelemetry": self._bridge_wasm_telemetry,
        }
        data = self._bridge_request("POST", "/init", payload, timeout=45.0)
        self._emit_telemetry("bridge_initialized", {"runtime": data})
        self._assert_bridge_ready(data)
        return data

    def _bridge_register_targets(self) -> None:
        for signer in self._bridge_signers:
            self._bridge_request("POST", "/bridge/register", signer, timeout=20.0)

    def _bridge_set_cookies(self, cookies: dict[str, str]) -> None:
        self._bridge_request(
            "POST",
            "/set-cookies",
            {
                "url": self.PAGE_ORIGIN or self.START_URL,
                "cookies": cookies,
            },
        )

    def list_bridge_targets(self) -> list[str]:
        data = self._bridge_request("GET", "/bridge/list", timeout=5.0)
        return data.get("targets", [])

    def list_wasm_modules(self) -> list[dict[str, Any]]:
        self._assert_bridge_ready()
        modules = self._bridge_driver.list_wasm_modules()
        self._emit_telemetry("wasm_modules", {"count": len(modules), "modules": modules[-10:] if len(modules) > 10 else modules})
        return modules

    def get_wasm_report(self, module_id: str) -> dict[str, Any]:
        self._assert_bridge_ready()
        report = self._bridge_driver.get_wasm_report(module_id)
        self._emit_telemetry("wasm_report", {"moduleId": module_id, "report": report})
        return report

    def get_wasm_snapshots(
        self,
        *,
        instance_id: str | None = None,
        since: int = 0,
    ) -> list[dict[str, Any]]:
        self._assert_bridge_ready()
        snapshots = self._bridge_driver.get_wasm_snapshots(instance_id=instance_id, since=since)
        self._emit_telemetry(
            "wasm_snapshots",
            {"instanceId": instance_id, "since": since, "count": len(snapshots), "snapshots": snapshots[-10:] if len(snapshots) > 10 else snapshots},
        )
        return snapshots

    def discover_functions(
        self,
        *,
        min_score: float = 0.0,
        sink_field: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._bridge_driver.discover_functions(min_score=min_score, sink_field=sink_field)

    def register_function(
        self,
        name: str,
        *,
        global_path: str | None = None,
        owner_path: str | None = None,
        resolver_source: str | None = None,
        resolver_arg: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._bridge_driver.register_function(
            name,
            global_path=global_path,
            owner_path=owner_path,
            resolver_source=resolver_source,
            resolver_arg=resolver_arg,
        )

    def invoke_function(
        self,
        target_fn_name: str,
        args: list[Any] | None = None,
        *,
        auto_register: bool = True,
    ) -> Any:
        self._assert_bridge_ready()
        return self._bridge_driver.invoke_function(
            target_fn_name,
            args=args,
            auto_register=auto_register,
        )

    def invoke_wasm_export(
        self,
        *,
        export_name: str,
        module_id: str | None = None,
        instance_id: str | None = None,
        args: list[Any] | None = None,
        buffer_descriptors: list[dict[str, Any]] | None = None,
        capture_memory: bool = True,
        snapshot_mode: str | None = None,
    ) -> dict[str, Any]:
        self._assert_bridge_ready()
        result = self._bridge_driver.invoke_wasm_export(
            export_name=export_name,
            module_id=module_id,
            instance_id=instance_id,
            args=args,
            buffer_descriptors=buffer_descriptors,
            capture_memory=capture_memory,
            snapshot_mode=snapshot_mode,
        )
        self._emit_telemetry(
            "wasm_invoke",
            {
                "moduleId": module_id,
                "instanceId": instance_id,
                "exportName": export_name,
                "result": result,
            },
        )
        return result

    def _assert_bridge_ready(self, health: dict[str, Any] | None = None) -> dict[str, Any]:
        health = health or self._bridge_health()
        phase = health.get("phase") or health.get("status")
        if str(phase).startswith("challenge") or phase in {"crashed", "disconnected"}:
            events = self._bridge_events()
            challenge_status = None
            if str(phase).startswith("challenge"):
                try:
                    challenge_status = self.challenge_status()
                except Exception:
                    challenge_status = {"challenge": health.get("lastChallenge"), "phase": phase}
            self._emit_telemetry(
                "bridge_blocked",
                {
                    "phase": phase,
                    "health": health,
                    "challengeStatus": challenge_status,
                    "events": events[-10:],
                },
            )
            raise RuntimeError(
                f"Bridge is not usable, phase={phase}, challenge={challenge_status or health.get('lastChallenge')}, events={events[-3:]}"
            )
        return health

    def poll_bridge_events(self) -> list[dict[str, Any]]:
        events = self._bridge_events()
        if events:
            self._emit_telemetry("bridge_events", {"count": len(events), "events": events[-10:]})
        return events

    def bridge_environment_status(self) -> dict[str, Any]:
        status = self._bridge_request("GET", "/environment/status", timeout=10.0)
        self._emit_telemetry("environment_status", status)
        return status

    def challenge_status(self) -> dict[str, Any]:
        status = self._bridge_request("GET", "/challenge/status", timeout=10.0)
        self._emit_telemetry("challenge_status", status)
        return status

    def continue_challenge(self, bypass_token: str | None = None, **payload: Any) -> dict[str, Any]:
        request_payload = dict(payload)
        if bypass_token:
            request_payload["bypassToken"] = bypass_token
        result = self._bridge_request("POST", "/challenge/continue", request_payload, timeout=45.0)
        self._emit_telemetry("challenge_continue", result)
        return result

    def run_pointer_path(self, **payload: Any) -> dict[str, Any]:
        self._assert_bridge_ready()
        result = self._bridge_request("POST", "/interaction/run-pointer-path", payload, timeout=60.0)
        self._emit_telemetry("interaction_run_pointer_path", result)
        return result

    def run_interaction_scenario(self, **payload: Any) -> dict[str, Any]:
        self._assert_bridge_ready()
        result = self._bridge_request("POST", "/interaction/run-scenario", payload, timeout=120.0)
        self._emit_telemetry("interaction_run_scenario", result)
        return result

    def replay_pointer_trace(
        self,
        *,
        points: list[dict[str, Any]] | None = None,
        trace_path: str | None = None,
        **payload: Any,
    ) -> dict[str, Any]:
        self._assert_bridge_ready()
        request_payload = dict(payload)
        if points is not None:
            request_payload["points"] = points
        if trace_path:
            request_payload["tracePath"] = trace_path
        result = self._bridge_request("POST", "/interaction/replay-pointer-trace", request_payload, timeout=60.0)
        self._emit_telemetry("interaction_replay_pointer_trace", result)
        return result

    def _bridge_sign(self, url: str, method: str = "GET", body: str = "") -> dict[str, str]:
        self._assert_bridge_ready()
        payload: dict[str, Any] = {
            "url": url,
            "method": method,
            "body": body,
        }
        if self._cookies:
            payload["cookies"] = self._cookies
        preferred_signer = self.PREFERRED_BRIDGE_TARGET or (self._bridge_signers[0]["name"] if self._bridge_signers else "")
        if preferred_signer:
            payload["signer"] = preferred_signer
        data = self._bridge_request("POST", "/sign", payload, timeout=20.0)
        return data.get("headers", {})

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    def _update_cookies(self, response: Any) -> None:
        for key, value in _extract_response_cookies(response).items():
            self._cookies[key] = value
        if self._cookies:
            try:
                self._bridge_set_cookies(self._cookies)
            except Exception:
                pass

    def _bootstrap_cookies_from_storage_state(self) -> None:
        if self._cookies or not self._storage_state_path.exists():
            return
        try:
            payload = json.loads(self._storage_state_path.read_text(encoding="utf-8"))
        except Exception:
            return

        target_host = urllib.parse.urlsplit(self.PAGE_ORIGIN or self.START_URL).hostname or ""
        fallback: dict[str, str] = {}
        scoped: dict[str, str] = {}
        for cookie in payload.get("cookies", []):
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            fallback[str(name)] = str(value)
            domain = str(cookie.get("domain") or "").lstrip(".")
            if domain and target_host.endswith(domain):
                scoped[str(name)] = str(value)

        self._cookies.update(scoped or fallback)
        if self._cookies:
            self._last_headers["Cookie"] = self._cookie_header()

    def _should_use_observed_verbatim_headers(self, headers: dict[str, str] | None) -> bool:
        if self._bridge_signers or self.PREFERRED_BRIDGE_TARGET:
            return False
        lowered = {str(key).lower() for key in (headers or {}).keys()}
        return any(
            key in lowered
            for key in {
                "af-ac-enc-dat",
                "af-ac-enc-sz-token",
                "sz-token",
                "x-sap-ri",
                "x-sap-sec",
                "d-nonptcha-sync",
                "x-sz-sdk-version",
            }
        )

    @staticmethod
    def _normalize_scalar(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return str(value)

    def _build_url(self, url: str, params: dict[str, Any] | None = None) -> str:
        if not params:
            return url

        pairs: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                for item in value:
                    pairs.append((key, self._normalize_scalar(item)))
            else:
                pairs.append((key, self._normalize_scalar(value)))

        query = urllib.parse.urlencode(pairs, doseq=True)
        if not query:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{query}"

    def _automation_label(self) -> dict[str, Any]:
        return dict(self._session_profile.get("automationLabel") or {})

    def _apply_automation_label(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str]]:
        label = self._automation_label()
        if not label or label.get("enabled") is False:
            return url, dict(headers or {})

        updated_headers = dict(headers or {})
        header_name = label.get("headerName")
        header_value = label.get("headerValue")
        if header_name and header_value is not None and not any(
            str(existing).lower() == str(header_name).lower() for existing in updated_headers
        ):
            updated_headers[str(header_name)] = str(header_value)

        cookie_name = label.get("cookieName")
        cookie_value = label.get("cookieValue")
        if cookie_name and cookie_value is not None and cookie_name not in self._cookies:
            self._cookies[str(cookie_name)] = str(cookie_value)

        query_name = label.get("queryName")
        query_value = label.get("queryValue")
        if query_name and query_value is not None:
            parsed = urllib.parse.urlsplit(url)
            query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            query_map = dict(query_pairs)
            if str(query_name) not in query_map:
                query_map[str(query_name)] = str(query_value)
                url = urllib.parse.urlunsplit(
                    (
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        urllib.parse.urlencode(list(query_map.items()), doseq=True),
                        parsed.fragment,
                    )
                )

        return url, updated_headers

    def _serialize_body(
        self,
        *,
        json_body: Any | None = None,
        form_data: dict[str, Any] | None = None,
        raw_body: str | bytes | None = None,
    ) -> tuple[str, str | None]:
        if raw_body not in (None, ""):
            if isinstance(raw_body, bytes):
                return raw_body.decode("utf-8", errors="replace"), None
            return str(raw_body), None
        if json_body is not None:
            return self._json_dumps(json_body), "application/json"
        if form_data:
            encoded = urllib.parse.urlencode(
                {key: self._normalize_scalar(value) for key, value in form_data.items()},
                doseq=True,
            )
            return encoded, "application/x-www-form-urlencoded; charset=UTF-8"
        return "", None

    def _prepare_headers(
        self,
        *,
        final_url: str,
        method: str,
        body_text: str,
        extra_headers: dict[str, str] | None = None,
        use_bridge: bool = True,
        preserve_observed_headers: bool = False,
    ) -> tuple[str, dict[str, str]]:
        final_url, extra_headers = self._apply_automation_label(final_url, extra_headers)
        bridge_headers: dict[str, str] = {}
        if use_bridge:
            bridge_fields = self._bridge_sign(final_url, method, body_text if method != "GET" else "")
            final_url, bridge_headers = self._apply_bridge_fields(final_url, bridge_fields)
        headers = dict(extra_headers or {}) if preserve_observed_headers else self._merge_headers(self.DEFAULT_HEADERS, extra_headers or {})
        if bridge_headers:
            headers = self._merge_headers(headers, bridge_headers)
        if self._cookies and self._should_attach_cookie_header(final_url, method, headers):
            headers["Cookie"] = self._cookie_header()

        _inject_sec_ch_ua_headers(headers, self._session_profile.get("userAgent") or "")

        self._last_request_url = final_url
        self._last_headers = dict(headers)
        return final_url, headers

    def _should_attach_cookie_header(self, url: str, method: str, headers: dict[str, str]) -> bool:
        if any(str(key).lower() == "cookie" for key in headers):
            return True
        parsed = urllib.parse.urlsplit(url)
        request_host = (parsed.hostname or "").lower()
        page_host = urllib.parse.urlsplit(self.PAGE_ORIGIN or self.START_URL).hostname or ""
        site_suffix = page_host[4:] if page_host.startswith("www.") else page_host
        if request_host and site_suffix:
            if request_host == page_host or request_host == site_suffix or request_host.endswith(f".{site_suffix}"):
                return True
        path = (parsed.path or "").lower()
        if "/h5/" in path:
            return True
        return method.upper() not in {"GET", "HEAD"}

    @staticmethod
    def _merge_headers(
        base_headers: dict[str, str] | None,
        extra_headers: dict[str, str] | None,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        canonical_names: dict[str, str] = {}
        for source in (base_headers or {}, extra_headers or {}):
            for key, value in source.items():
                if value is None:
                    continue
                actual_key = str(key)
                lowered = actual_key.lower()
                previous_key = canonical_names.get(lowered)
                if previous_key and previous_key in merged:
                    del merged[previous_key]
                merged[actual_key] = str(value)
                canonical_names[lowered] = actual_key
        return merged

    def _apply_bridge_fields(self, url: str, bridge_fields: dict[str, str]) -> tuple[str, dict[str, str]]:
        if not bridge_fields:
            return url, {}

        parsed = urllib.parse.urlsplit(url)
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query_map = {key: value for key, value in query_pairs}
        header_fields: dict[str, str] = {}

        for key, value in bridge_fields.items():
            lowered = str(key).lower()
            if lowered in {"sign", "t"}:
                query_map[str(key)] = str(value)
            else:
                header_fields[str(key)] = str(value)

        rebuilt_query = urllib.parse.urlencode(list(query_map.items()), doseq=True)
        rebuilt_url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, rebuilt_query, parsed.fragment)
        )
        return rebuilt_url, header_fields

    @staticmethod
    def _parse_response(response: Any) -> Any:
        headers = {str(key): str(value) for key, value in getattr(response, "headers", {}).items()}
        content_type = headers.get("content-type", "").lower()
        if "json" in content_type:
            try:
                return response.json()
            except Exception:
                pass
        return {
            "status_code": getattr(response, "status_code", None),
            "headers": headers,
            "text": getattr(response, "text", ""),
        }

    def request(
        self,
        *,
        url: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        form_data: dict[str, Any] | None = None,
        raw_body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
        use_bridge: bool = True,
        preserve_observed_headers: bool = False,
    ) -> Any:
        method = method.upper()
        final_url = self._build_url(url, params)
        body_text, inferred_content_type = self._serialize_body(
            json_body=json_body,
            form_data=form_data,
            raw_body=raw_body,
        )

        request_headers = dict(headers or {})
        if inferred_content_type and "Content-Type" not in request_headers and "content-type" not in request_headers:
            request_headers["Content-Type"] = inferred_content_type

        final_url, prepared_headers = self._prepare_headers(
            final_url=final_url,
            method=method,
            body_text=body_text,
            extra_headers=request_headers,
            use_bridge=use_bridge,
            preserve_observed_headers=preserve_observed_headers,
        )

        body = body_text.encode("utf-8") if method not in {"GET", "HEAD"} and body_text else None

        try:
            execution = self._transport.request(
                method=method,
                url=final_url,
                headers=prepared_headers,
                body=body,
                timeout=timeout,
            )
        except RuntimeError as exc:
            payload: dict[str, Any] | None = None
            try:
                payload = json.loads(str(exc))
            except Exception:
                payload = None
            self._emit_telemetry(
                "http_request_failed",
                {
                    "method": method,
                    "url": final_url,
                    "headers": prepared_headers,
                    "bodyLength": len(body or b""),
                    "transport": payload or {"error": str(exc)},
                },
            )
            raise

        response = execution.response
        self._update_cookies(response)
        telemetry = {
            "method": method,
            "url": final_url,
            "headers": prepared_headers,
            "bodyLength": len(body or b""),
            "transport": execution.telemetry,
            "failureClass": None,
        }
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 400:
            telemetry["failureClass"] = "http_status"
            self._emit_telemetry("http_request_completed", telemetry)
            raise RuntimeError(
                f"HTTP request failed with status {status_code}: {getattr(response, 'text', '')[:500]}"
            )

        self._emit_telemetry("http_request_completed", telemetry)
        return self._parse_response(response)

    def replay_observed(self, index: int = 0) -> Any:
        if not self.OBSERVED_TARGETS:
            raise RuntimeError("No observed target requests are embedded in this crawler")
        if index < 0 or index >= len(self.OBSERVED_TARGETS):
            raise IndexError(f"Observed target index out of range: {index}")

        target = self.OBSERVED_TARGETS[index]
        observed_headers = target.get("headers") or {}
        preserve_observed_headers = self._should_use_observed_verbatim_headers(observed_headers)
        return self.request(
            url=target["url"],
            method=target.get("method", "GET"),
            raw_body=target.get("body") or "",
            headers=observed_headers,
            use_bridge=not preserve_observed_headers,
            preserve_observed_headers=preserve_observed_headers,
        )

    # ------------------------------------------------------------------
    # Generic pagination engine
    # ------------------------------------------------------------------
    # Common query-param names for each pagination concept.
    # Listed in priority order; first match wins.
    _OFFSET_PARAMS  = ("offset", "newest", "start", "skip", "from", "begins_at", "first")
    _PAGE_PARAMS    = ("page", "p", "page_num", "pagenum", "pageno", "pg", "page_index")
    _CURSOR_PARAMS  = ("cursor", "next_cursor", "page_token", "after", "continuation_token", "scroll_id")
    _LIMIT_PARAMS   = ("limit", "size", "count", "per_page", "pageSize", "page_size", "num", "n")
    # Response-body keys where the items array lives
    _ITEMS_KEYS     = ("items", "data", "results", "products", "list", "records",
                       "entries", "hits", "ads", "nodes", "goods", "content")
    # Response-body keys that report total available items
    _TOTAL_KEYS     = ("total", "total_count", "totalCount", "count", "total_results",
                       "totalResults", "total_num", "totalNum", "num_found", "numFound")
    # Keys that signal "no more pages"
    _END_KEYS       = ("is_end", "isEnd", "end_of_list", "no_more", "noMore",
                       "eof", "finished", "done")
    # Keys that carry a next-page cursor
    _NEXT_CURSOR_KEYS = ("next_cursor", "nextCursor", "cursor", "next_page_token",
                         "nextPageToken", "after", "scroll_id")
    # Keys that carry a boolean "has-more" signal (True = more pages)
    _HAS_MORE_KEYS  = ("has_more", "hasMore", "has_next", "hasNext", "more", "continue")

    @staticmethod
    def _find_items(data: Any) -> list:
        """Extract the main items list from a JSON response payload."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in BaseCrawler._ITEMS_KEYS:
                val = data.get(key)
                if isinstance(val, list):
                    return val
        return []

    @staticmethod
    def _find_total(data: Any) -> int | None:
        """Extract the total-item count from a JSON response payload."""
        if isinstance(data, dict):
            for key in BaseCrawler._TOTAL_KEYS:
                val = data.get(key)
                if isinstance(val, int) and val >= 0:
                    return val
        return None

    @staticmethod
    def _is_end_of_stream(data: Any) -> bool:
        """Return True if the response signals that there are no more pages."""
        if not isinstance(data, dict):
            return False
        for key in BaseCrawler._END_KEYS:
            if data.get(key) is True:
                return True
        for key in BaseCrawler._HAS_MORE_KEYS:
            val = data.get(key)
            if val is False:
                return True
        return False

    @staticmethod
    def _next_cursor_value(data: Any) -> str | None:
        """Extract a cursor / page-token for cursor-based pagination."""
        if not isinstance(data, dict):
            return None
        for key in BaseCrawler._NEXT_CURSOR_KEYS:
            val = data.get(key)
            if val and isinstance(val, (str, int)):
                return str(val)
        return None

    @staticmethod
    def _detect_pagination(parsed_qs: dict[str, list[str]]) -> tuple[str, str, int, int]:
        """Inspect the first observed request's query-string and return
        (scheme, param_name, current_value, page_size).

        scheme is one of: 'offset', 'page', 'cursor', 'none'
        """
        # Detect limit/page-size first
        page_size = 20
        for lp in BaseCrawler._LIMIT_PARAMS:
            if lp in parsed_qs:
                try:
                    page_size = int(parsed_qs[lp][0])
                    break
                except (ValueError, IndexError):
                    pass

        # Offset-based
        for op in BaseCrawler._OFFSET_PARAMS:
            if op in parsed_qs:
                try:
                    val = int(parsed_qs[op][0])
                    return ("offset", op, val, page_size)
                except (ValueError, IndexError):
                    pass

        # Cursor-based
        for cp in BaseCrawler._CURSOR_PARAMS:
            if cp in parsed_qs:
                return ("cursor", cp, 0, page_size)

        # Page-number-based
        for pp in BaseCrawler._PAGE_PARAMS:
            if pp in parsed_qs:
                try:
                    val = int(parsed_qs[pp][0])
                    return ("page", pp, val, page_size)
                except (ValueError, IndexError):
                    pass

        return ("none", "", 0, page_size)

    def collect_items(
        self,
        item_limit: int = 100,
        *,
        request_delay: float = 0.5,
        index: int = 0,
    ) -> list[Any]:
        """Collect up to *item_limit* items from the first observed target by
        automatically paginating through successive pages.

        Works generically for any site by:
        - Detecting the pagination scheme (offset / page-number / cursor / none)
          from the first observed URL's query-string.
        - Extracting items from the response using common response-key heuristics.
        - Stopping when the response signals end-of-stream, returns an empty page,
          or the total seen so far reaches *item_limit*.

        All logic is site-agnostic.  No site-specific parameter names or
        response shapes are hard-coded.
        """
        if not self.OBSERVED_TARGETS or index >= len(self.OBSERVED_TARGETS):
            return []

        seed_target = self.OBSERVED_TARGETS[index]
        seed_url = seed_target.get("url", "")
        seed_method = seed_target.get("method", "GET").upper()
        seed_headers = seed_target.get("headers") or {}

        # Parse the seed URL to discover pagination params
        parsed = urllib.parse.urlparse(seed_url)
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        scheme, param_name, start_val, page_size = self._detect_pagination(qs)

        collected: list[Any] = []
        cursor_value: str | None = None
        page_index = start_val  # offset or page counter

        preserve = self._should_use_observed_verbatim_headers(seed_headers)

        for _iteration in range(max(1, (item_limit // max(1, page_size)) + 5)):
            if len(collected) >= item_limit:
                break

            # Build the paginated URL
            if scheme == "offset":
                new_qs = dict(qs)
                new_qs[param_name] = [str(page_index)]
                new_query = urllib.parse.urlencode(new_qs, doseq=True)
                page_url = urllib.parse.urlunparse(parsed._replace(query=new_query))
            elif scheme == "page":
                new_qs = dict(qs)
                new_qs[param_name] = [str(page_index)]
                new_query = urllib.parse.urlencode(new_qs, doseq=True)
                page_url = urllib.parse.urlunparse(parsed._replace(query=new_query))
            elif scheme == "cursor" and cursor_value is not None:
                new_qs = dict(qs)
                new_qs[param_name] = [cursor_value]
                new_query = urllib.parse.urlencode(new_qs, doseq=True)
                page_url = urllib.parse.urlunparse(parsed._replace(query=new_query))
            else:
                page_url = seed_url

            try:
                data = self.request(
                    url=page_url,
                    method=seed_method,
                    raw_body=seed_target.get("body") or "",
                    headers=seed_headers,
                    use_bridge=not preserve,
                    preserve_observed_headers=preserve,
                )
            except Exception as exc:
                import sys
                print(f"[collect_items] request failed on page {_iteration}: {exc}", file=sys.stderr)
                break

            page_items = self._find_items(data)
            if not page_items:
                break  # Empty page → end of data

            # Trim to not exceed item_limit
            remaining = item_limit - len(collected)
            collected.extend(page_items[:remaining])

            if self._is_end_of_stream(data):
                break

            # Advance pagination state
            if scheme == "cursor":
                next_cur = self._next_cursor_value(data)
                if not next_cur or next_cur == cursor_value:
                    break
                cursor_value = next_cur
            elif scheme == "offset":
                page_index += len(page_items)
            elif scheme == "page":
                page_index += 1
            else:
                break  # No pagination detected — single page only

            # Respect rate limits
            if request_delay > 0:
                time.sleep(request_delay)

        return collected

    def crawl_known_endpoint(self, method: str = "GET") -> Any:
        if self.KNOWN_ENDPOINT:
            return self.request(url=self.KNOWN_ENDPOINT, method=method)
        if self.OBSERVED_TARGETS:
            return self.replay_observed(0)
        return self.request(url=self.START_URL or self.PAGE_ORIGIN, method="GET")

    def crawl(self, **kwargs: Any) -> Any:
        action = kwargs.pop("action", "observed" if self.OBSERVED_TARGETS else "page")

        if action == "observed":
            return self.replay_observed(index=int(kwargs.get("index", 0)))
        if action == "known_endpoint":
            return self.crawl_known_endpoint(method=str(kwargs.get("method", "GET")))
        if action == "page":
            return self.request(url=str(kwargs.get("url", self.START_URL or self.PAGE_ORIGIN)), method="GET")
        if action == "request":
            return self.request(
                url=str(kwargs["url"]),
                method=str(kwargs.get("method", "GET")),
                params=kwargs.get("params"),
                json_body=kwargs.get("json_body"),
                form_data=kwargs.get("form_data"),
                raw_body=kwargs.get("raw_body"),
                headers=kwargs.get("headers"),
                timeout=float(kwargs.get("timeout", 20.0)),
            )
        raise ValueError(f"Unknown action: {action}")

    def close(self) -> None:
        self._emit_telemetry(
            "session_closed",
            {
                "transportBackend": self._transport_backend,
                "recordCount": len(self._telemetry_records),
            },
        )
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    def __del__(self) -> None:
        self.close()


if __name__ == "__main__":
    crawler = __AXELO_CRAWLER_CLASS__(bridge=True)
    try:
        result = crawler.crawl()
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
        print(json.dumps(crawler.poll_bridge_events(), ensure_ascii=False, indent=2))
    finally:
        crawler.close()
