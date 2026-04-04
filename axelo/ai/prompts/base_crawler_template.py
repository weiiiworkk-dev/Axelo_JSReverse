"""
Generated crawler - Axelo JSReverse (Deterministic bridge mode)
This file is rendered from axelo/ai/prompts/base_crawler_template.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx


class __AXELO_CRAWLER_CLASS__:
    BRIDGE_PORT = __AXELO_BRIDGE_PORT__
    BRIDGE_PATH = "bridge_server.js"

    PAGE_ORIGIN = __AXELO_PAGE_ORIGIN__
    START_URL = __AXELO_START_URL__
    KNOWN_ENDPOINT = __AXELO_KNOWN_ENDPOINT__
    API_BASE = __AXELO_PREFERRED_API_BASE__
    BRIDGE_LOCALE = __AXELO_BRIDGE_LOCALE__
    BRIDGE_TIMEZONE = __AXELO_BRIDGE_TIMEZONE__
    DEFAULT_STORAGE_STATE_PATH = __AXELO_STORAGE_STATE_PATH__
    DEFAULT_ENVIRONMENT = __AXELO_DEFAULT_ENVIRONMENT__
    DEFAULT_INTERACTION = __AXELO_DEFAULT_INTERACTION__

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
    ) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._cookies: dict[str, str] = dict(cookies or {})
        self._last_headers: dict[str, str] = {}
        self._last_request_url: str = ""
        self._bridge_event_cursor = 0
        self._bridge_headless = bridge_headless
        self._bridge_signers = bridge_signers or []
        self._bridge_environment = dict(bridge_environment or self.DEFAULT_ENVIRONMENT or {})
        self._bridge_interaction = dict(bridge_interaction or self.DEFAULT_INTERACTION or {})
        self._bridge_base_url = f"http://127.0.0.1:{self.BRIDGE_PORT}"
        self._file_dir = Path(__file__).resolve().parent
        self._session_dir = self._file_dir.parent
        self._repo_root = self._find_repo_root()

        default_storage_state = self.DEFAULT_STORAGE_STATE_PATH or str(self._session_dir / "browser_storage_state.json")
        self._storage_state_path = Path(storage_state_path or default_storage_state)

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

    def _start_bridge(self) -> None:
        env = os.environ.copy()
        node_path = self._node_path()
        if node_path:
            env["NODE_PATH"] = node_path

        self._proc = subprocess.Popen(
            ["node", self.BRIDGE_PATH],
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
        url = f"{self._bridge_base_url}{path}"
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, json=payload)

        if response.status_code >= 400:
            detail = ""
            try:
                data = response.json()
                detail = data.get("error") or json.dumps(data, ensure_ascii=False)
            except Exception:
                detail = response.text
            raise RuntimeError(f"Bridge {method} {path} failed: HTTP {response.status_code} {detail}")

        return response.json()

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
            "locale": self.BRIDGE_LOCALE,
            "timezoneId": self.BRIDGE_TIMEZONE,
            "defaultSigner": self._bridge_signers[0]["name"] if self._bridge_signers else "",
            "environmentSimulation": self._bridge_environment,
            "interactionSimulation": self._bridge_interaction,
        }
        data = self._bridge_request("POST", "/init", payload, timeout=45.0)
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

    def _assert_bridge_ready(self, health: dict[str, Any] | None = None) -> dict[str, Any]:
        health = health or self._bridge_health()
        phase = health.get("phase") or health.get("status")
        if phase in {"challenge", "crashed", "disconnected"}:
            events = self._bridge_events()
            raise RuntimeError(
                f"Bridge is not usable, phase={phase}, challenge={health.get('lastChallenge')}, events={events[-3:]}"
            )
        return health

    def poll_bridge_events(self) -> list[dict[str, Any]]:
        return self._bridge_events()

    def bridge_environment_status(self) -> dict[str, Any]:
        return self._bridge_request("GET", "/environment/status", timeout=10.0)

    def run_pointer_path(self, **payload: Any) -> dict[str, Any]:
        self._assert_bridge_ready()
        return self._bridge_request("POST", "/interaction/run-pointer-path", payload, timeout=60.0)

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
        return self._bridge_request("POST", "/interaction/replay-pointer-trace", request_payload, timeout=60.0)

    def _bridge_sign(self, url: str, method: str = "GET", body: str = "") -> dict[str, str]:
        self._assert_bridge_ready()
        payload: dict[str, Any] = {
            "url": url,
            "method": method,
            "body": body,
            "cookies": self._cookies,
        }
        if self._bridge_signers:
            payload["signer"] = self._bridge_signers[0]["name"]
        data = self._bridge_request("POST", "/sign", payload, timeout=20.0)
        return data.get("headers", {})

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    def _update_cookies(self, response: httpx.Response) -> None:
        for key, value in response.cookies.items():
            self._cookies[key] = value
        if self._cookies:
            try:
                self._bridge_set_cookies(self._cookies)
            except Exception:
                pass

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
    ) -> dict[str, str]:
        bridge_headers = self._bridge_sign(final_url, method, body_text if method != "GET" else "")
        headers = {**self.DEFAULT_HEADERS}
        if extra_headers:
            headers.update({str(key): str(value) for key, value in extra_headers.items() if value is not None})
        headers.update(bridge_headers)
        if self._cookies:
            headers["Cookie"] = self._cookie_header()

        self._last_request_url = final_url
        self._last_headers = dict(headers)
        return headers

    @staticmethod
    def _parse_response(response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "").lower()
        if "json" in content_type:
            try:
                return response.json()
            except Exception:
                pass
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "text": response.text,
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

        prepared_headers = self._prepare_headers(
            final_url=final_url,
            method=method,
            body_text=body_text,
            extra_headers=request_headers,
        )

        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": final_url,
            "headers": prepared_headers,
            "timeout": timeout,
            "follow_redirects": True,
        }
        if method not in {"GET", "HEAD"} and body_text:
            request_kwargs["content"] = body_text.encode("utf-8")

        with httpx.Client() as client:
            response = client.request(**request_kwargs)
            response.raise_for_status()
            self._update_cookies(response)
            return self._parse_response(response)

    def replay_observed(self, index: int = 0) -> Any:
        if not self.OBSERVED_TARGETS:
            raise RuntimeError("No observed target requests are embedded in this crawler")
        if index < 0 or index >= len(self.OBSERVED_TARGETS):
            raise IndexError(f"Observed target index out of range: {index}")

        target = self.OBSERVED_TARGETS[index]
        return self.request(
            url=target["url"],
            method=target.get("method", "GET"),
            raw_body=target.get("body") or "",
            headers=target.get("headers") or {},
        )

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
