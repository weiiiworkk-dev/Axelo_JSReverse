from __future__ import annotations

import json
import secrets
import time

import structlog
from playwright.async_api import Page

from axelo.models.analysis import HookIntercept, TaintEvent, TaintSink

log = structlog.get_logger()

DEFAULT_HOOK_TARGETS: list[str] = [
    "crypto.subtle.sign",
    "crypto.subtle.digest",
    "crypto.subtle.encrypt",
    "crypto.subtle.decrypt",
    "crypto.getRandomValues",
    "window.btoa",
    "window.atob",
    "Date.now",
    "Math.random",
    "JSON.stringify",
    "TextEncoder.prototype.encode",
    "URLSearchParams.prototype.append",
    "URLSearchParams.prototype.set",
    "FormData.prototype.append",
    "Headers.prototype.append",
    "Headers.prototype.set",
    "HTMLCanvasElement.prototype.toDataURL",
    "CanvasRenderingContext2D.prototype.getImageData",
    "WebGLRenderingContext.prototype.readPixels",
    "WebGL2RenderingContext.prototype.readPixels",
    "window.fetch",
    "navigator.sendBeacon",
    "XMLHttpRequest.prototype.open",
    "XMLHttpRequest.prototype.setRequestHeader",
    "XMLHttpRequest.prototype.send",
]


class JSHookInjector:
    """
    Inject a browser-side taint runtime and keep the legacy HookIntercept stream.
    """

    def __init__(self) -> None:
        self.intercepts: list[HookIntercept] = []
        self.taint_events: list[TaintEvent] = []
        self._sequence = 0
        self._binding_name = ""

    async def inject(self, page: Page, targets: list[str] | None = None) -> None:
        targets = targets or DEFAULT_HOOK_TARGETS
        self._binding_name = f"__axelo_cb_{secrets.token_hex(6)}"
        hook_js = self._build_hook_js(targets, self._binding_name)
        await page.expose_binding(self._binding_name, self._on_hook_fired, handle=False)
        await page.add_init_script(hook_js)
        log.info("hooks_injected", count=len(targets))

    def _on_hook_fired(self, _source: dict, event_type: str, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except Exception:
            payload = {}

        sequence = int(payload.get("sequence", self._sequence))
        timestamp = float(payload.get("timestamp", time.time()))
        self._sequence = max(self._sequence, sequence + 1)

        if event_type == "raw_call":
            intercept = HookIntercept(
                api_name=str(payload.get("api_name", "")),
                args_repr=str(payload.get("args_json", "[]") or "[]"),
                return_repr=str(payload.get("return_json", "null") or "null"),
                stack_trace=[str(item) for item in payload.get("stack_trace", [])],
                timestamp=timestamp,
                sequence=sequence,
            )
            self.intercepts.append(intercept)
            log.debug("hook_fired", api=intercept.api_name, seq=intercept.sequence)
            return

        if event_type not in {"source", "transform", "sink"}:
            return

        sink_payload = payload.get("sink")
        sink = None
        if isinstance(sink_payload, dict):
            sink = TaintSink(
                request_id=str(sink_payload.get("request_id", "")),
                sink_field=str(sink_payload.get("sink_field", "")),
                sink_kind=str(sink_payload.get("sink_kind", "unknown")),
                request_url=str(sink_payload.get("request_url", "")),
                request_method=str(sink_payload.get("request_method", "")),
            )

        event = TaintEvent(
            event_type=event_type,
            api_name=str(payload.get("api_name", "")),
            taint_ids=[str(item) for item in payload.get("taint_ids", [])],
            parent_taint_ids=[str(item) for item in payload.get("parent_taint_ids", [])],
            sequence=sequence,
            timestamp=timestamp,
            stack_trace=[str(item) for item in payload.get("stack_trace", [])],
            value_preview=str(payload.get("value_preview", "")),
            sink=sink,
        )
        self.taint_events.append(event)
        log.debug("taint_event", event_type=event.event_type, api=event.api_name, seq=event.sequence)

    def _build_hook_js(self, targets: list[str], binding_name: str) -> str:
        template = r"""
(function() {
  const hookTargets = __HOOK_TARGETS__;
  const bindingName = __HOOK_BINDING__;
  const emitBinding = (() => {
    const binding = window[bindingName];
    if (typeof binding !== "function") return null;
    try {
      delete window[bindingName];
    } catch (_error) {}
    return binding.bind(window);
  })();
  const OBJECT_TAINTS = new WeakMap();
  const PRIMITIVE_TAINTS = new Map();
  const XHR_STATE = new WeakMap();
  let eventSeq = 0;
  let taintSeq = 0;
  let requestSeq = 0;

  function nextSequence() { return eventSeq++; }
  function nextTaintId() { taintSeq += 1; return "t" + taintSeq; }
  function nextRequestId() { requestSeq += 1; return "req_" + requestSeq; }
  function nowTs() { return Date.now() / 1000; }

  function captureStack() {
    try {
      return String(new Error().stack || "")
        .split("\n")
        .slice(2, 8)
        .map((line) => line.trim())
        .filter((line) => line && line.indexOf("__axelo") === -1);
    } catch (_error) {
      return [];
    }
  }

  function safeReplacer(_key, value) {
    if (value instanceof ArrayBuffer) {
      return { __type: "ArrayBuffer", byteLength: value.byteLength };
    }
    if (ArrayBuffer.isView(value)) {
      return { __type: value.constructor.name, byteLength: value.byteLength };
    }
    if (value instanceof Headers) {
      return Object.fromEntries(Array.from(value.entries()));
    }
    if (value instanceof URLSearchParams) {
      return Object.fromEntries(Array.from(value.entries()));
    }
    if (value instanceof FormData) {
      return Array.from(value.entries()).map(([key, item]) => [key, String(item)]);
    }
    if (value instanceof Promise) return "[Promise]";
    if (typeof value === "function") return "[Function]";
    return value;
  }

  function preview(value) {
    try {
      const serialized = JSON.stringify(value, safeReplacer);
      return serialized && serialized.length > 240 ? serialized.slice(0, 240) + "..." : (serialized || "");
    } catch (_error) {
      try {
        return String(value);
      } catch (_stringError) {
        return "";
      }
    }
  }

  function emit(eventType, payload) {
    try {
      if (!emitBinding) return;
      emitBinding(eventType, JSON.stringify(Object.assign({
        sequence: nextSequence(),
        timestamp: nowTs(),
      }, payload || {})));
    } catch (_error) {}
  }

  function emitRawCall(apiName, args, result, stack) {
    emit("raw_call", {
      api_name: apiName,
      args_json: preview(args),
      return_json: preview(result),
      stack_trace: stack || captureStack(),
    });
  }

  function fingerprint(value) {
    if (value === null) return "null";
    if (value === undefined) return "undefined";
    const valueType = typeof value;
    if (valueType === "string") return "s:" + value.slice(0, 180);
    if (valueType === "number" || valueType === "boolean") return valueType + ":" + String(value);
    return "";
  }

  function storePrimitive(value, meta) {
    const key = fingerprint(value);
    if (!key) return;
    const bucket = PRIMITIVE_TAINTS.get(key) || [];
    bucket.push({ meta: meta, ts: Date.now() });
    PRIMITIVE_TAINTS.set(key, bucket.slice(-8));
  }

  function markValue(value, meta) {
    if (value && (typeof value === "object" || typeof value === "function")) {
      OBJECT_TAINTS.set(value, meta);
      if (ArrayBuffer.isView(value) && value.buffer) OBJECT_TAINTS.set(value.buffer, meta);
      return;
    }
    storePrimitive(value, meta);
  }

  function lookupValue(value) {
    if (value && (typeof value === "object" || typeof value === "function")) {
      if (OBJECT_TAINTS.has(value)) return OBJECT_TAINTS.get(value);
      if (ArrayBuffer.isView(value) && value.buffer && OBJECT_TAINTS.has(value.buffer)) return OBJECT_TAINTS.get(value.buffer);
      return null;
    }
    const key = fingerprint(value);
    if (!key) return null;
    const bucket = PRIMITIVE_TAINTS.get(key) || [];
    return bucket.length ? bucket[bucket.length - 1].meta : null;
  }

  function collectMetas(value, depth, seen) {
    if (depth < 0) return [];
    const state = seen || new WeakSet();
    const metas = [];
    const direct = lookupValue(value);
    if (direct) metas.push(direct);
    if (!value || typeof value !== "object") return metas;
    if (state.has(value)) return metas;
    state.add(value);

    if (Array.isArray(value)) {
      for (const item of value.slice(0, 6)) metas.push.apply(metas, collectMetas(item, depth - 1, state));
      return metas;
    }
    if (value instanceof Headers) {
      for (const entry of Array.from(value.entries()).slice(0, 12)) metas.push.apply(metas, collectMetas(entry[1], depth - 1, state));
      return metas;
    }
    if (value instanceof URLSearchParams || value instanceof FormData) {
      for (const entry of Array.from(value.entries()).slice(0, 12)) metas.push.apply(metas, collectMetas(entry[1], depth - 1, state));
      return metas;
    }
    for (const key of Object.keys(value).slice(0, 12)) {
      let nested;
      try { nested = value[key]; } catch (_error) { continue; }
      metas.push.apply(metas, collectMetas(nested, depth - 1, state));
    }
    return metas;
  }

  function uniqueIds(items) {
    return Array.from(new Set(items.filter(Boolean)));
  }

  function parentIdsFromArgs(args) {
    const metas = collectMetas(args, 2);
    return uniqueIds(metas.flatMap((item) => item.taint_ids || []));
  }

  function createMeta(apiName, parentIds) {
    return {
      taint_ids: [nextTaintId()],
      parent_taint_ids: uniqueIds(parentIds || []),
      api_name: apiName,
    };
  }

  function markSource(apiName, value) {
    const stack = captureStack();
    const meta = createMeta(apiName, []);
    markValue(value, meta);
    emit("source", {
      api_name: apiName,
      taint_ids: meta.taint_ids,
      parent_taint_ids: [],
      stack_trace: stack,
      value_preview: preview(value),
    });
    return value;
  }

  function markTransform(apiName, args, value, targetValue) {
    const stack = captureStack();
    const parents = parentIdsFromArgs(args);
    if (!parents.length) return value;
    const meta = createMeta(apiName, parents);
    markValue(targetValue === undefined ? value : targetValue, meta);
    emit("transform", {
      api_name: apiName,
      taint_ids: meta.taint_ids,
      parent_taint_ids: parents,
      stack_trace: stack,
      value_preview: preview(targetValue === undefined ? value : targetValue),
    });
    return value;
  }

  function emitSink(apiName, sinkKind, sinkField, value, requestInfo) {
    const metas = collectMetas(value, 2);
    if (!metas.length) return;
    const taintIds = uniqueIds(metas.flatMap((item) => item.taint_ids || []));
    const parentIds = uniqueIds(metas.flatMap((item) => item.parent_taint_ids || []));
    emit("sink", {
      api_name: apiName,
      taint_ids: taintIds,
      parent_taint_ids: parentIds,
      stack_trace: captureStack(),
      value_preview: preview(value),
      sink: {
        request_id: requestInfo && requestInfo.request_id ? requestInfo.request_id : "",
        sink_field: sinkField || "<body>",
        sink_kind: sinkKind || "unknown",
        request_url: requestInfo && requestInfo.request_url ? requestInfo.request_url : "",
        request_method: requestInfo && requestInfo.request_method ? requestInfo.request_method : "",
      },
    });
  }

  function spoofNativeToString(fn, name) {
    const nativeStr = "function " + (name || fn.name || "") + "() { [native code] }";
    try {
      Object.defineProperty(fn, "toString", {
        value: function toString() { return nativeStr; },
        writable: false,
        configurable: false,
        enumerable: false,
      });
    } catch (_e) {}
    return fn;
  }

  function patch(path, factory) {
    const parts = String(path).split(".");
    const prop = parts.pop();
    let host = window;
    for (const key of parts) {
      host = host && host[key];
    }
    if (!host || typeof host[prop] !== "function") return;
    try {
      const original = host[prop];
      const replacement = factory(original, host, path);
      spoofNativeToString(replacement, original.name || prop);
      host[prop] = replacement;
    } catch (_error) {}
  }

  function patchSync(path, onResult) {
    patch(path, (orig, host, apiName) => function(...args) {
      const result = orig.apply(host || this, args);
      const stack = captureStack();
      emitRawCall(apiName, args, result, stack);
      if (typeof onResult === "function") onResult.call(this, args, result, apiName);
      return result;
    });
  }

  function patchAsync(path, onResult) {
    patch(path, (orig, host, apiName) => async function(...args) {
      const result = await orig.apply(host || this, args);
      const stack = captureStack();
      emitRawCall(apiName, args, result, stack);
      if (typeof onResult === "function") onResult.call(this, args, result, apiName);
      return result;
    });
  }

  function readRequestInfo(input, init, requestId) {
    let requestUrl = "";
    let requestMethod = "";
    if (typeof input === "string") requestUrl = input;
    if (input && typeof input === "object" && typeof input.url === "string") requestUrl = input.url;
    if (init && typeof init === "object" && init.method) requestMethod = String(init.method).toUpperCase();
    if (!requestMethod && input && typeof input === "object" && input.method) requestMethod = String(input.method).toUpperCase();
    return {
      request_id: requestId,
      request_url: requestUrl || "",
      request_method: requestMethod || "GET",
    };
  }

  function emitFetchSinks(input, init, requestInfo) {
    let headers = null;
    let body = undefined;
    if (init && typeof init === "object") {
      headers = init.headers != null ? init.headers : headers;
      body = init.body !== undefined ? init.body : body;
    }
    if (!headers && input && typeof input === "object" && input.headers) headers = input.headers;
    if (body === undefined && input && typeof input === "object" && "body" in input) body = input.body;

    if (headers instanceof Headers) {
      for (const [key, value] of headers.entries()) emitSink("window.fetch", "header", key, value, requestInfo);
    } else if (Array.isArray(headers)) {
      for (const pair of headers) if (Array.isArray(pair) && pair.length >= 2) emitSink("window.fetch", "header", String(pair[0]), pair[1], requestInfo);
    } else if (headers && typeof headers === "object") {
      for (const [key, value] of Object.entries(headers)) emitSink("window.fetch", "header", key, value, requestInfo);
    }

    if (requestInfo.request_url) {
      try {
        const url = new URL(requestInfo.request_url, window.location.href);
        for (const [key, value] of url.searchParams.entries()) emitSink("window.fetch", "query", key, value, requestInfo);
      } catch (_error) {}
    }

    if (body instanceof URLSearchParams || body instanceof FormData) {
      for (const [key, value] of body.entries()) emitSink("window.fetch", "body", key, value, requestInfo);
    } else if (body !== undefined) {
      emitSink("window.fetch", "body", "<body>", body, requestInfo);
    }
  }

  patchSync("Date.now", function(_args, result, apiName) {
    markSource(apiName, result);
  });
  patchSync("Math.random", function(_args, result, apiName) {
    markSource(apiName, result);
  });
  patchSync("crypto.getRandomValues", function(args, result, apiName) {
    markSource(apiName, result || args[0]);
  });
  patchSync("window.btoa", function(args, result, apiName) {
    markTransform(apiName, args, result);
  });
  patchSync("window.atob", function(args, result, apiName) {
    markTransform(apiName, args, result);
  });
  patchSync("JSON.stringify", function(args, result, apiName) {
    markTransform(apiName, args, result);
  });
  patchSync("TextEncoder.prototype.encode", function(args, result, apiName) {
    markTransform(apiName, args, result);
  });
  patchSync("URLSearchParams.prototype.append", function(args, _result, apiName) {
    markTransform(apiName, args, this, this);
  });
  patchSync("URLSearchParams.prototype.set", function(args, _result, apiName) {
    markTransform(apiName, args, this, this);
  });
  patchSync("FormData.prototype.append", function(args, _result, apiName) {
    markTransform(apiName, args, this, this);
  });
  patchSync("Headers.prototype.append", function(args, _result, apiName) {
    markTransform(apiName, args, this, this);
  });
  patchSync("Headers.prototype.set", function(args, _result, apiName) {
    markTransform(apiName, args, this, this);
  });
  patchSync("HTMLCanvasElement.prototype.toDataURL", function(_args, result, apiName) {
    markSource(apiName, result);
  });
  patchSync("CanvasRenderingContext2D.prototype.getImageData", function(_args, result, apiName) {
    markSource(apiName, result);
  });
  patchSync("WebGLRenderingContext.prototype.readPixels", function(args, _result, apiName) {
    if (args.length) markSource(apiName, args[args.length - 1]);
  });
  patchSync("WebGL2RenderingContext.prototype.readPixels", function(args, _result, apiName) {
    if (args.length) markSource(apiName, args[args.length - 1]);
  });
  patchAsync("crypto.subtle.digest", function(args, result, apiName) {
    markTransform(apiName, args, result);
  });
  patchAsync("crypto.subtle.sign", function(args, result, apiName) {
    markTransform(apiName, args, result);
  });
  patchAsync("crypto.subtle.encrypt", function(args, result, apiName) {
    markTransform(apiName, args, result);
  });
  patchAsync("crypto.subtle.decrypt", function(args, result, apiName) {
    markTransform(apiName, args, result);
  });

  patch("window.fetch", (orig, host, apiName) => async function(input, init) {
    const requestInfo = readRequestInfo(input, init, nextRequestId());
    emitFetchSinks(input, init, requestInfo);
    const result = await orig.apply(host || this, arguments);
    emitRawCall(apiName, Array.from(arguments), result, captureStack());
    return result;
  });

  patch("navigator.sendBeacon", (orig, host, apiName) => function(url, data) {
    const requestInfo = {
      request_id: nextRequestId(),
      request_url: typeof url === "string" ? url : "",
      request_method: "POST",
    };
    emitSink(apiName, "body", "<body>", data, requestInfo);
    const result = orig.apply(host || this, arguments);
    emitRawCall(apiName, Array.from(arguments), result, captureStack());
    return result;
  });

  patch("XMLHttpRequest.prototype.open", (orig, host, apiName) => function(method, url) {
    const state = {
      request_id: nextRequestId(),
      request_method: method ? String(method).toUpperCase() : "GET",
      request_url: typeof url === "string" ? url : "",
    };
    XHR_STATE.set(this, state);
    const result = orig.apply(host || this, arguments);
    emitRawCall(apiName, Array.from(arguments), result, captureStack());
    return result;
  });

  patch("XMLHttpRequest.prototype.setRequestHeader", (orig, host, apiName) => function(name, value) {
    const state = XHR_STATE.get(this) || { request_id: nextRequestId(), request_method: "GET", request_url: "" };
    XHR_STATE.set(this, state);
    emitSink(apiName, "header", String(name), value, state);
    const result = orig.apply(host || this, arguments);
    emitRawCall(apiName, Array.from(arguments), result, captureStack());
    return result;
  });

  patch("XMLHttpRequest.prototype.send", (orig, host, apiName) => function(body) {
    const state = XHR_STATE.get(this) || { request_id: nextRequestId(), request_method: "POST", request_url: "" };
    XHR_STATE.set(this, state);
    emitSink(apiName, "body", "<body>", body, state);
    const result = orig.apply(host || this, arguments);
    emitRawCall(apiName, Array.from(arguments), result, captureStack());
    return result;
  });

  for (const target of hookTargets) {
    if (target.indexOf("window.fetch") >= 0 || target.indexOf("XMLHttpRequest") >= 0 || target.indexOf("navigator.sendBeacon") >= 0) continue;
  }
})();
"""
        return (
            template
            .replace("__HOOK_TARGETS__", json.dumps(targets, ensure_ascii=False))
            .replace("__HOOK_BINDING__", json.dumps(binding_name, ensure_ascii=False))
        )

    def get_intercepts(self) -> list[HookIntercept]:
        return list(self.intercepts)

    def get_taint_events(self) -> list[TaintEvent]:
        return list(self.taint_events)

    def clear(self) -> None:
        self.intercepts.clear()
        self.taint_events.clear()
        self._sequence = 0
