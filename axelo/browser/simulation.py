from __future__ import annotations

import json
import secrets
from typing import Any

from axelo.models.target import BrowserProfile


SIMULATION_INIT_SCRIPT_TEMPLATE = r"""
(() => {
  const root = window;
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

  const handles = clone(config.runtimeHandles || {}) || {};
  const envName = String(handles.envName || "__axelo_env");
  const interactionName = String(handles.interactionName || "__axelo_interaction");
  const stateKey = String(handles.stateKey || (interactionName + "_state"));
  if (root[stateKey] && root[envName] && root[interactionName]) return;

  const envConfig = clone(config.environmentSimulation || {}) || {};
  const interactionConfig = clone(config.interactionSimulation || {}) || {};
  const identityConfig = clone(config.browserIdentity || {}) || {};
  const sessionConfig = clone(config.sessionRuntime || {}) || {};
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
    MAX_COMBINED_TEXTURE_IMAGE_UNITS: 32,
    MAX_CUBE_MAP_TEXTURE_SIZE: 16384,
    MAX_FRAGMENT_UNIFORM_VECTORS: 1024,
    MAX_RENDERBUFFER_SIZE: 16384,
    MAX_TEXTURE_IMAGE_UNITS: 16,
    MAX_TEXTURE_SIZE: 16384,
    MAX_VARYING_VECTORS: 30,
    MAX_VERTEX_ATTRIBS: 16,
    MAX_VERTEX_TEXTURE_IMAGE_UNITS: 16,
    MAX_VERTEX_UNIFORM_VECTORS: 4096,
  };

  const minimumParameterMap = (() => {
    const provided = webglConfig.minimumParameters || {};
    const resolved = {};
    for (const [name, numeric] of Object.entries(DEFAULT_WEBGL_CONSTANTS)) {
      resolved[numeric] = own.call(provided, name) ? clone(provided[name]) : clone(DEFAULT_WEBGL_MINIMUMS[name]);
    }
    return resolved;
  })();

  const COMMON_WEBGL_EXTENSIONS = [
    "ANGLE_instanced_arrays",
    "EXT_blend_minmax",
    "EXT_color_buffer_half_float",
    "EXT_disjoint_timer_query",
    "EXT_float_blend",
    "EXT_frag_depth",
    "EXT_shader_texture_lod",
    "EXT_sRGB",
    "EXT_texture_compression_bptc",
    "EXT_texture_filter_anisotropic",
    "OES_element_index_uint",
    "OES_standard_derivatives",
    "OES_texture_float",
    "OES_texture_float_linear",
    "OES_texture_half_float",
    "OES_texture_half_float_linear",
    "OES_vertex_array_object",
    "WEBGL_color_buffer_float",
    "WEBGL_compressed_texture_s3tc",
    "WEBGL_debug_renderer_info",
    "WEBGL_debug_shaders",
    "WEBGL_depth_texture",
    "WEBGL_draw_buffers",
    "WEBGL_lose_context",
  ];

  const defaultVendor = String(webglConfig.unmaskedVendor || identityConfig.webglVendor || "Google Inc. (Intel)");
  const defaultRenderer = String(
    webglConfig.unmaskedRenderer
      || identityConfig.webglRenderer
      || "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"
  );
  const debugRendererInfo = Object.freeze({
    UNMASKED_VENDOR_WEBGL: 37445,
    UNMASKED_RENDERER_WEBGL: 37446,
  });

  const localeTag = String(identityConfig.locale || navigator.language || "en-US");
  const acceptLanguage = String(identityConfig.acceptLanguage || localeTag);
  const preferredLanguages = Array.isArray(identityConfig.languages) && identityConfig.languages.length
    ? identityConfig.languages.map((item) => String(item))
    : (() => {
        const primary = localeTag.split("-")[0];
        const unique = [localeTag];
        if (primary && primary !== localeTag) unique.push(primary);
        if (!unique.includes("en-US")) unique.push("en-US");
        if (!unique.includes("en")) unique.push("en");
        return unique;
      })();

  const pluginEntries = Array.isArray(identityConfig.plugins) && identityConfig.plugins.length
    ? identityConfig.plugins
    : [
        {
          name: "Chrome PDF Plugin",
          filename: "internal-pdf-viewer",
          description: "Portable Document Format",
        },
        {
          name: "Chrome PDF Viewer",
          filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
          description: "",
        },
        {
          name: "Native Client",
          filename: "internal-nacl-plugin",
          description: "",
        },
      ];

  const platformFromUserAgent = (userAgentText) => {
    const normalized = String(userAgentText || "").toLowerCase();
    if (normalized.includes("iphone")) return "iPhone";
    if (normalized.includes("ipad")) return "iPad";
    if (normalized.includes("mac os x")) return "MacIntel";
    if (normalized.includes("win")) return "Win32";
    if (normalized.includes("android")) return "Linux armv8l";
    if (normalized.includes("linux")) return "Linux x86_64";
    return "Win32";
  };

  const navigatorPlatform = String(identityConfig.platform || platformFromUserAgent(identityConfig.userAgent));
  const sessionSeed = Math.round(
    clampNumber(
      sessionConfig.seed,
      1,
      2147483647,
      (typeof root.crypto !== "undefined" && root.crypto && typeof root.crypto.getRandomValues === "function")
        ? root.crypto.getRandomValues(new Uint32Array(1))[0] || 1
        : Math.floor(Math.random() * 2147483646) + 1,
    )
  );

  const createPluginArray = () => {
    const plugins = pluginEntries.map((entry) => {
      const plugin = {
        name: String(entry.name || ""),
        filename: String(entry.filename || ""),
        description: String(entry.description || ""),
        length: 0,
        item() {
          return null;
        },
        namedItem() {
          return null;
        },
      };
      safeDefine(plugin, Symbol.toStringTag, { value: "Plugin" });
      return Object.freeze(plugin);
    });
    const pluginArray = { length: plugins.length };
    plugins.forEach((plugin, index) => {
      pluginArray[index] = plugin;
    });
    safeDefine(pluginArray, "item", {
      value(index) {
        return plugins[Number(index)] || null;
      },
    });
    safeDefine(pluginArray, "namedItem", {
      value(name) {
        return plugins.find((plugin) => plugin.name === name) || null;
      },
    });
    safeDefine(pluginArray, "refresh", {
      value() {},
    });
    safeDefine(pluginArray, Symbol.iterator, {
      value: function* iteratePlugins() {
        yield* plugins;
      },
    });
    safeDefine(pluginArray, Symbol.toStringTag, { value: "PluginArray" });
    return Object.freeze(pluginArray);
  };

  const installNavigatorFixtures = () => {
    try {
      delete navigatorTarget.webdriver;
    } catch (_) {}
    safeDefine(navigatorTarget, "webdriver", {
      get() {
        return undefined;
      },
      configurable: true,
      enumerable: false,
    });
    safeDefine(navigatorTarget, "languages", {
      get() {
        return preferredLanguages.slice();
      },
    });
    safeDefine(navigatorTarget, "language", {
      get() {
        return preferredLanguages[0] || localeTag;
      },
    });
    safeDefine(navigatorTarget, "platform", {
      get() {
        return navigatorPlatform;
      },
    });
    safeDefine(navigatorTarget, "plugins", {
      get() {
        return createPluginArray();
      },
    });

    const chromeRuntime = Object.freeze({
      id: undefined,
      connect() {
        return null;
      },
      sendMessage() {
        return undefined;
      },
      onMessage: Object.freeze({
        addListener() {},
        removeListener() {},
        hasListener() {
          return false;
        },
      }),
    });
    const chromeApp = Object.freeze({
      isInstalled: false,
      InstallState: Object.freeze({
        DISABLED: "disabled",
        INSTALLED: "installed",
        NOT_INSTALLED: "not_installed",
      }),
      RunningState: Object.freeze({
        CANNOT_RUN: "cannot_run",
        READY_TO_RUN: "ready_to_run",
        RUNNING: "running",
      }),
    });
    const chromeObject = root.chrome && typeof root.chrome === "object" ? root.chrome : {};
    safeDefine(chromeObject, "runtime", { value: chromeRuntime, writable: false });
    safeDefine(chromeObject, "app", { value: chromeApp, writable: false });
    safeDefine(chromeObject, "csi", {
      value() {
        return { onloadT: Date.now(), startE: Date.now(), pageT: 1, tran: 15 };
      },
      writable: false,
    });
    safeDefine(chromeObject, "loadTimes", {
      value() {
        return {
          commitLoadTime: 0,
          finishDocumentLoadTime: 0,
          finishLoadTime: 0,
          firstPaintAfterLoadTime: 0,
          navigationType: "Other",
          requestTime: 0,
          startLoadTime: 0,
        };
      },
      writable: false,
    });
    safeDefine(root, "chrome", { value: chromeObject, writable: false });
  };

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

  const wrapWebGLContext = (context, requested) => {
    if (!context || context.__axeloWrappedWebGL) return context;
    const extensionMap = Object.freeze({
      WEBGL_debug_renderer_info: debugRendererInfo,
    });
    const wrapped = new Proxy(context, {
      get(target, property, receiver) {
        if (property === "__axeloWrappedWebGL") return true;
        if (property === "getSupportedExtensions") {
          return function getSupportedExtensions() {
            const originalExtensions = typeof target.getSupportedExtensions === "function" ? target.getSupportedExtensions.call(target) : [];
            return Array.from(new Set([...(originalExtensions || []), ...COMMON_WEBGL_EXTENSIONS]));
          };
        }
        if (property === "getExtension") {
          return function getExtension(name) {
            const key = String(name || "");
            if (own.call(extensionMap, key)) return extensionMap[key];
            return typeof target.getExtension === "function" ? target.getExtension.call(target, name) : null;
          };
        }
        if (property === "getParameter") {
          return function getParameter(parameter) {
            if (parameter === debugRendererInfo.UNMASKED_VENDOR_WEBGL) return defaultVendor;
            if (parameter === debugRendererInfo.UNMASKED_RENDERER_WEBGL) return defaultRenderer;
            if (own.call(minimumParameterMap, parameter)) {
              const originalValue = typeof target.getParameter === "function" ? target.getParameter.call(target, parameter) : null;
              if (originalValue == null || originalValue === 0) return clone(minimumParameterMap[parameter]);
            }
            return typeof target.getParameter === "function" ? target.getParameter.call(target, parameter) : null;
          };
        }
        if (typeof property === "string" && own.call(DEFAULT_WEBGL_CONSTANTS, property)) {
          return DEFAULT_WEBGL_CONSTANTS[property];
        }
        return Reflect.get(target, property, receiver);
      },
    });
    safeDefine(wrapped, Symbol.toStringTag, {
      value: requested === "webgl2" ? "WebGL2RenderingContext" : "WebGLRenderingContext",
    });
    return wrapped;
  };

  const createFallbackWebGLContext = (canvas, requested) => {
    const proto = requested === "webgl2"
      ? (root.WebGL2RenderingContext && root.WebGL2RenderingContext.prototype)
      : (root.WebGLRenderingContext && root.WebGLRenderingContext.prototype);
    const context = Object.assign(Object.create(proto || Object.prototype), {
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
        return COMMON_WEBGL_EXTENSIONS.slice();
      },
      getExtension(name) {
        if (String(name || "") === "WEBGL_debug_renderer_info") return debugRendererInfo;
        return null;
      },
      getParameter(parameter) {
        try {
          if (parameter === debugRendererInfo.UNMASKED_VENDOR_WEBGL) return defaultVendor;
          if (parameter === debugRendererInfo.UNMASKED_RENDERER_WEBGL) return defaultRenderer;
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
    });
    return wrapWebGLContext(context, requested);
  };

  const wrapCanvasGetContext = (host) => {
    if (!host || typeof host.getContext !== "function") return;
    const marker = stateKey + ":webgl.wrap";
    if (host[marker]) return;
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
            return wrapWebGLContext(context, requested);
          }
        } catch (error) {
          state.webgl.errorCount += 1;
          pushDiagnostic("webgl", "Context creation failed", { error: error && error.message ? error.message : String(error), requested });
        }
        if (webglConfig.enabled === false) return null;
        state.webgl.fallbackContextCount += 1;
        return createFallbackWebGLContext(this, requested);
      },
      writable: false,
    });
    safeDefine(host, marker, { value: true, writable: false });
  };

  const installCanvasFingerprintHooks = () => {
    const canvasHost = root.HTMLCanvasElement && root.HTMLCanvasElement.prototype;
    if (!canvasHost) return;
    const marker = stateKey + ":canvas.wrap";
    if (canvasHost[marker]) return;

    const deriveNoise = (index) => {
      const h = (((sessionSeed * 0x9e3779b9) >>> 0) + ((index * 0x6b43a9b5) >>> 0)) >>> 0;
      return ((h & 0x07) - 3.5) * 0.4;
    };
    const cloneCanvasWithNoise = (canvas) => {
      if (!canvas || !canvas.width || !canvas.height || typeof document.createElement !== "function") return null;
      try {
        const shadow = document.createElement("canvas");
        shadow.width = canvas.width;
        shadow.height = canvas.height;
        const ctx = shadow.getContext("2d", { willReadFrequently: true });
        if (!ctx) return null;
        ctx.drawImage(canvas, 0, 0);
        const width = shadow.width;
        const height = shadow.height;
        // 8 pseudo-random pixel positions distributed across canvas surface
        const lcg = (v) => (((v * 1664525 + 1013904223) >>> 0));
        let rngState = sessionSeed >>> 0;
        const probes = [];
        for (let pi = 0; pi < 8; pi++) {
          rngState = lcg(rngState);
          const px = Math.floor((rngState / 4294967296) * width);
          rngState = lcg(rngState);
          const py = Math.floor((rngState / 4294967296) * height);
          probes.push([Math.max(0, Math.min(width - 1, px)), Math.max(0, Math.min(height - 1, py))]);
        }
        probes.forEach(([x, y], index) => {
          const imageData = ctx.getImageData(x, y, 1, 1);
          imageData.data[0] = Math.max(0, Math.min(255, Math.round(imageData.data[0] + deriveNoise(index))));
          imageData.data[1] = Math.max(0, Math.min(255, Math.round(imageData.data[1] + deriveNoise(index + 3))));
          imageData.data[2] = Math.max(0, Math.min(255, Math.round(imageData.data[2] + deriveNoise(index + 6))));
          ctx.putImageData(imageData, x, y);
        });
        return shadow;
      } catch (_error) {
        return null;
      }
    };

    if (typeof canvasHost.toDataURL === "function") {
      const originalToDataURL = canvasHost.toDataURL;
      safeDefine(canvasHost, "toDataURL", {
        value(...args) {
          const shadow = cloneCanvasWithNoise(this);
          return originalToDataURL.apply(shadow || this, args);
        },
      });
    }
    if (typeof canvasHost.toBlob === "function") {
      const originalToBlob = canvasHost.toBlob;
      safeDefine(canvasHost, "toBlob", {
        value(callback, ...args) {
          const shadow = cloneCanvasWithNoise(this);
          return originalToBlob.apply(shadow || this, [callback, ...args]);
        },
      });
    }
    if (root.CanvasRenderingContext2D && root.CanvasRenderingContext2D.prototype && typeof root.CanvasRenderingContext2D.prototype.getImageData === "function") {
      const contextHost = root.CanvasRenderingContext2D.prototype;
      const originalGetImageData = contextHost.getImageData;
      safeDefine(contextHost, "getImageData", {
        value(...args) {
          const imageData = originalGetImageData.apply(this, args);
          if (!imageData || !imageData.data || imageData.data.length < 4) return imageData;
          for (let index = 0; index < Math.min(12, imageData.data.length); index += 4) {
            imageData.data[index] = Math.max(0, Math.min(255, imageData.data[index] + deriveNoise(index)));
          }
          return imageData;
        },
      });
    }
    safeDefine(canvasHost, marker, { value: true, writable: false });
  };

  const makeSeededRng = (seed) => {
    let value = (Number(seed) || 1) >>> 0;
    if (!value) value = 1;
    return () => {
      value ^= value << 13;
      value ^= value >>> 17;
      value ^= value << 5;
      value >>>= 0;
      return value / 4294967296;
    };
  };

  const minimumJerk = (value) => {
    const t = clampNumber(value, 0, 1, 0);
    return (10 * t * t * t) - (15 * t * t * t * t) + (6 * t * t * t * t * t);
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
    const seed = Math.round(
      clampNumber(
        runtimeOptions.seed,
        1,
        2147483647,
        sessionConfig.seed || pointerConfig.defaultSeed || interactionConfig.defaultSeed || sessionSeed,
      )
    );
    const sampleRateHz = Math.round(clampNumber(runtimeOptions.sampleRateHz, 1, 1000, pointerConfig.sampleRateHz || 60));
    const targetWidth = runtimeOptions.targetWidthPx || 48;
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
    const fittsMs = Math.round(200 + 150 * Math.log2(1 + distance / targetWidth));
    const requestedDuration = Math.round(clampNumber(runtimeOptions.durationMs, 16, 600000, pointerConfig.durationMs || fittsMs));
    const steps = explicitPoints > 1 ? explicitPoints : Math.max(8, Math.round((requestedDuration / 1000) * sampleRateHz));
    const rng = makeSeededRng(seed);
    const tremorHz = 5.5 + rng() * 1.5;
    const tremorAmp = 0.15 + rng() * 0.2;
    const path = [];

    for (let index = 0; index < steps; index += 1) {
      const t = steps === 1 ? 1 : index / (steps - 1);
      const eased = minimumJerk(t);
      const wave = Math.sin(Math.PI * eased) * curvature * distance;
      const noise = ((rng() - 0.5) * 2 * jitterPx) + ((rng() - 0.5) * jitterPx * 0.5);
      const tx = Math.sin(2 * Math.PI * tremorHz * t + sessionSeed) * tremorAmp;
      const ty = Math.cos(2 * Math.PI * tremorHz * t + sessionSeed * 0.7) * tremorAmp;
      let px = start.x + dx * eased + nx * (wave + noise) + tx;
      let py = start.y + dy * eased + ny * (wave + noise) + ty;
      if (t > 0.90) {
        const cf = (t - 0.90) / 0.10;
        px += (end.x - px) * cf * 0.25;
        py += (end.y - py) * cf * 0.25;
      }
      const point = clampPointToBounds({ x: px, y: py }, bounds);
      path.push({
        x: Number(point.x.toFixed(2)),
        y: Number(point.y.toFixed(2)),
        ts: Math.round(requestedDuration * t),
      });
    }
    const autoHover = Math.round(80 + Math.max(0, 40 - targetWidth) * 2.5 + rng() * 50);
    const actualHoverMs = hoverPauseMs > 0 ? hoverPauseMs : autoHover;
    if (actualHoverMs > 0 && path.length > 0) {
      path.push({
        x: path[path.length - 1].x,
        y: path[path.length - 1].y,
        ts: requestedDuration + actualHoverMs,
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

  const installPermissionsFixture = () => {
    try {
      if (!navigator.permissions || typeof navigator.permissions.query !== "function") return;
      const _originalQuery = navigator.permissions.query.bind(navigator.permissions);
      const _promptNames = new Set([
        "notifications", "clipboard-read", "clipboard-write", "push", "midi",
        "camera", "microphone", "background-sync",
        "geolocation", "accelerometer", "gyroscope", "magnetometer",
        "payment", "usb", "bluetooth", "serial", "xr-spatial-tracking",
      ]);
      safeDefine(navigator.permissions, "query", {
        value: function query(permissionDesc) {
          const name = permissionDesc && permissionDesc.name ? String(permissionDesc.name) : "";
          if (_promptNames.has(name)) {
            return Promise.resolve(Object.freeze({ state: "prompt", name, onchange: null }));
          }
          return _originalQuery(permissionDesc);
        },
        writable: false,
      });
    } catch (error) {
      pushDiagnostic("permissions", "Permissions fixture failed", { error: error && error.message ? error.message : String(error) });
    }
  };

  const installAudioContextFixture = () => {
    try {
      const AudioCtorProto = (root.AudioBuffer || (root.webkitAudioContext && root.webkitAudioContext.prototype && Object.getPrototypeOf(new root.webkitAudioContext())))
        ? root.AudioBuffer
        : null;
      if (!AudioCtorProto || typeof AudioCtorProto.prototype.getChannelData !== "function") return;
      const _origGetChannelData = AudioCtorProto.prototype.getChannelData;
      const noiseScale = 0.0000001;
      safeDefine(AudioCtorProto.prototype, "getChannelData", {
        value: function getChannelData(channel) {
          const data = _origGetChannelData.call(this, channel);
          if (data && data.length > 1) {
            const s = sessionSeed;
            data[0] += noiseScale * (((s & 0xFF) / 255) - 0.5);
            data[1] += noiseScale * ((((s >>> 8) & 0xFF) / 255) - 0.5);
          }
          return data;
        },
        writable: false,
      });
    } catch (error) {
      pushDiagnostic("audio", "AudioContext fixture failed", { error: error && error.message ? error.message : String(error) });
    }
  };

  const installWebRTCFixture = () => {
    try {
      ['RTCPeerConnection','webkitRTCPeerConnection','mozRTCPeerConnection'].forEach(function(name) {
        if (!root[name]) return;
        const fake = function() { throw new DOMException('NotSupportedError'); };
        fake.prototype = root[name].prototype;
        safeDefine(root, name, { value: fake, writable: false });
      });
    } catch(e) { pushDiagnostic("webrtc","WebRTC fixture failed",{error:e.message}); }
  };

  const installPerformanceFixture = () => {
    try {
      if (typeof performance === "undefined" || typeof performance.now !== "function") return;
      const _orig = performance.now.bind(performance);
      safeDefine(performance, 'now', {
        value: function now() {
          const raw = _orig();
          // Time-based jitter: depends on actual elapsed time + session seed → not predictable by statistical analysis
          const jitter = (Math.sin(raw * 0.001 + sessionSeed) * 0.15)
                       + (Math.cos(raw * 0.003 + sessionSeed * 1.7) * 0.08);
          return raw + jitter;
        },
        writable: false,
      });
    } catch(e) { pushDiagnostic("perf","Performance fixture failed",{error:e.message}); }
  };

  const installScreenFixture = () => {
    try {
      const vw = root.innerWidth || 1920, vh = root.innerHeight || 1080;
      const s = root.screen; if (!s) return;
      const props = {
        colorDepth: 24, pixelDepth: 24,
        availWidth: vw, availHeight: vh,
        width: vw, height: vh,
      };
      for (const k of Object.keys(props)) {
        try { Object.defineProperty(s, k, { get: (function(v){ return function(){ return v; }; })(props[k]), configurable: true }); } catch(_) {}
      }
      // orientation object — real browsers expose this
      if (!s.orientation) {
        try {
          Object.defineProperty(s, 'orientation', {
            get: function() {
              return Object.freeze({
                type: 'landscape-primary', angle: 0,
                onchange: null,
                addEventListener: function() {},
                removeEventListener: function() {},
              });
            },
            configurable: true,
          });
        } catch(_) {}
      }
    } catch(e) { pushDiagnostic("screen","Screen fixture failed",{error:e.message}); }
  };

  const installWindowSizeFixture = () => {
    try {
      const chromePx = 85 + Math.floor(sessionSeed % 20);
      safeDefine(root, 'outerWidth',  { get: function() { return (root.innerWidth  || 1920) + chromePx; } });
      safeDefine(root, 'outerHeight', { get: function() { return (root.innerHeight || 1080) + chromePx; } });
    } catch(e) { pushDiagnostic("window","Window size fixture failed",{error:e.message}); }
  };

  const installDocumentFocusFixture = () => {
    try {
      safeDefine(Document.prototype, 'hasFocus',
        { value: function hasFocus() { return true; }, writable: false });
      safeDefine(document, 'visibilityState', { get: function() { return 'visible'; } });
      safeDefine(document, 'hidden',          { get: function() { return false; } });
      safeDefine(document, 'mozHidden',       { get: function() { return false; } });
      safeDefine(document, 'webkitHidden',    { get: function() { return false; } });
    } catch(e) { pushDiagnostic("focus","Focus fixture failed",{error:e.message}); }
  };

  const installWindowNameFixture = () => {
    try {
      if (typeof root.name === 'string' && root.name !== '') {
        root.name = '';
      }
    } catch(e) {}
  };

  installNavigatorFixtures();
  installMediaFixtures();
  installBatteryFixture();
  installPermissionsFixture();
  installAudioContextFixture();
  installWebRTCFixture();
  installPerformanceFixture();
  installScreenFixture();
  installWindowSizeFixture();
  installDocumentFocusFixture();
  installWindowNameFixture();
  wrapCanvasGetContext(root.HTMLCanvasElement && root.HTMLCanvasElement.prototype);
  wrapCanvasGetContext(root.OffscreenCanvas && root.OffscreenCanvas.prototype);
  installCanvasFingerprintHooks();

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
          languages: navigator.languages || null,
          platform: navigator.platform || null,
          plugins: navigator.plugins ? navigator.plugins.length : null,
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
          defaultSeed: sessionConfig.seed || pointerConfig.defaultSeed || interactionConfig.defaultSeed || sessionSeed,
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

  Object.defineProperty(root, stateKey, {
    value: {
      envConfig,
      interactionConfig,
      diagnostics,
      state,
    },
    enumerable: false,
    configurable: false,
    writable: false,
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
    headers = dict(profile.extra_headers)
    if profile.locale and not any(str(key).lower() == "accept-language" for key in headers):
        headers["Accept-Language"] = _default_accept_language(profile.locale)
    options = {
        "user_agent": profile.user_agent or None,
        "viewport": {"width": profile.viewport_width, "height": profile.viewport_height},
        "locale": profile.locale,
        "timezone_id": profile.timezone,
        "extra_http_headers": headers or None,
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


def _default_accept_language(locale: str) -> str:
    normalized = (locale or "en-US").strip() or "en-US"
    parts = [normalized]
    primary = normalized.split("-")[0]
    if primary and primary.lower() != normalized.lower():
        parts.append(f"{primary};q=0.9")
    if normalized.lower() != "en-us":
        parts.append("en-US;q=0.8")
    if primary.lower() != "en":
        parts.append("en;q=0.7")
    return ",".join(dict.fromkeys(parts))


def _language_preferences(locale: str) -> list[str]:
    normalized = (locale or "en-US").strip() or "en-US"
    primary = normalized.split("-")[0]
    values = [normalized]
    if primary and primary.lower() != normalized.lower():
        values.append(primary)
    if normalized.lower() != "en-us":
        values.append("en-US")
    if primary.lower() != "en":
        values.append("en")
    return list(dict.fromkeys(values))


def _platform_from_user_agent(user_agent: str) -> str:
    normalized = (user_agent or "").lower()
    if "iphone" in normalized:
        return "iPhone"
    if "ipad" in normalized:
        return "iPad"
    if "mac os x" in normalized or "macintosh" in normalized:
        return "MacIntel"
    if "android" in normalized:
        return "Linux armv8l"
    if "linux" in normalized:
        return "Linux x86_64"
    return "Win32"


def _browser_identity_payload(profile: BrowserProfile) -> dict[str, Any]:
    locale = profile.locale or "en-US"
    return {
        "userAgent": profile.user_agent or "",
        "locale": locale,
        "acceptLanguage": _default_accept_language(locale),
        "languages": _language_preferences(locale),
        "platform": _platform_from_user_agent(profile.user_agent or ""),
        "plugins": [
            {
                "name": "Chrome PDF Plugin",
                "filename": "internal-pdf-viewer",
                "description": "Portable Document Format",
            },
            {
                "name": "Chrome PDF Viewer",
                "filename": "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                "description": "",
            },
            {
                "name": "Native Client",
                "filename": "internal-nacl-plugin",
                "description": "",
            },
        ],
        "webglVendor": "Google Inc. (Intel)",
        "webglRenderer": "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    }


def _simulation_runtime_handles() -> dict[str, str]:
    token = secrets.token_hex(6)
    return {
        "envName": f"__ax_env_{token}",
        "interactionName": f"__ax_int_{token}",
        "stateKey": f"__ax_state_{token}",
    }


def build_simulation_payload(profile: BrowserProfile) -> dict[str, Any]:
    return {
        "environmentSimulation": _camelize_value(profile.environment_simulation.model_dump(mode="json")),
        "interactionSimulation": _camelize_value(profile.interaction_simulation.model_dump(mode="json")),
        "browserIdentity": _camelize_value(_browser_identity_payload(profile)),
        "sessionRuntime": {
            "seed": secrets.randbelow(2_147_483_646) + 1,
        },
        "runtimeHandles": _simulation_runtime_handles(),
    }


def render_simulation_init_script(profile: BrowserProfile, payload: dict[str, Any] | None = None) -> str:
    payload = json.dumps(payload or build_simulation_payload(profile), ensure_ascii=False, separators=(",", ":"))
    return SIMULATION_INIT_SCRIPT_TEMPLATE.replace("__AXELO_SIMULATION_CONFIG__", payload)
