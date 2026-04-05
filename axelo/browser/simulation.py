from __future__ import annotations

import json
from typing import Any

from axelo.models.target import BrowserProfile


SIMULATION_INIT_SCRIPT_TEMPLATE = r"""
(() => {
  const root = window;
  // Short, non-toolchain-branded names for the diagnostic API objects.
  const envName = "__sim_env__";
  const interactionName = "__sim_ia__";
  // Use a plain non-enumerable property instead of a global Symbol registry
  // entry so that named-symbol lookups reveal nothing about this script.
  const _markProp = "_sp_v2_";
  if (root[_markProp] === true && root[envName] && root[interactionName]) return;
  Object.defineProperty(root, _markProp, {value: true, enumerable: false, configurable: false, writable: false});
  // WeakSet used to track wrapped canvas prototypes without leaking a named
  // symbol into the global Symbol registry.
  const _wrapRegistry = new WeakSet();

  const config = __AXELO_SIMULATION_CONFIG__;
  const diagnostics = [];
  const MAX_DIAGNOSTICS = 100;
  const own = Object.prototype.hasOwnProperty;

  const clone = (value) => {
    if (value === undefined) return null;
    if (value === null) return null;
    return JSON.parse(JSON.stringify(value));
  };

  const pushDiagnostic = (scope, message, detail) => {
    diagnostics.push({
      ts: new Date().toISOString(),
      scope: String(scope || "runtime"),
      message: String(message || "unknown"),
      detail: detail == null ? null : clone(detail),
    });
    if (diagnostics.length > MAX_DIAGNOSTICS) diagnostics.splice(0, diagnostics.length - MAX_DIAGNOSTICS);
  };

  const safeDefine = (target, property, descriptor) => {
    try {
      Object.defineProperty(target, property, {
        configurable: true,
        enumerable: false,
        ...descriptor,
      });
      return true;
    } catch (error) {
      pushDiagnostic("define", `Failed to define ${String(property)}`, { error: error && error.message ? error.message : String(error) });
      return false;
    }
  };

  const clampNumber = (value, min, max, fallback) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return fallback;
    return Math.min(max, Math.max(min, numeric));
  };

  const envConfig = clone(config.environmentSimulation || {}) || {};
  const interactionConfig = clone(config.interactionSimulation || {}) || {};
  const navigatorTarget = Object.getPrototypeOf(navigator) || navigator;
  const webglConfig = envConfig.webgl || {};
  const mediaConfig = envConfig.media || {};
  const pointerConfig = interactionConfig.pointer || {};

  const state = {
    initializedAt: new Date().toISOString(),
    diagnostics,
    webgl: {
      realContextCount: 0,
      fallbackContextCount: 0,
      errorCount: 0,
    },
    interaction: {
      lastPathSummary: null,
      lastDispatchSummary: null,
    },
  };

  const DEFAULT_WEBGL_CONSTANTS = {
    ALIASED_LINE_WIDTH_RANGE: 33902,
    ALIASED_POINT_SIZE_RANGE: 33901,
    MAX_COMBINED_TEXTURE_IMAGE_UNITS: 35661,
    MAX_CUBE_MAP_TEXTURE_SIZE: 34076,
    MAX_FRAGMENT_UNIFORM_VECTORS: 36349,
    MAX_RENDERBUFFER_SIZE: 34024,
    MAX_TEXTURE_IMAGE_UNITS: 34930,
    MAX_TEXTURE_SIZE: 3379,
    MAX_VARYING_VECTORS: 36348,
    MAX_VERTEX_ATTRIBS: 34921,
    MAX_VERTEX_TEXTURE_IMAGE_UNITS: 35660,
    MAX_VERTEX_UNIFORM_VECTORS: 36347,
  };

  const DEFAULT_WEBGL_MINIMUMS = {
    ALIASED_LINE_WIDTH_RANGE: [1, 1],
    ALIASED_POINT_SIZE_RANGE: [1, 1],
    MAX_COMBINED_TEXTURE_IMAGE_UNITS: 8,
    MAX_CUBE_MAP_TEXTURE_SIZE: 1024,
    MAX_FRAGMENT_UNIFORM_VECTORS: 16,
    MAX_RENDERBUFFER_SIZE: 1024,
    MAX_TEXTURE_IMAGE_UNITS: 8,
    MAX_TEXTURE_SIZE: 2048,
    MAX_VARYING_VECTORS: 8,
    MAX_VERTEX_ATTRIBS: 8,
    MAX_VERTEX_TEXTURE_IMAGE_UNITS: 0,
    MAX_VERTEX_UNIFORM_VECTORS: 128,
  };

  const minimumParameterMap = (() => {
    const provided = webglConfig.minimumParameters || {};
    const resolved = {};
    for (const [name, numeric] of Object.entries(DEFAULT_WEBGL_CONSTANTS)) {
      resolved[numeric] = own.call(provided, name) ? clone(provided[name]) : clone(DEFAULT_WEBGL_MINIMUMS[name]);
    }
    return resolved;
  })();

  const installMediaFixtures = () => {
    const colorScheme = envConfig.colorScheme || "light";
    const reducedMotion = envConfig.reducedMotion || "no-preference";
    const originalMatchMedia = typeof root.matchMedia === "function" ? root.matchMedia.bind(root) : null;

    const resolveMediaMatch = (query) => {
      const normalized = String(query || "").toLowerCase();
      if (normalized.includes("prefers-color-scheme")) {
        if (normalized.includes("dark")) return colorScheme === "dark";
        if (normalized.includes("light")) return colorScheme !== "dark";
      }
      if (normalized.includes("prefers-reduced-motion")) {
        if (normalized.includes("reduce")) return reducedMotion === "reduce";
        if (normalized.includes("no-preference")) return reducedMotion !== "reduce";
      }
      if (normalized.includes("(pointer: coarse)")) return (mediaConfig.pointer || "fine") === "coarse";
      if (normalized.includes("(pointer: fine)")) return (mediaConfig.pointer || "fine") === "fine";
      if (normalized.includes("(hover: hover)")) return (mediaConfig.hover || "hover") === "hover";
      if (normalized.includes("(hover: none)")) return (mediaConfig.hover || "hover") === "none";
      if (normalized.includes("(any-pointer: coarse)")) return (mediaConfig.anyPointer || mediaConfig.pointer || "fine") === "coarse";
      if (normalized.includes("(any-pointer: fine)")) return (mediaConfig.anyPointer || mediaConfig.pointer || "fine") === "fine";
      if (normalized.includes("(any-hover: hover)")) return (mediaConfig.anyHover || mediaConfig.hover || "hover") === "hover";
      if (normalized.includes("(any-hover: none)")) return (mediaConfig.anyHover || mediaConfig.hover || "hover") === "none";
      return null;
    };

    const createMediaQueryList = (query, matches) => {
      const listeners = new Set();
      return {
        media: String(query),
        matches: Boolean(matches),
        onchange: null,
        addListener(listener) {
          if (typeof listener === "function") listeners.add(listener);
        },
        removeListener(listener) {
          listeners.delete(listener);
        },
        addEventListener(type, listener) {
          if (type === "change" && typeof listener === "function") listeners.add(listener);
        },
        removeEventListener(type, listener) {
          if (type === "change") listeners.delete(listener);
        },
        dispatchEvent(event) {
          const payload = event || { matches: Boolean(matches), media: String(query) };
          for (const listener of Array.from(listeners)) {
            try {
              listener.call(this, payload);
            } catch (error) {
              pushDiagnostic("media", "Media listener failed", { error: error && error.message ? error.message : String(error) });
            }
          }
          if (typeof this.onchange === "function") {
            try {
              this.onchange.call(this, payload);
            } catch (error) {
              pushDiagnostic("media", "Media onchange failed", { error: error && error.message ? error.message : String(error) });
            }
          }
          return true;
        },
      };
    };

    safeDefine(root, "matchMedia", {
      value(query) {
        const resolved = resolveMediaMatch(query);
        if (resolved !== null) return createMediaQueryList(query, resolved);
        if (originalMatchMedia) return originalMatchMedia(query);
        return createMediaQueryList(query, false);
      },
      writable: false,
    });

    if (navigator.deviceMemory === undefined) {
      safeDefine(navigatorTarget, "deviceMemory", {
        get() {
          return clampNumber(mediaConfig.deviceMemory, 1, 64, 8);
        },
      });
    }
    if (navigator.hardwareConcurrency === undefined) {
      safeDefine(navigatorTarget, "hardwareConcurrency", {
        get() {
          return Math.round(clampNumber(mediaConfig.hardwareConcurrency, 1, 128, 8));
        },
      });
    }
    if (navigator.maxTouchPoints === undefined) {
      safeDefine(navigatorTarget, "maxTouchPoints", {
        get() {
          return Math.round(clampNumber(mediaConfig.maxTouchPoints, 0, 16, 0));
        },
      });
    }
    if (navigator.connection === undefined) {
      const connection = Object.freeze({
        effectiveType: String(mediaConfig.connection && mediaConfig.connection.effectiveType ? mediaConfig.connection.effectiveType : "4g"),
        rtt: Math.round(clampNumber(mediaConfig.connection && mediaConfig.connection.rtt, 1, 5000, 50)),
        downlink: clampNumber(mediaConfig.connection && mediaConfig.connection.downlink, 0.1, 1000, 10),
        saveData: Boolean(mediaConfig.connection && mediaConfig.connection.saveData),
        addEventListener() {},
        removeEventListener() {},
        dispatchEvent() {
          return true;
        },
      });
      safeDefine(navigatorTarget, "connection", {
        get() {
          return connection;
        },
      });
    }
  };

  const installBatteryFixture = () => {
    if (envConfig.enabled === false) return;
    const batteryConfig = envConfig.battery || {};
    if (batteryConfig.enabled === false) return;
    const battery = Object.freeze({
      charging: batteryConfig.charging !== false,
      chargingTime: clampNumber(batteryConfig.chargingTime, 0, 86400, 0),
      dischargingTime: batteryConfig.dischargingTime == null ? Infinity : clampNumber(batteryConfig.dischargingTime, 0, 86400 * 30, Infinity),
      level: clampNumber(batteryConfig.level, 0, 1, 1),
      onchargingchange: null,
      onchargingtimechange: null,
      ondischargingtimechange: null,
      onlevelchange: null,
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent() {
        return true;
      },
    });
    safeDefine(navigatorTarget, "getBattery", {
      value() {
        return Promise.resolve(battery);
      },
      writable: false,
    });
  };

  // A realistic subset of extensions a desktop Chrome WebGL context exposes.
  const WEBGL_EXTENSIONS = [
    "ANGLE_instanced_arrays",
    "EXT_blend_minmax",
    "EXT_color_buffer_half_float",
    "EXT_frag_depth",
    "EXT_shader_texture_lod",
    "EXT_texture_compression_bptc",
    "EXT_texture_compression_rgtc",
    "EXT_texture_filter_anisotropic",
    "WEBKIT_EXT_texture_filter_anisotropic",
    "EXT_sRGB",
    "KHR_parallel_shader_compile",
    "OES_element_index_uint",
    "OES_fbo_render_mipmap",
    "OES_standard_derivatives",
    "OES_texture_float",
    "OES_texture_float_linear",
    "OES_texture_half_float",
    "OES_texture_half_float_linear",
    "OES_vertex_array_object",
    "WEBGL_color_buffer_float",
    "WEBGL_compressed_texture_s3tc",
    "WEBGL_compressed_texture_s3tc_srgb",
    "WEBGL_debug_renderer_info",
    "WEBGL_debug_shaders",
    "WEBGL_depth_texture",
    "WEBGL_draw_buffers",
    "WEBGL_lose_context",
    "WEBGL_multi_draw",
  ];

  // WEBGL_debug_renderer_info constants
  const UNMASKED_VENDOR_WEBGL = 37445;
  const UNMASKED_RENDERER_WEBGL = 37446;

  const createFallbackWebGLContext = (canvas) => {
    const context = {
      canvas,
      drawingBufferWidth: Number(canvas && canvas.width) || 0,
      drawingBufferHeight: Number(canvas && canvas.height) || 0,
      getContextAttributes() {
        return {
          alpha: true,
          antialias: true,
          depth: true,
          desynchronized: false,
          failIfMajorPerformanceCaveat: false,
          powerPreference: "default",
          premultipliedAlpha: true,
          preserveDrawingBuffer: false,
          stencil: false,
          xrCompatible: false,
        };
      },
      getSupportedExtensions() {
        return WEBGL_EXTENSIONS.slice();
      },
      getExtension(name) {
        const n = String(name || "").trim();
        if (n === "WEBGL_debug_renderer_info") {
          return Object.freeze({
            UNMASKED_VENDOR_WEBGL,
            UNMASKED_RENDERER_WEBGL,
          });
        }
        if (n === "WEBGL_lose_context") {
          return Object.freeze({loseContext() {}, restoreContext() {}});
        }
        if (WEBGL_EXTENSIONS.indexOf(n) !== -1) {
          return Object.freeze({});
        }
        return null;
      },
      getParameter(parameter) {
        try {
          if (parameter === UNMASKED_VENDOR_WEBGL) {
            return String(webglConfig.vendor || "Google Inc. (Intel)");
          }
          if (parameter === UNMASKED_RENDERER_WEBGL) {
            return String(webglConfig.renderer || "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)");
          }
          if (own.call(minimumParameterMap, parameter)) return clone(minimumParameterMap[parameter]);
          return null;
        } catch (error) {
          state.webgl.errorCount += 1;
          pushDiagnostic("webgl", "Fallback getParameter failed", {
            error: error && error.message ? error.message : String(error),
            parameter,
          });
          return null;
        }
      },
      isContextLost() {
        return false;
      },
      getError() {
        return 0;
      },
      finish() {},
      flush() {},
      viewport() {},
      clear() {},
      clearColor() {},
      enable() {},
      disable() {},
      scissor() {},
      blendFunc() {},
      createBuffer() {
        return {};
      },
      bindBuffer() {},
      bufferData() {},
      createTexture() {
        return {};
      },
      bindTexture() {},
      texImage2D() {},
      texParameteri() {},
      createShader() {
        return {};
      },
      shaderSource() {},
      compileShader() {},
      createProgram() {
        return {};
      },
      attachShader() {},
      linkProgram() {},
      useProgram() {},
      drawArrays() {},
      drawElements() {},
    };
    return new Proxy(context, {
      get(target, property) {
        if (own.call(target, property)) return target[property];
        if (typeof property === "string" && own.call(DEFAULT_WEBGL_CONSTANTS, property)) return DEFAULT_WEBGL_CONSTANTS[property];
        return () => null;
      },
    });
  };

  const wrapCanvasGetContext = (host) => {
    if (!host || typeof host.getContext !== "function") return;
    if (_wrapRegistry.has(host)) return;
    const original = host.getContext;
    safeDefine(host, "getContext", {
      value(type, ...args) {
        const requested = String(type || "").toLowerCase();
        if (requested !== "webgl" && requested !== "experimental-webgl" && requested !== "webgl2") {
          return original.apply(this, [type, ...args]);
        }
        try {
          const context = original.apply(this, [type, ...args]);
          if (context) {
            state.webgl.realContextCount += 1;
            return context;
          }
        } catch (error) {
          state.webgl.errorCount += 1;
          pushDiagnostic("webgl", "Context creation failed", { error: error && error.message ? error.message : String(error), requested });
        }
        if (webglConfig.enabled === false) return null;
        state.webgl.fallbackContextCount += 1;
        return createFallbackWebGLContext(this);
      },
      writable: false,
    });
    _wrapRegistry.add(host);
  };

  const makeSeededRng = (seed) => {
    let value = (Number(seed) || 1) >>> 0;
    if (!value) value = 1;
    return () => {
      value = (value * 1664525 + 1013904223) >>> 0;
      return value / 4294967296;
    };
  };

  const easeInOut = (value) => {
    const t = clampNumber(value, 0, 1, 0);
    return -(Math.cos(Math.PI * t) - 1) / 2;
  };

  const resolveBounds = (bounds) => {
    const width = Math.max(0, root.innerWidth || (document.documentElement && document.documentElement.clientWidth) || 0);
    const height = Math.max(0, root.innerHeight || (document.documentElement && document.documentElement.clientHeight) || 0);
    return {
      minX: clampNumber(bounds && bounds.minX, 0, width || 1, 0),
      minY: clampNumber(bounds && bounds.minY, 0, height || 1, 0),
      maxX: clampNumber(bounds && bounds.maxX, 0, width || 1, width),
      maxY: clampNumber(bounds && bounds.maxY, 0, height || 1, height),
    };
  };

  const normalizePoint = (point, fallback) => {
    const candidate = point || fallback || { x: 0, y: 0 };
    return {
      x: clampNumber(candidate.x, -100000, 100000, fallback ? fallback.x : 0),
      y: clampNumber(candidate.y, -100000, 100000, fallback ? fallback.y : 0),
    };
  };

  const clampPointToBounds = (point, bounds) => ({
    x: clampNumber(point.x, bounds.minX, bounds.maxX, bounds.minX),
    y: clampNumber(point.y, bounds.minY, bounds.maxY, bounds.minY),
  });

  const normalizeTracePoints = (input) => {
    const source = Array.isArray(input && input.points) ? input.points : Array.isArray(input) ? input : [];
    const output = [];
    let lastTs = 0;
    for (let index = 0; index < source.length; index += 1) {
      const item = source[index] || {};
      const x = Number(item.x);
      const y = Number(item.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      let ts = Number(item.ts);
      if (!Number.isFinite(ts)) {
        const dt = Number(item.dt);
        ts = Number.isFinite(dt) ? lastTs + dt : index * 16;
      }
      ts = Math.max(0, Math.round(ts));
      lastTs = ts;
      output.push({
        x: Number(x.toFixed(2)),
        y: Number(y.toFixed(2)),
        ts,
      });
    }
    return output;
  };

  const buildPointerPath = (options) => {
    const runtimeOptions = options || {};
    const seed = Math.round(clampNumber(runtimeOptions.seed, 1, 2147483647, pointerConfig.defaultSeed || interactionConfig.defaultSeed || 1337));
    const sampleRateHz = Math.round(clampNumber(runtimeOptions.sampleRateHz, 1, 1000, pointerConfig.sampleRateHz || 60));
    const requestedDuration = Math.round(clampNumber(runtimeOptions.durationMs, 16, 600000, pointerConfig.durationMs || 1200));
    const explicitPoints = Math.round(clampNumber(runtimeOptions.points, 0, 10000, 0));
    const jitterPx = clampNumber(runtimeOptions.jitterPx, 0, 200, pointerConfig.jitterPx || 1.25);
    const curvature = clampNumber(runtimeOptions.curvature, 0, 2, pointerConfig.curvature || 0.18);
    const hoverPauseMs = Math.round(clampNumber(runtimeOptions.hoverPauseMs, 0, 60000, pointerConfig.hoverPauseMs || 0));
    const bounds = resolveBounds(runtimeOptions.bounds || null);
    const width = Math.max(1, bounds.maxX - bounds.minX);
    const height = Math.max(1, bounds.maxY - bounds.minY);
    const start = clampPointToBounds(
      normalizePoint(runtimeOptions.start, { x: bounds.minX + width * 0.2, y: bounds.minY + height * 0.35 }),
      bounds,
    );
    const end = clampPointToBounds(
      normalizePoint(runtimeOptions.end, { x: bounds.minX + width * 0.8, y: bounds.minY + height * 0.6 }),
      bounds,
    );
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const nx = -dy / distance;
    const ny = dx / distance;
    const steps = explicitPoints > 1 ? explicitPoints : Math.max(8, Math.round((requestedDuration / 1000) * sampleRateHz));
    const rng = makeSeededRng(seed);
    const path = [];

    for (let index = 0; index < steps; index += 1) {
      const t = steps === 1 ? 1 : index / (steps - 1);
      const eased = easeInOut(t);
      const wave = Math.sin(Math.PI * eased) * curvature * distance;
      const noise = ((rng() - 0.5) * 2 * jitterPx) + ((rng() - 0.5) * jitterPx * 0.5);
      const point = clampPointToBounds({
        x: start.x + dx * eased + nx * (wave + noise),
        y: start.y + dy * eased + ny * (wave + noise),
      }, bounds);
      path.push({
        x: Number(point.x.toFixed(2)),
        y: Number(point.y.toFixed(2)),
        ts: Math.round(requestedDuration * t),
      });
    }
    if (hoverPauseMs > 0 && path.length > 0) {
      path.push({
        x: path[path.length - 1].x,
        y: path[path.length - 1].y,
        ts: requestedDuration + hoverPauseMs,
      });
    }
    const durationMs = path.length > 0 ? path[path.length - 1].ts : requestedDuration;
    state.interaction.lastPathSummary = {
      seed,
      points: path.length,
      durationMs,
      bounds: clone(bounds),
    };
    return {
      seed,
      points: path,
      durationMs,
      sampleRateHz,
      start,
      end,
      bounds,
    };
  };

  const dispatchPointerPath = (pathInput, options) => {
    const runtimeOptions = options || {};
    const points = normalizeTracePoints(pathInput);
    let emitted = 0;
    for (const point of points) {
      const target = document.elementFromPoint(point.x, point.y) || document.body || document.documentElement;
      if (!target) continue;
      const eventInit = {
        bubbles: true,
        cancelable: true,
        clientX: point.x,
        clientY: point.y,
        screenX: point.x,
        screenY: point.y,
        buttons: Math.round(clampNumber(runtimeOptions.buttons, 0, 16, 1)),
        pointerId: 1,
        pointerType: "mouse",
        isPrimary: true,
      };
      try {
        if (typeof root.PointerEvent === "function") {
          target.dispatchEvent(new root.PointerEvent("pointermove", eventInit));
          emitted += 1;
        }
        target.dispatchEvent(new root.MouseEvent("mousemove", eventInit));
        emitted += 1;
      } catch (error) {
        pushDiagnostic("interaction", "Dispatch failed", { error: error && error.message ? error.message : String(error) });
      }
    }
    state.interaction.lastDispatchSummary = {
      points: points.length,
      eventsEmitted: emitted,
      mode: "dispatch",
    };
    return {
      points: points.length,
      eventsEmitted: emitted,
      mode: "dispatch",
    };
  };

  // ── Stealth fixes ──────────────────────────────────────────────────────────
  // These patches suppress the most widely-probed automation signals.

  const installStealthFixtures = () => {
    // 1. navigator.webdriver
    // Headless Chromium exposes navigator.webdriver=true by default.  Remove it
    // so that the property evaluates to undefined rather than true.
    try {
      Object.defineProperty(navigator, "webdriver", {
        get: () => undefined,
        configurable: true,
        enumerable: true,
      });
    } catch (_e) {
      pushDiagnostic("stealth", "Could not redefine navigator.webdriver", {});
    }

    // 2. window.chrome stub
    // Real Chrome exposes window.chrome; headless mode omits it entirely which
    // is a trivially detectable signal.
    if (!root.chrome) {
      try {
        const _chrome = {
          app: {
            isInstalled: false,
            getDetails: function() { return null; },
            runningState: function() { return "cannot_run"; },
            InstallState: {DISABLED: "disabled", INSTALLED: "installed", NOT_INSTALLED: "not_installed"},
          },
          runtime: {
            id: undefined,
            connect: function() { return null; },
            sendMessage: function() {},
            onConnect: {addListener: function() {}, removeListener: function() {}, hasListener: function() { return false; }},
            onMessage: {addListener: function() {}, removeListener: function() {}, hasListener: function() { return false; }},
          },
          loadTimes: function() { return {}; },
          csi: function() { return {}; },
        };
        Object.defineProperty(root, "chrome", {
          value: _chrome,
          enumerable: true,
          configurable: true,
          writable: true,
        });
      } catch (_e) {
        pushDiagnostic("stealth", "Could not define window.chrome", {});
      }
    }

    // 3. navigator.plugins
    // Headless Chrome returns an empty PluginArray which is a well-known signal.
    // We inject a minimal set matching what a typical desktop Chrome exposes.
    try {
      if (!navigator.plugins || navigator.plugins.length === 0) {
        const _pluginNames = [
          "PDF Viewer",
          "Chrome PDF Viewer",
          "Chromium PDF Viewer",
          "Microsoft Edge PDF Viewer",
          "WebKit built-in PDF",
        ];
        // Build a plain array-like object that mimics PluginArray
        const _plugins = Object.assign(Object.create(null), {
          length: _pluginNames.length,
          item: function(i) { return this[i] || null; },
          namedItem: function(n) {
            for (let k = 0; k < _pluginNames.length; k++) {
              if (_pluginNames[k] === n) return this[k] || null;
            }
            return null;
          },
          refresh: function() {},
        });
        for (let _i = 0; _i < _pluginNames.length; _i++) {
          const _p = Object.assign(Object.create(null), {
            name: _pluginNames[_i],
            filename: "internal-pdf-viewer",
            description: "Portable Document Format",
            length: 1,
          });
          _plugins[_i] = _p;
        }
        Object.defineProperty(navigator, "plugins", {
          get: function() { return _plugins; },
          configurable: true,
          enumerable: true,
        });
      }
    } catch (_e) {
      pushDiagnostic("stealth", "Could not redefine navigator.plugins", {});
    }

    // 4. navigator.languages consistency
    // Ensure navigator.languages is not empty; it should reflect the locale.
    try {
      if (!navigator.languages || navigator.languages.length === 0) {
        const _locale = String(envConfig.profileName || "desktop");
        const _lang = _locale === "mobile" ? ["zh-CN", "zh", "en"] : ["zh-CN", "zh", "en-US", "en"];
        Object.defineProperty(navigator, "languages", {
          get: function() { return _lang; },
          configurable: true,
          enumerable: true,
        });
      }
    } catch (_e) {
      pushDiagnostic("stealth", "Could not redefine navigator.languages", {});
    }
  };

  // ── End stealth fixes ───────────────────────────────────────────────────────

  installStealthFixtures();
  installMediaFixtures();
  installBatteryFixture();
  wrapCanvasGetContext(root.HTMLCanvasElement && root.HTMLCanvasElement.prototype);
  wrapCanvasGetContext(root.OffscreenCanvas && root.OffscreenCanvas.prototype);

  const envApi = Object.freeze({
    config: Object.freeze(clone(envConfig) || {}),
    diagnostics,
    getStatus() {
      return {
        initializedAt: state.initializedAt,
        profileName: envConfig.profileName || null,
        colorScheme: envConfig.colorScheme || null,
        reducedMotion: envConfig.reducedMotion || null,
        battery: {
          available: typeof navigator.getBattery === "function",
          level: envConfig.battery && envConfig.battery.level != null ? envConfig.battery.level : null,
          charging: envConfig.battery ? envConfig.battery.charging !== false : null,
        },
        media: {
          pointer: mediaConfig.pointer || null,
          hover: mediaConfig.hover || null,
          anyPointer: mediaConfig.anyPointer || mediaConfig.pointer || null,
          anyHover: mediaConfig.anyHover || mediaConfig.hover || null,
          maxTouchPoints: navigator.maxTouchPoints == null ? null : navigator.maxTouchPoints,
        },
        webgl: clone(state.webgl),
        diagnostics: diagnostics.slice(-20),
      };
    },
  });

  const interactionApi = Object.freeze({
    config: Object.freeze(clone(interactionConfig) || {}),
    buildPointerPath,
    normalizeTracePoints,
    dispatchPointerPath,
    getStatus() {
      return {
        initializedAt: state.initializedAt,
        profileName: interactionConfig.profileName || null,
        mode: interactionConfig.mode || "playwright_mouse",
        highFrequencyDispatch: Boolean(interactionConfig.highFrequencyDispatch),
        pointer: {
          defaultSeed: pointerConfig.defaultSeed || interactionConfig.defaultSeed || 1337,
          sampleRateHz: pointerConfig.sampleRateHz || 60,
          durationMs: pointerConfig.durationMs || 1200,
          jitterPx: pointerConfig.jitterPx || 1.25,
          curvature: pointerConfig.curvature || 0.18,
        },
        lastPathSummary: clone(state.interaction.lastPathSummary),
        lastDispatchSummary: clone(state.interaction.lastDispatchSummary),
      };
    },
  });

  Object.defineProperty(root, envName, {
    value: envApi,
    enumerable: false,
    configurable: false,
    writable: false,
  });
  Object.defineProperty(root, interactionName, {
    value: interactionApi,
    enumerable: false,
    configurable: false,
    writable: false,
  });
})();
"""


def build_context_options(profile: BrowserProfile) -> dict[str, Any]:
    environment = profile.environment_simulation
    options = {
        "user_agent": profile.user_agent or None,
        "viewport": {"width": profile.viewport_width, "height": profile.viewport_height},
        "locale": profile.locale,
        "timezone_id": profile.timezone,
        "extra_http_headers": profile.extra_headers,
        "ignore_https_errors": True,
        "color_scheme": environment.color_scheme,
        "reduced_motion": environment.reduced_motion,
        "device_scale_factor": environment.device_scale_factor,
        "has_touch": environment.has_touch,
        "is_mobile": environment.is_mobile,
    }
    return {key: value for key, value in options.items() if value is not None}


def _camelize(name: str) -> str:
    if name.upper() == name:
        return name
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _camelize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {_camelize(str(key)): _camelize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camelize_value(item) for item in value]
    return value


def build_simulation_payload(profile: BrowserProfile) -> dict[str, Any]:
    return {
        "environmentSimulation": _camelize_value(profile.environment_simulation.model_dump(mode="json")),
        "interactionSimulation": _camelize_value(profile.interaction_simulation.model_dump(mode="json")),
    }


def render_simulation_init_script(profile: BrowserProfile) -> str:
    payload = json.dumps(build_simulation_payload(profile), ensure_ascii=False, separators=(",", ":"))
    return SIMULATION_INIT_SCRIPT_TEMPLATE.replace("__AXELO_SIMULATION_CONFIG__", payload)
