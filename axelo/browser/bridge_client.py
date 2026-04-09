from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx


class BridgeClient:
    """HTTP client for the generated Playwright-backed bridge server."""

    def __init__(self, base_url: str, *, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        with httpx.Client(timeout=timeout or self._timeout) as client:
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

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health", timeout=5.0)

    def list_targets(self) -> list[str]:
        return self.request("GET", "/bridge/list", timeout=5.0).get("targets", [])

    def list_wasm_modules(self) -> list[dict[str, Any]]:
        return self.request("GET", "/wasm/modules", timeout=10.0).get("modules", [])

    def get_wasm_report(self, module_id: str) -> dict[str, Any]:
        encoded = quote(module_id, safe="")
        return self.request("GET", f"/wasm/report?moduleId={encoded}", timeout=15.0)

    def get_wasm_snapshots(
        self,
        *,
        instance_id: str | None = None,
        since: int = 0,
    ) -> list[dict[str, Any]]:
        query = f"/wasm/snapshots?since={int(since)}"
        if instance_id:
            query += f"&instanceId={quote(instance_id, safe='')}"
        return self.request("GET", query, timeout=15.0).get("snapshots", [])

    def register_function(
        self,
        name: str,
        *,
        global_path: str | None = None,
        owner_path: str | None = None,
        resolver_source: str | None = None,
        resolver_arg: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "globalPath": global_path,
            "ownerPath": owner_path,
            "resolverSource": resolver_source,
            "resolverArg": resolver_arg or None,
        }
        return self.request("POST", "/bridge/register", payload, timeout=20.0)

    def discover_functions(
        self,
        *,
        min_score: float = 0.0,
        sink_field: str | None = None,
    ) -> list[dict[str, Any]]:
        query = f"?min_score={min_score:.3f}"
        if sink_field:
            query += f"&sink_field={sink_field}"
        data = self.request("GET", f"/executor/discover{query}", timeout=10.0)
        return data.get("candidates", [])

    def invoke_function(
        self,
        target_fn_name: str,
        args: list[Any] | None = None,
        *,
        auto_register: bool = True,
    ) -> Any:
        payload = {
            "name": target_fn_name,
            "args": list(args or []),
            "autoRegister": auto_register,
        }
        data = self.request("POST", "/executor/invoke", payload, timeout=20.0)
        return data.get("result")

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
        payload: dict[str, Any] = {
            "moduleId": module_id,
            "instanceId": instance_id,
            "exportName": export_name,
            "args": list(args or []),
            "bufferDescriptors": list(buffer_descriptors or []),
            "captureMemory": capture_memory,
            "snapshotMode": snapshot_mode,
        }
        return self.request("POST", "/wasm/invoke", payload, timeout=30.0)


class BridgeDriver(BridgeClient):
    """Thin semantic alias for callers that treat the bridge as a runtime driver."""

    pass
