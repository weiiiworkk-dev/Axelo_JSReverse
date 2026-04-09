'use strict';

const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { URL } = require('url');

const PORT = Number(process.env.AXELO_BRIDGE_PORT || __AXELO_BRIDGE_PORT__);
const DEFAULT_START_URL = process.env.AXELO_BRIDGE_START_URL || __AXELO_START_URL__;
const DEFAULT_STORAGE_STATE_PATH = process.env.AXELO_BRIDGE_STORAGE_STATE || __AXELO_STORAGE_STATE_PATH__;
const DEFAULT_USER_AGENT = __AXELO_DEFAULT_USER_AGENT__;
const DEFAULT_APP_KEY = process.env.AXELO_BRIDGE_APP_KEY || __AXELO_DEFAULT_APP_KEY__;
const DEFAULT_ENVIRONMENT_SIMULATION = __AXELO_DEFAULT_ENVIRONMENT_SIMULATION__;
const DEFAULT_INTERACTION_SIMULATION = __AXELO_DEFAULT_INTERACTION_SIMULATION__;
const DEFAULT_EXECUTOR_CANDIDATES = __AXELO_EXECUTOR_CANDIDATES__;
const DEFAULT_PREFERRED_BRIDGE_TARGET = __AXELO_PREFERRED_BRIDGE_TARGET__;
const MAX_BODY_BYTES = 1024 * 1024;
const MAX_EVENTS = 200;

const playwrightInfo = tryRequire(['playwright', 'playwright-core']);
const playwright = playwrightInfo ? playwrightInfo.module : null;
const SIMULATION_INIT_SCRIPT_TEMPLATE = __AXELO_SIMULATION_INIT_SCRIPT_TEMPLATE__;

function renderBridgeInitScript(handles) {
  const bridgeHandles = handles || defaultSimulationHandles();
  const apiName = String(bridgeHandles.bridgeName || randomStealthHandle('ax_bridge'));
  const stateKey = String(bridgeHandles.bridgeStateKey || randomStealthHandle('ax_bridge_state'));
  return `(() => {
  const root = window;
  const apiName = ${JSON.stringify(apiName)};
  const stateKey = ${JSON.stringify(stateKey)};
  if (root[stateKey] && root[apiName]) return;

  const own = Object.prototype.hasOwnProperty;
  const registry = new Map();

  const pick = (base, dotPath) => {
    if (!dotPath) return base;
    return String(dotPath).split(".").reduce((value, key) => (value == null ? value : value[key]), base);
  };

  const encodeBytes = (view) => {
    let binary = "";
    for (let i = 0; i < view.length; i += 1) binary += String.fromCharCode(view[i]);
    return btoa(binary);
  };

  const normalize = (value) => {
    if (value === undefined || value === null) return value ?? null;
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
    if (value instanceof ArrayBuffer) return { __type: "ArrayBuffer", base64: encodeBytes(new Uint8Array(value)) };
    if (ArrayBuffer.isView(value)) {
      return {
        __type: value.constructor.name,
        base64: encodeBytes(new Uint8Array(value.buffer, value.byteOffset, value.byteLength)),
      };
    }
    if (Array.isArray(value)) return value.map(normalize);
    if (typeof value === "object") {
      const out = {};
      for (const key in value) if (own.call(value, key)) out[key] = normalize(value[key]);
      return out;
    }
    return String(value);
  };

  const api = Object.freeze({
    register(name, fn, thisArg) {
      if (!name) throw new Error("Missing bridge name");
      if (typeof fn !== "function") throw new Error("Bridge target must be a function");
      registry.set(String(name), { fn, thisArg: thisArg ?? root });
      return { ok: true, name: String(name) };
    },
    registerGlobal(name, globalPath, ownerPath) {
      const fn = pick(root, globalPath);
      if (typeof fn !== "function") throw new Error("Global path does not resolve to a function: " + globalPath);
      const owner = ownerPath
        ? pick(root, ownerPath)
        : String(globalPath).includes(".")
          ? pick(root, String(globalPath).split(".").slice(0, -1).join("."))
          : root;
      return this.register(name, fn, owner ?? root);
    },
    async call(name, args) {
      const entry = registry.get(String(name));
      if (!entry) throw new Error("Bridge target is not registered: " + name);
      const finalArgs = Array.isArray(args) ? args : [];
      const result = await Promise.resolve(entry.fn.apply(entry.thisArg, finalArgs));
      return normalize(result);
    },
    list() {
      return Array.from(registry.keys());
    },
  });

  Object.defineProperty(root, stateKey, {
    value: api,
    enumerable: false,
    configurable: false,
    writable: false,
  });
  Object.defineProperty(root, apiName, {
    value: api,
    enumerable: false,
    configurable: false,
    writable: false,
  });
})();`;
}

function renderWasmInitScript(handles) {
  const wasmHandles = handles || defaultSimulationHandles();
  const apiName = String(wasmHandles.wasmName || randomStealthHandle('ax_wasm'));
  const configName = String(wasmHandles.wasmConfigName || randomStealthHandle('ax_wasm_cfg'));
  const stateKey = String(wasmHandles.wasmStateKey || randomStealthHandle('ax_wasm_state'));
  return `(() => {
  const root = window;
  const apiName = ${JSON.stringify(apiName)};
  const configName = ${JSON.stringify(configName)};
  const stateKey = ${JSON.stringify(stateKey)};
  if (root[stateKey] && root[apiName]) return;

  const own = Object.prototype.hasOwnProperty;
  const original = {
    instantiate: typeof WebAssembly.instantiate === 'function' ? WebAssembly.instantiate.bind(WebAssembly) : null,
    instantiateStreaming: typeof WebAssembly.instantiateStreaming === 'function' ? WebAssembly.instantiateStreaming.bind(WebAssembly) : null,
    compile: typeof WebAssembly.compile === 'function' ? WebAssembly.compile.bind(WebAssembly) : null,
    compileStreaming: typeof WebAssembly.compileStreaming === 'function' ? WebAssembly.compileStreaming.bind(WebAssembly) : null,
    Instance: WebAssembly.Instance,
  };

  const defaults = {
    enabled: true,
    snapshotMode: 'full',
    overloadPolicy: 'preserve_realism',
    maxFullSnapshotBytes: 2097152,
    sliceBytes: 4096,
    persistRawBinary: true,
    artifactDir: 'wasm_artifacts',
    maxEvents: 200,
    maxSnapshots: 120,
  };

  const safeDefine = (target, property, descriptor) => {
    try {
      Object.defineProperty(target, property, {
        configurable: true,
        enumerable: false,
        ...descriptor,
      });
      return true;
    } catch (_error) {
      return false;
    }
  };

  const cloneJson = (value) => {
    if (value === undefined) return null;
    if (value === null) return null;
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (_error) {
      return null;
    }
  };

  const mergeValue = (current, patch) => {
    if (Array.isArray(patch)) return patch.slice();
    if (!patch || typeof patch !== 'object') return patch;
    const base = current && typeof current === 'object' && !Array.isArray(current) ? current : {};
    const next = { ...base };
    for (const [key, value] of Object.entries(patch)) {
      if (value === undefined) continue;
      next[key] = mergeValue(base[key], value);
    }
    return next;
  };

  const encodeBytes = (view) => {
    if (!view || !view.length) return '';
    const chunkSize = 0x8000;
    let binary = '';
    for (let offset = 0; offset < view.length; offset += chunkSize) {
      const chunk = view.subarray(offset, Math.min(view.length, offset + chunkSize));
      let piece = '';
      for (let index = 0; index < chunk.length; index += 1) piece += String.fromCharCode(chunk[index]);
      binary += piece;
    }
    return btoa(binary);
  };

  const normalize = (value) => {
    if (value === undefined || value === null) return value ?? null;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value;
    if (value instanceof ArrayBuffer) return { __type: 'ArrayBuffer', base64: encodeBytes(new Uint8Array(value)) };
    if (ArrayBuffer.isView(value)) {
      return {
        __type: value.constructor.name,
        base64: encodeBytes(new Uint8Array(value.buffer, value.byteOffset, value.byteLength)),
      };
    }
    if (Array.isArray(value)) return value.map(normalize);
    if (typeof value === 'object') {
      const out = {};
      for (const key in value) if (own.call(value, key)) out[key] = normalize(value[key]);
      return out;
    }
    return String(value);
  };

  const fnv1a = (view) => {
    let hash = 0x811c9dc5;
    for (let index = 0; index < view.length; index += 1) {
      hash ^= view[index];
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, '0');
  };

  const nowIso = () => new Date().toISOString();

  const copyBytes = (value) => {
    if (!value) return null;
    if (value instanceof ArrayBuffer) return new Uint8Array(value.slice(0));
    if (ArrayBuffer.isView(value)) {
      return new Uint8Array(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength));
    }
    return null;
  };

  const readVarUint = (bytes, start) => {
    let result = 0;
    let shift = 0;
    let offset = start;
    while (offset < bytes.length) {
      const byte = bytes[offset];
      offset += 1;
      result |= (byte & 0x7f) << shift;
      if ((byte & 0x80) === 0) return { value: result >>> 0, next: offset };
      shift += 7;
      if (shift > 35) return null;
    }
    return null;
  };

  const sectionName = (id) => ({
    0: 'custom',
    1: 'type',
    2: 'import',
    3: 'function',
    4: 'table',
    5: 'memory',
    6: 'global',
    7: 'export',
    8: 'start',
    9: 'element',
    10: 'code',
    11: 'data',
    12: 'data_count',
  }[id] || 'unknown');

  const parseSections = (bytes) => {
    if (!bytes || bytes.length < 8) return [];
    if (bytes[0] !== 0x00 || bytes[1] !== 0x61 || bytes[2] !== 0x73 || bytes[3] !== 0x6d) return [];
    const sections = [];
    let offset = 8;
    while (offset < bytes.length) {
      const id = bytes[offset];
      offset += 1;
      const sizeInfo = readVarUint(bytes, offset);
      if (!sizeInfo) break;
      const size = sizeInfo.value;
      offset = sizeInfo.next;
      const start = offset;
      const end = Math.min(bytes.length, start + size);
      sections.push({ id, name: sectionName(id), size, start, end });
      offset = end;
    }
    return sections;
  };

  const hasSequence = (bytes, sequence) => {
    if (!bytes || !sequence || !sequence.length || sequence.length > bytes.length) return false;
    outer:
    for (let offset = 0; offset <= bytes.length - sequence.length; offset += 1) {
      for (let index = 0; index < sequence.length; index += 1) {
        if (bytes[offset + index] !== sequence[index]) continue outer;
      }
      return true;
    }
    return false;
  };

  const hasAscii = (bytes, text) => {
    if (!bytes || !text) return false;
    const encoded = new TextEncoder().encode(text);
    return hasSequence(bytes, encoded);
  };

  const detectAlgorithms = (bytes) => {
    const hits = [];
    if (!bytes || !bytes.length) return hits;
    if (hasAscii(bytes, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/')) {
      hits.push({ algorithm: 'base64', confidence: 0.95, evidence: 'standard_alphabet' });
    }
    if (
      hasSequence(bytes, [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36])
      || hasSequence(bytes, [0x63, 0x7c, 0x77, 0x7b])
    ) {
      hits.push({ algorithm: 'aes', confidence: 0.72, evidence: 'rcon_or_sbox_prefix' });
    }
    return hits;
  };

  const state = {
    config: mergeValue(defaults, root[configName] || {}),
    nextModuleId: 0,
    nextInstanceId: 0,
    nextSnapshotId: 0,
    nextEventId: 0,
    modulesByRef: new WeakMap(),
    instancesByRef: new WeakMap(),
    memoriesByRef: new WeakMap(),
    modules: new Map(),
    instances: new Map(),
    snapshots: [],
    events: [],
  };

  const enqueue = (type, detail) => {
    const event = {
      id: ++state.nextEventId,
      ts: nowIso(),
      type,
      detail: cloneJson(detail) || {},
    };
    state.events.push(event);
    if (state.events.length > Number(state.config.maxEvents || defaults.maxEvents)) {
      state.events.splice(0, state.events.length - Number(state.config.maxEvents || defaults.maxEvents));
    }
    return event;
  };

  const snapshotCap = () => Number(state.config.maxSnapshots || defaults.maxSnapshots);

  const registerBinary = (meta, bytes, sourceKind, sourceUrl) => {
    if (!meta || !bytes || !bytes.length) return meta;
    meta.binaryBase64 = encodeBytes(bytes);
    meta.binaryByteLength = bytes.length;
    meta.binaryFingerprint = fnv1a(bytes);
    meta.binarySourceKind = sourceKind || meta.binarySourceKind || 'buffer';
    meta.binarySourceUrl = sourceUrl || meta.binarySourceUrl || '';
    meta.sections = parseSections(bytes);
    meta.detections = detectAlgorithms(bytes);
    return meta;
  };

  const ensureModuleMeta = (module, extra) => {
    if (!module) return null;
    let meta = state.modulesByRef.get(module);
    const created = !meta;
    if (!meta) {
      meta = {
        moduleId: 'wasm-module-' + (++state.nextModuleId),
        module,
        createdAt: nowIso(),
        imports: [],
        exports: [],
        binaryBase64: '',
        binaryByteLength: 0,
        binaryFingerprint: '',
        binarySourceKind: 'unknown',
        binarySourceUrl: '',
        sections: [],
        detections: [],
        instanceIds: [],
      };
      state.modulesByRef.set(module, meta);
      state.modules.set(meta.moduleId, meta);
    }
    try {
      meta.imports = WebAssembly.Module.imports(module).map((item) => ({
        module: item.module,
        name: item.name,
        kind: item.kind,
      }));
    } catch (_error) {}
    try {
      meta.exports = WebAssembly.Module.exports(module).map((item) => ({
        name: item.name,
        kind: item.kind,
      }));
    } catch (_error) {}
    if (extra && extra.bytes) registerBinary(meta, extra.bytes, extra.sourceKind, extra.sourceUrl);
    if (created) {
      enqueue('wasm_module_registered', {
        moduleId: meta.moduleId,
        importCount: meta.imports.length,
        exportCount: meta.exports.length,
        sourceKind: meta.binarySourceKind,
      });
    }
    return meta;
  };

  const addMemoryBinding = (instanceMeta, memory, bindingName, source) => {
    if (!(memory instanceof WebAssembly.Memory)) return;
    let memoryMeta = state.memoriesByRef.get(memory);
    if (!memoryMeta) {
      memoryMeta = {
        memory,
        bindingNames: [],
      };
      state.memoriesByRef.set(memory, memoryMeta);
    }
    const bindingKey = String(source || 'export') + ':' + String(bindingName || 'memory');
    if (memoryMeta.bindingNames.indexOf(bindingKey) < 0) memoryMeta.bindingNames.push(bindingKey);
    const bindingRecord = {
      name: String(bindingName || 'memory'),
      source: String(source || 'export'),
      byteLength: memory.buffer ? memory.buffer.byteLength : 0,
      memory,
    };
    instanceMeta.memoryBindings.push(bindingRecord);
  };

  const collectImportMemories = (instanceMeta, imports) => {
    if (!imports || typeof imports !== 'object') return;
    for (const [namespace, value] of Object.entries(imports)) {
      if (value instanceof WebAssembly.Memory) {
        addMemoryBinding(instanceMeta, value, namespace, 'import');
        continue;
      }
      if (!value || typeof value !== 'object') continue;
      for (const [key, nested] of Object.entries(value)) {
        if (nested instanceof WebAssembly.Memory) addMemoryBinding(instanceMeta, nested, namespace + '.' + key, 'import');
      }
    }
  };

  const findPrimaryMemory = (instanceMeta) => {
    if (!instanceMeta || !Array.isArray(instanceMeta.memoryBindings) || instanceMeta.memoryBindings.length === 0) return null;
    return instanceMeta.memoryBindings[0];
  };

  const resolveDescriptors = (args, result, descriptorInput, byteLength) => {
    const descriptors = [];
    for (const descriptor of Array.isArray(descriptorInput) ? descriptorInput : []) {
      if (!descriptor || typeof descriptor !== 'object') continue;
      const ptr = descriptor.ptrValue != null
        ? Number(descriptor.ptrValue)
        : descriptor.ptrArgIndex != null
          ? Number(args[Number(descriptor.ptrArgIndex)])
          : null;
      const len = descriptor.lenValue != null
        ? Number(descriptor.lenValue)
        : descriptor.lenArgIndex != null
          ? Number(args[Number(descriptor.lenArgIndex)])
          : null;
      if (!Number.isFinite(ptr) || !Number.isFinite(len)) continue;
      if (ptr < 0 || len <= 0 || ptr + len > byteLength) continue;
      descriptors.push({
        name: String(descriptor.name || 'buffer'),
        role: String(descriptor.role || 'input'),
        offset: Math.trunc(ptr),
        length: Math.trunc(len),
        encoding: String(descriptor.encoding || 'binary'),
      });
    }
    if (descriptors.length > 0) return descriptors;

    for (let index = 0; index < args.length - 1; index += 1) {
      const ptr = Number(args[index]);
      const len = Number(args[index + 1]);
      if (!Number.isFinite(ptr) || !Number.isFinite(len)) continue;
      if (ptr < 0 || len <= 0 || len > 65536 || ptr + len > byteLength) continue;
      descriptors.push({
        name: 'heuristic_' + index,
        role: 'heuristic',
        offset: Math.trunc(ptr),
        length: Math.trunc(len),
        encoding: 'binary',
      });
      if (descriptors.length >= 4) break;
    }
    if (Number.isFinite(Number(result)) && descriptors.length === 0 && args.length > 0 && Number.isFinite(Number(args[args.length - 1]))) {
      const ptr = Number(result);
      const len = Number(args[args.length - 1]);
      if (ptr >= 0 && len > 0 && len <= 65536 && ptr + len <= byteLength) {
        descriptors.push({
          name: 'heuristic_return',
          role: 'output',
          offset: Math.trunc(ptr),
          length: Math.trunc(len),
          encoding: 'binary',
        });
      }
    }
    return descriptors;
  };

  const makeSliceRecord = (view, offset, length, label) => {
    if (!view || !view.length || length <= 0) return null;
    const start = Math.max(0, Math.min(view.length, offset));
    const end = Math.max(start, Math.min(view.length, start + length));
    const slice = view.slice(start, end);
    return {
      label,
      offset: start,
      length: slice.length,
      base64: encodeBytes(slice),
    };
  };

  const snapshotMemory = (instanceMeta, args, result, options) => {
    const memoryBinding = findPrimaryMemory(instanceMeta);
    if (!memoryBinding || !(memoryBinding.memory instanceof WebAssembly.Memory)) return null;
    const buffer = memoryBinding.memory.buffer;
    if (!buffer) return null;
    const byteLength = buffer.byteLength;
    const view = new Uint8Array(buffer);
    const sliceBytes = Math.max(64, Number(state.config.sliceBytes || defaults.sliceBytes));
    const maxFull = Math.max(1024, Number(state.config.maxFullSnapshotBytes || defaults.maxFullSnapshotBytes));
    const requestedMode = String(options && options.snapshotMode ? options.snapshotMode : state.config.snapshotMode || defaults.snapshotMode);
    const descriptors = resolveDescriptors(
      Array.isArray(args) ? args : [],
      result,
      options && options.bufferDescriptors ? options.bufferDescriptors : [],
      byteLength,
    );
    const useFull = requestedMode === 'full' && byteLength <= maxFull;
    const degraded = !useFull;
    const reasons = [];
    if (requestedMode === 'full' && byteLength > maxFull) reasons.push('memory_too_large');
    if (requestedMode !== 'full') reasons.push('summary_mode_requested');
    const record = {
      byteLength,
      mode: useFull ? 'full' : 'summary',
      degraded,
      reasons,
      head: makeSliceRecord(view, 0, Math.min(sliceBytes, byteLength), 'head'),
      tail: makeSliceRecord(view, Math.max(0, byteLength - sliceBytes), Math.min(sliceBytes, byteLength), 'tail'),
      windows: descriptors
        .map((descriptor) => ({
          ...descriptor,
          before: makeSliceRecord(view, descriptor.offset, descriptor.length, descriptor.name),
        }))
        .filter(Boolean),
    };
    if (useFull) {
      record.fullBase64 = encodeBytes(new Uint8Array(buffer.slice(0)));
    }
    return record;
  };

  const sanitizeMemoryRecord = (record, phase) => {
    if (!record) return null;
    const windows = (record.windows || []).map((item) => ({
      name: item.name,
      role: item.role,
      offset: item.offset,
      length: item.length,
      encoding: item.encoding,
      base64: item.before ? item.before.base64 : null,
      label: phase + ':' + item.name,
    }));
    return {
      byteLength: record.byteLength,
      mode: record.mode,
      degraded: record.degraded,
      reasons: Array.isArray(record.reasons) ? record.reasons.slice() : [],
      head: record.head,
      tail: record.tail,
      fullBase64: record.fullBase64 || null,
      windows,
    };
  };

  const executeExport = (instanceMeta, exportName, args, options) => {
    if (!instanceMeta) throw new Error('WASM instance not found');
    const callable = instanceMeta.rawExports[exportName] || (instanceMeta.instance && instanceMeta.instance.exports ? instanceMeta.instance.exports[exportName] : null);
    if (typeof callable !== 'function') throw new Error('WASM export is not callable: ' + exportName);
    const finalArgs = Array.isArray(args) ? args.slice() : [];
    const captureMemory = !(options && options.captureMemory === false);
    const before = captureMemory ? snapshotMemory(instanceMeta, finalArgs, null, options || {}) : null;
    let value;
    try {
      value = callable.apply(undefined, finalArgs);
    } catch (error) {
      enqueue('wasm_export_error', {
        instanceId: instanceMeta.instanceId,
        moduleId: instanceMeta.moduleId,
        exportName,
        message: error && error.message ? error.message : String(error),
      });
      throw error;
    }
    const after = captureMemory ? snapshotMemory(instanceMeta, finalArgs, value, options || {}) : null;
    let snapshot = null;
    if (captureMemory) {
      snapshot = {
        snapshotId: ++state.nextSnapshotId,
        ts: nowIso(),
        moduleId: instanceMeta.moduleId,
        instanceId: instanceMeta.instanceId,
        exportName,
        args: normalize(finalArgs),
        result: normalize(value),
        degraded: Boolean((before && before.degraded) || (after && after.degraded)),
        memory: {
          primaryMemoryName: instanceMeta.primaryMemoryName || null,
          before: sanitizeMemoryRecord(before, 'before'),
          after: sanitizeMemoryRecord(after, 'after'),
        },
      };
      state.snapshots.push(snapshot);
      if (state.snapshots.length > snapshotCap()) {
        state.snapshots.splice(0, state.snapshots.length - snapshotCap());
      }
      enqueue(snapshot.degraded ? 'wasm_snapshot_degraded' : 'wasm_snapshot_captured', {
        snapshotId: snapshot.snapshotId,
        moduleId: snapshot.moduleId,
        instanceId: snapshot.instanceId,
        exportName,
        byteLength: after && after.byteLength ? after.byteLength : before && before.byteLength ? before.byteLength : null,
      });
    } else {
      enqueue('wasm_export_invoked', {
        moduleId: instanceMeta.moduleId,
        instanceId: instanceMeta.instanceId,
        exportName,
      });
    }
    return { value, snapshot };
  };

  const wrapExport = (instanceMeta, exportName, originalFn) => {
    if (typeof originalFn !== 'function') return originalFn;
    if (instanceMeta.wrappedExports[exportName]) return instanceMeta.wrappedExports[exportName];
    const wrapped = function() {
      const args = Array.prototype.slice.call(arguments);
      return executeExport(instanceMeta, exportName, args, {
        captureMemory: true,
        snapshotMode: state.config.snapshotMode,
      }).value;
    };
    safeDefine(wrapped, '__axeloWrappedExport__', { value: true, writable: false });
    instanceMeta.wrappedExports[exportName] = wrapped;
    return wrapped;
  };

  const registerInstance = (instance, module, imports, extra) => {
    if (!instance) return null;
    let meta = state.instancesByRef.get(instance);
    const created = !meta;
    if (!meta) {
      meta = {
        instanceId: 'wasm-instance-' + (++state.nextInstanceId),
        instance,
        moduleId: null,
        createdAt: nowIso(),
        exportNames: [],
        rawExports: Object.create(null),
        wrappedExports: Object.create(null),
        memoryBindings: [],
        primaryMemoryName: null,
      };
      state.instancesByRef.set(instance, meta);
      state.instances.set(meta.instanceId, meta);
    }
    const moduleMeta = ensureModuleMeta(module, extra || null);
    if (moduleMeta) {
      meta.moduleId = moduleMeta.moduleId;
      if (moduleMeta.instanceIds.indexOf(meta.instanceId) < 0) moduleMeta.instanceIds.push(meta.instanceId);
    }
    meta.memoryBindings = [];
    collectImportMemories(meta, imports || {});
    const exportsObject = instance.exports || {};
    meta.exportNames = [];
    for (const [name, value] of Object.entries(exportsObject)) {
      meta.exportNames.push(name);
      if (typeof value === 'function') {
        meta.rawExports[name] = value;
        const wrapped = wrapExport(meta, name, value);
        try {
          exportsObject[name] = wrapped;
        } catch (_error) {
          safeDefine(exportsObject, name, { value: wrapped, writable: true, enumerable: true });
        }
      } else if (value instanceof WebAssembly.Memory) {
        addMemoryBinding(meta, value, name, 'export');
      }
    }
    meta.primaryMemoryName = meta.memoryBindings.length > 0 ? meta.memoryBindings[0].name : null;
    if (created) {
      enqueue('wasm_instance_registered', {
        instanceId: meta.instanceId,
        moduleId: meta.moduleId,
        exportCount: meta.exportNames.length,
        memoryCount: meta.memoryBindings.length,
      });
    }
    return meta;
  };

  const serializeInstanceSummary = (instanceMeta) => ({
    instanceId: instanceMeta.instanceId,
    moduleId: instanceMeta.moduleId,
    createdAt: instanceMeta.createdAt,
    exportNames: instanceMeta.exportNames.slice(),
    memoryBindings: instanceMeta.memoryBindings.map((item) => ({
      name: item.name,
      source: item.source,
      byteLength: item.memory && item.memory.buffer ? item.memory.buffer.byteLength : item.byteLength,
    })),
    primaryMemoryName: instanceMeta.primaryMemoryName,
  });

  const serializeModuleSummary = (moduleMeta) => {
    const linkedInstances = moduleMeta.instanceIds
      .map((instanceId) => state.instances.get(instanceId))
      .filter(Boolean)
      .map((item) => serializeInstanceSummary(item));
    const primaryMemory = linkedInstances.length > 0 && linkedInstances[0].memoryBindings.length > 0
      ? linkedInstances[0].memoryBindings[0]
      : null;
    return {
      moduleId: moduleMeta.moduleId,
      createdAt: moduleMeta.createdAt,
      sourceKind: moduleMeta.binarySourceKind,
      sourceUrl: moduleMeta.binarySourceUrl,
      importTable: moduleMeta.imports.slice(),
      exports: moduleMeta.exports.slice(),
      exportedFunctions: moduleMeta.exports.filter((item) => item.kind === 'function').map((item) => item.name),
      instanceIds: moduleMeta.instanceIds.slice(),
      instances: linkedInstances,
      binary: {
        byteLength: moduleMeta.binaryByteLength,
        fingerprint: moduleMeta.binaryFingerprint || null,
      },
      primaryMemory: primaryMemory || null,
      detectionCount: moduleMeta.detections.length,
    };
  };

  const serializeModuleReport = (moduleMeta, includeBinary) => ({
    ...serializeModuleSummary(moduleMeta),
    sections: moduleMeta.sections.slice(),
    detections: moduleMeta.detections.slice(),
    binary: {
      byteLength: moduleMeta.binaryByteLength,
      fingerprint: moduleMeta.binaryFingerprint || null,
      sourceKind: moduleMeta.binarySourceKind,
      sourceUrl: moduleMeta.binarySourceUrl || null,
      base64: includeBinary ? moduleMeta.binaryBase64 || null : null,
    },
  });

  const captureSourceBytes = async (source) => {
    const direct = copyBytes(source);
    if (direct) {
      return {
        bytes: direct,
        sourceKind: source && source.constructor && source.constructor.name ? source.constructor.name : 'buffer',
        sourceUrl: '',
      };
    }
    if (typeof Response !== 'undefined' && source instanceof Response) {
      const clone = typeof source.clone === 'function' ? source.clone() : source;
      const buffer = await clone.arrayBuffer();
      return {
        bytes: new Uint8Array(buffer),
        sourceKind: 'Response',
        sourceUrl: clone.url || source.url || '',
      };
    }
    const awaited = await Promise.resolve(source);
    if (awaited !== source) return captureSourceBytes(awaited);
    return null;
  };

  const registerCompiledModule = (module, sourceMeta) => ensureModuleMeta(module, sourceMeta || null);

  const registerInstantiateResult = (module, instance, imports, sourceMeta) => {
    const moduleMeta = ensureModuleMeta(module, sourceMeta || null);
    const instanceMeta = registerInstance(instance, module, imports, sourceMeta || null);
    enqueue('wasm_module_loaded', {
      moduleId: moduleMeta ? moduleMeta.moduleId : null,
      instanceId: instanceMeta ? instanceMeta.instanceId : null,
      sourceKind: moduleMeta ? moduleMeta.binarySourceKind : null,
      exportCount: moduleMeta ? moduleMeta.exports.length : 0,
      importCount: moduleMeta ? moduleMeta.imports.length : 0,
      binaryByteLength: moduleMeta ? moduleMeta.binaryByteLength : 0,
    });
    return { moduleMeta, instanceMeta };
  };

  if (original.compile) {
    safeDefine(WebAssembly, 'compile', {
      value: async function(source) {
        const sourceMeta = await captureSourceBytes(source).catch(() => null);
        const module = await original.compile(source);
        registerCompiledModule(module, sourceMeta);
        return module;
      },
      writable: false,
    });
  }

  if (original.compileStreaming) {
    safeDefine(WebAssembly, 'compileStreaming', {
      value: async function(source) {
        const sourceMetaPromise = captureSourceBytes(source).catch(() => null);
        const module = await original.compileStreaming(source);
        registerCompiledModule(module, await sourceMetaPromise);
        return module;
      },
      writable: false,
    });
  }

  if (original.instantiate) {
    safeDefine(WebAssembly, 'instantiate', {
      value: async function(source, imports) {
        const isModuleSource = source instanceof WebAssembly.Module;
        const sourceMetaPromise = isModuleSource ? Promise.resolve(null) : captureSourceBytes(source).catch(() => null);
        const result = await original.instantiate(source, imports);
        if (isModuleSource) {
          registerInstantiateResult(source, result, imports, await sourceMetaPromise);
          return result;
        }
        registerInstantiateResult(result && result.module, result && result.instance, imports, await sourceMetaPromise);
        return result;
      },
      writable: false,
    });
  }

  if (original.instantiateStreaming) {
    safeDefine(WebAssembly, 'instantiateStreaming', {
      value: async function(source, imports) {
        const sourceMetaPromise = captureSourceBytes(source).catch(() => null);
        const result = await original.instantiateStreaming(source, imports);
        registerInstantiateResult(result && result.module, result && result.instance, imports, await sourceMetaPromise);
        return result;
      },
      writable: false,
    });
  }

  if (typeof original.Instance === 'function') {
    const WrappedInstance = function(module, imports) {
      const instance = Reflect.construct(original.Instance, [module, imports], WrappedInstance);
      registerInstance(instance, module, imports, null);
      return instance;
    };
    Object.setPrototypeOf(WrappedInstance, original.Instance);
    WrappedInstance.prototype = original.Instance.prototype;
    safeDefine(WebAssembly, 'Instance', {
      value: WrappedInstance,
      writable: false,
    });
  }

  const api = Object.freeze({
    configure(nextConfig) {
      state.config = mergeValue(defaults, mergeValue(state.config, nextConfig || {}));
      safeDefine(root, configName, { value: cloneJson(state.config), writable: true });
      return cloneJson(state.config);
    },
    sync() {
      const events = state.events.slice();
      state.events.splice(0, state.events.length);
      return {
        status: this.getStatus(),
        events,
      };
    },
    getStatus() {
      return {
        enabled: state.config.enabled !== false,
        moduleCount: state.modules.size,
        instanceCount: state.instances.size,
        snapshotCount: state.snapshots.length,
        pendingEventCount: state.events.length,
        snapshotMode: state.config.snapshotMode,
        overloadPolicy: state.config.overloadPolicy,
      };
    },
    listModules() {
      return Array.from(state.modules.values()).map((item) => serializeModuleSummary(item));
    },
    getReport(moduleId, options) {
      const meta = state.modules.get(String(moduleId));
      if (!meta) throw new Error('WASM module not found: ' + moduleId);
      return serializeModuleReport(meta, Boolean(options && options.includeBinary));
    },
    getSnapshots(instanceId, sinceId) {
      const since = Number.isFinite(Number(sinceId)) ? Number(sinceId) : 0;
      return state.snapshots
        .filter((item) => (!instanceId || item.instanceId === String(instanceId)) && item.snapshotId > since)
        .map((item) => cloneJson(item));
    },
    invoke(payload) {
      const request = payload || {};
      const exportName = String(request.exportName || '');
      if (!exportName) throw new Error('Missing exportName');
      let instanceMeta = null;
      if (request.instanceId) {
        instanceMeta = state.instances.get(String(request.instanceId)) || null;
      } else if (request.moduleId) {
        const moduleMeta = state.modules.get(String(request.moduleId)) || null;
        if (moduleMeta && moduleMeta.instanceIds.length > 0) {
          instanceMeta = state.instances.get(moduleMeta.instanceIds[moduleMeta.instanceIds.length - 1]) || null;
        }
      }
      if (!instanceMeta) throw new Error('WASM instance not found for invocation');
      const invocation = executeExport(instanceMeta, exportName, Array.isArray(request.args) ? request.args : [], {
        bufferDescriptors: Array.isArray(request.bufferDescriptors) ? request.bufferDescriptors : [],
        captureMemory: request.captureMemory !== false,
        snapshotMode: request.snapshotMode || state.config.snapshotMode,
      });
      return {
        moduleId: instanceMeta.moduleId,
        instanceId: instanceMeta.instanceId,
        exportName,
        result: normalize(invocation.value),
        snapshot: invocation.snapshot ? cloneJson(invocation.snapshot) : null,
      };
    },
  });

  const initialConfig = root[configName];
  if (initialConfig && typeof initialConfig === 'object') api.configure(initialConfig);

  Object.defineProperty(root, stateKey, {
    value: state,
    enumerable: false,
    configurable: false,
    writable: false,
  });
  Object.defineProperty(root, apiName, {
    value: api,
    enumerable: false,
    configurable: false,
    writable: false,
  });
})();`;
}

const VALID_CHALLENGE_POLICIES = new Set(['fail_fast', 'pause_and_report', 'wait_for_test_bypass_token']);

function createRuntimeSessionId() {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : crypto.createHash('md5').update(`${Date.now()}:${Math.random()}`, 'utf8').digest('hex');
}

function createRuntimeSeed() {
  return Math.max(1, crypto.randomBytes(4).readUInt32BE(0));
}

function randomStealthHandle(prefix) {
  return `__${prefix}_${crypto.randomBytes(6).toString('hex')}`;
}

function defaultSimulationHandles() {
  return {
    envName: randomStealthHandle('ax_env'),
    interactionName: randomStealthHandle('ax_int'),
    stateKey: randomStealthHandle('ax_state'),
    bridgeName: randomStealthHandle('ax_bridge'),
    bridgeStateKey: randomStealthHandle('ax_bridge_state'),
    wasmName: randomStealthHandle('ax_wasm'),
    wasmStateKey: randomStealthHandle('ax_wasm_state'),
    wasmConfigName: randomStealthHandle('ax_wasm_cfg'),
  };
}

const runtime = {
  browser: null,
  context: null,
  page: null,
  startPromise: null,
  restartTimer: null,
  shuttingDown: false,
  cachedStorageState: null,
  pendingCookies: [],
  phase: 'idle',
  reconnectCount: 0,
  lastError: null,
  lastErrorAt: null,
  lastChallenge: null,
  challengeState: {
    status: 'idle',
    policy: 'fail_fast',
    awaitingAuthorization: false,
    continueRequestedAt: null,
    continuedAt: null,
    tokenRequired: false,
    tokenVerified: false,
  },
  lastUrl: '',
  lastTitle: '',
  nextEventId: 0,
  events: [],
  lastEnvironmentStatus: null,
  lastInteractionStatus: null,
  lastWasmStatus: null,
  runtimeSessionId: createRuntimeSessionId(),
  config: defaultConfig(),
};

function defaultConfig() {
  return normalizeRuntimeConfig({
    startUrl: DEFAULT_START_URL,
    appKey: DEFAULT_APP_KEY,
    headless: process.env.AXELO_BRIDGE_HEADLESS === 'false' ? false : true,
    channel: process.env.AXELO_BRIDGE_CHANNEL || undefined,
    storageStatePath: DEFAULT_STORAGE_STATE_PATH || '',
    userAgent: DEFAULT_USER_AGENT || '',
    locale: process.env.AXELO_BRIDGE_LOCALE || 'en-US',
    timezoneId: process.env.AXELO_BRIDGE_TIMEZONE || 'UTC',
    viewport: { width: 1366, height: 768 },
    navigationTimeoutMs: Number(process.env.AXELO_BRIDGE_NAV_TIMEOUT_MS || 30000),
    callTimeoutMs: Number(process.env.AXELO_BRIDGE_CALL_TIMEOUT_MS || 10000),
    pageReadyDelayMs: Number(process.env.AXELO_BRIDGE_READY_DELAY_MS || 500),
    readinessSelector: process.env.AXELO_BRIDGE_READY_SELECTOR || '',
    autoRestartOnCrash: true,
    autoRestartOnDisconnect: true,
    autoRestartOnChallenge: false,
    defaultSigner: process.env.AXELO_BRIDGE_DEFAULT_SIGNER || DEFAULT_PREFERRED_BRIDGE_TARGET || '',
    executorCandidates: DEFAULT_EXECUTOR_CANDIDATES,
    sessionProfile: null,
    interactionEngine: null,
    challengePolicy: process.env.AXELO_BRIDGE_CHALLENGE_POLICY || 'fail_fast',
    authorizedBypassToken: process.env.AXELO_BRIDGE_BYPASS_TOKEN || '',
    simulationHandles: defaultSimulationHandles(),
    runtimeSeed: createRuntimeSeed(),
    environmentSimulation: DEFAULT_ENVIRONMENT_SIMULATION,
    interactionSimulation: DEFAULT_INTERACTION_SIMULATION,
    wasmTelemetry: defaultWasmTelemetryConfig(),
    challengeUrlPatterns: ['captcha', 'challenge', 'verify', 'punish', 'x5secdata'],
    challengeTitlePatterns: ['captcha', 'challenge', 'verify'],
    challengeTextPatterns: ['captcha', 'challenge', 'verify', 'slider', 'human', 'fail_sys_user_validate', 'rgv587_error', 'x5secdata'],
  });
}

function defaultSessionProfile() {
  return {
    profileName: 'desktop_consistent',
    locale: process.env.AXELO_BRIDGE_LOCALE || 'en-US',
    timezoneId: process.env.AXELO_BRIDGE_TIMEZONE || 'UTC',
    userAgent: DEFAULT_USER_AGENT || '',
    viewport: { width: 1366, height: 768 },
    deviceClass: 'desktop',
    colorScheme: 'light',
    reducedMotion: 'no-preference',
    deviceScaleFactor: 1.0,
    hasTouch: false,
    isMobile: false,
    deviceMemory: 8,
    hardwareConcurrency: 8,
    maxTouchPoints: 0,
    geolocation: null,
    geoPolicy: {
      mode: 'consistency_check_only',
      expectedTimezoneId: process.env.AXELO_BRIDGE_TIMEZONE || 'UTC',
      warnOnMismatch: true,
    },
    automationLabel: {
      enabled: false,
      automationMode: false,
      headerName: 'x-axelo-automation',
      headerValue: 'authorized-test',
      cookieName: 'axelo_automation',
      cookieValue: 'authorized-test',
      queryName: 'axeloAutomation',
      queryValue: 'true',
    },
    battery: DEFAULT_ENVIRONMENT_SIMULATION.battery,
    connection: DEFAULT_ENVIRONMENT_SIMULATION.media && DEFAULT_ENVIRONMENT_SIMULATION.media.connection
      ? DEFAULT_ENVIRONMENT_SIMULATION.media.connection
      : {},
    webgl: DEFAULT_ENVIRONMENT_SIMULATION.webgl,
  };
}

function defaultInteractionEngine() {
  return {
    enabled: true,
    profileName: 'synthetic_performance',
    mode: 'playwright_mouse',
    highFrequencyDispatch: false,
    defaultSeed: createRuntimeSeed(),
    pointer: DEFAULT_INTERACTION_SIMULATION.pointer,
    scroll: { enabled: true, jitterPx: 18, stepDelayMs: 24 },
    click: { enabled: true, baseDelayMs: 100, jitterMs: 55 },
  };
}

function defaultWasmTelemetryConfig() {
  return {
    enabled: true,
    snapshotMode: 'full',
    overloadPolicy: 'preserve_realism',
    maxFullSnapshotBytes: 2097152,
    sliceBytes: 4096,
    persistRawBinary: true,
    artifactDir: path.join(__dirname, 'wasm_artifacts'),
  };
}

function coerceViewport(viewport, fallback) {
  const base = fallback || { width: 1366, height: 768 };
  return {
    width: Math.max(320, Math.round(Number(viewport && viewport.width) || base.width)),
    height: Math.max(320, Math.round(Number(viewport && viewport.height) || base.height)),
  };
}

function sessionProfileFromLegacyConfig(config) {
  const environment = config && config.environmentSimulation ? config.environmentSimulation : {};
  const media = environment.media || {};
  return {
    profileName: environment.profileName || null,
    locale: config && config.locale ? config.locale : null,
    timezoneId: config && config.timezoneId ? config.timezoneId : null,
    viewport: config && config.viewport ? config.viewport : null,
    colorScheme: environment.colorScheme || null,
    reducedMotion: environment.reducedMotion || null,
    deviceScaleFactor: environment.deviceScaleFactor,
    hasTouch: environment.hasTouch,
    isMobile: environment.isMobile,
    deviceMemory: media.deviceMemory,
    hardwareConcurrency: media.hardwareConcurrency,
    maxTouchPoints: media.maxTouchPoints,
    battery: environment.battery || null,
    connection: media.connection || null,
    webgl: environment.webgl || null,
  };
}

function interactionEngineFromLegacyConfig(config) {
  const interaction = config && config.interactionSimulation ? config.interactionSimulation : {};
  return {
    enabled: interaction.enabled !== false,
    profileName: interaction.profileName || null,
    mode: interaction.mode || null,
    highFrequencyDispatch: Boolean(interaction.highFrequencyDispatch),
    defaultSeed: interaction.defaultSeed != null ? interaction.defaultSeed : interaction.pointer && interaction.pointer.defaultSeed,
    pointer: interaction.pointer || null,
  };
}

function deriveEnvironmentSimulation(sessionProfile) {
  const profile = sessionProfile || {};
  const hasTouch = Boolean(profile.hasTouch || profile.isMobile || Number(profile.maxTouchPoints || 0) > 0);
  return {
    enabled: true,
    profileName: profile.profileName || 'session_profile',
    colorScheme: profile.colorScheme || 'light',
    reducedMotion: profile.reducedMotion || 'no-preference',
    deviceScaleFactor: profile.deviceScaleFactor != null ? profile.deviceScaleFactor : 1.0,
    hasTouch,
    isMobile: Boolean(profile.isMobile),
    battery: profile.battery || DEFAULT_ENVIRONMENT_SIMULATION.battery,
    media: {
      enabled: true,
      pointer: hasTouch ? 'coarse' : 'fine',
      hover: hasTouch ? 'none' : 'hover',
      anyPointer: hasTouch ? 'coarse' : 'fine',
      anyHover: hasTouch ? 'none' : 'hover',
      hardwareConcurrency: profile.hardwareConcurrency != null ? profile.hardwareConcurrency : 8,
      deviceMemory: profile.deviceMemory != null ? profile.deviceMemory : 8,
      maxTouchPoints: profile.maxTouchPoints != null ? profile.maxTouchPoints : (hasTouch ? 1 : 0),
      connection: profile.connection || (DEFAULT_ENVIRONMENT_SIMULATION.media && DEFAULT_ENVIRONMENT_SIMULATION.media.connection) || {},
    },
    webgl: profile.webgl || DEFAULT_ENVIRONMENT_SIMULATION.webgl,
  };
}

function deriveInteractionSimulation(interactionEngine) {
  const engine = interactionEngine || {};
  return {
    enabled: engine.enabled !== false,
    profileName: engine.profileName || 'interaction_engine',
    mode: engine.mode || 'playwright_mouse',
    highFrequencyDispatch: Boolean(engine.highFrequencyDispatch),
    pointer: engine.pointer || DEFAULT_INTERACTION_SIMULATION.pointer,
  };
}

function normalizeWasmTelemetryConfig(config) {
  const base = defaultWasmTelemetryConfig();
  const next = mergeValue(base, config || {});
  next.enabled = next.enabled !== false;
  next.snapshotMode = String(next.snapshotMode || 'full') === 'full' ? 'full' : 'summary';
  next.overloadPolicy = String(next.overloadPolicy || 'preserve_realism');
  next.maxFullSnapshotBytes = Math.max(1024, Math.round(Number(next.maxFullSnapshotBytes || base.maxFullSnapshotBytes)));
  next.sliceBytes = Math.max(64, Math.round(Number(next.sliceBytes || base.sliceBytes)));
  next.persistRawBinary = next.persistRawBinary !== false;
  next.artifactDir = next.artifactDir ? String(next.artifactDir) : base.artifactDir;
  return next;
}

function normalizeRuntimeConfig(config) {
  const baseProfile = defaultSessionProfile();
  const mergedLegacyProfile = mergeValue(baseProfile, sessionProfileFromLegacyConfig(config || {}));
  const sessionProfile = mergeValue(mergedLegacyProfile, config && config.sessionProfile ? config.sessionProfile : {});
  sessionProfile.locale = sessionProfile.locale || (config && config.locale) || baseProfile.locale;
  sessionProfile.timezoneId = sessionProfile.timezoneId || (config && config.timezoneId) || baseProfile.timezoneId;
  sessionProfile.viewport = coerceViewport(sessionProfile.viewport || (config && config.viewport), baseProfile.viewport);
  sessionProfile.deviceClass = sessionProfile.deviceClass || (sessionProfile.isMobile ? 'mobile' : 'desktop');
  sessionProfile.automationLabel = mergeValue(baseProfile.automationLabel, sessionProfile.automationLabel || {});
  sessionProfile.geoPolicy = mergeValue(baseProfile.geoPolicy, sessionProfile.geoPolicy || {});

  const baseInteraction = defaultInteractionEngine();
  const mergedLegacyInteraction = mergeValue(baseInteraction, interactionEngineFromLegacyConfig(config || {}));
  const interactionEngine = mergeValue(
    mergedLegacyInteraction,
    config && config.interactionEngine ? config.interactionEngine : {},
  );
  interactionEngine.pointer = mergeValue(baseInteraction.pointer, interactionEngine.pointer || {});
  interactionEngine.scroll = mergeValue(baseInteraction.scroll, interactionEngine.scroll || {});
  interactionEngine.click = mergeValue(baseInteraction.click, interactionEngine.click || {});
  interactionEngine.defaultSeed = interactionEngine.defaultSeed != null
    ? interactionEngine.defaultSeed
    : interactionEngine.pointer.defaultSeed;

  return {
    ...(config || {}),
    locale: sessionProfile.locale,
    timezoneId: sessionProfile.timezoneId,
    viewport: sessionProfile.viewport,
    sessionProfile,
    interactionEngine,
    challengePolicy: VALID_CHALLENGE_POLICIES.has(String(config && config.challengePolicy || ''))
      ? String(config.challengePolicy)
      : 'fail_fast',
    environmentSimulation: deriveEnvironmentSimulation(sessionProfile),
    interactionSimulation: deriveInteractionSimulation(interactionEngine),
    wasmTelemetry: normalizeWasmTelemetryConfig(config && config.wasmTelemetry ? config.wasmTelemetry : {}),
  };
}

function tryRequire(names) {
  const candidates = [];
  for (const name of names) {
    candidates.push(name);
  }

  let cursor = __dirname;
  while (true) {
    for (const name of names) {
      candidates.push(path.join(cursor, 'node_modules', name));
      candidates.push(path.join(cursor, 'axelo', 'js_tools', 'scripts', 'node_modules', name));
    }
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }

  const seen = new Set();
  for (const candidate of candidates) {
    if (seen.has(candidate)) continue;
    seen.add(candidate);
    try {
      return { module: require(candidate), name: candidate };
    } catch (_error) {
      continue;
    }
  }
  return null;
}

function createError(statusCode, message, details) {
  const error = new Error(message);
  error.statusCode = statusCode;
  if (details !== undefined) error.details = details;
  return error;
}

function nowIso() {
  return new Date().toISOString();
}

function md5(text) {
  return crypto.createHash('md5').update(text, 'utf8').digest('hex');
}

function safePageUrl(page) {
  try {
    return page.url();
  } catch (_error) {
    return '';
  }
}

function enqueueEvent(type, detail) {
  const event = { id: ++runtime.nextEventId, ts: nowIso(), type, detail: detail || {} };
  runtime.events.push(event);
  if (runtime.events.length > MAX_EVENTS) {
    runtime.events.splice(0, runtime.events.length - MAX_EVENTS);
  }
  return event;
}

function clearRestartTimer() {
  if (runtime.restartTimer) {
    clearTimeout(runtime.restartTimer);
    runtime.restartTimer = null;
  }
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function mergeValue(current, patch) {
  if (Array.isArray(patch)) return patch.slice();
  if (!isPlainObject(patch)) return patch;
  const base = isPlainObject(current) ? current : {};
  const next = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined) continue;
    next[key] = mergeValue(base[key], value);
  }
  return next;
}

function mergeConfig(current, patch) {
  const next = { ...current };
  for (const [key, value] of Object.entries(patch || {})) {
    if (value === undefined) continue;
    next[key] = mergeValue(current[key], value);
  }
  return normalizeRuntimeConfig(next);
}

function summarizeEnvironmentConfig() {
  const config = runtime.config.sessionProfile || {};
  return {
    profileName: config.profileName || null,
    colorScheme: config.colorScheme || null,
    reducedMotion: config.reducedMotion || null,
    deviceScaleFactor: config.deviceScaleFactor ?? null,
    hasTouch: config.hasTouch ?? null,
    isMobile: config.isMobile ?? null,
    locale: config.locale || null,
    timezoneId: config.timezoneId || null,
    viewport: config.viewport || null,
    deviceMemory: config.deviceMemory ?? null,
    hardwareConcurrency: config.hardwareConcurrency ?? null,
    automationLabel: config.automationLabel || null,
    diagnostics: runtime.lastEnvironmentStatus && Array.isArray(runtime.lastEnvironmentStatus.diagnostics)
      ? runtime.lastEnvironmentStatus.diagnostics.length
      : 0,
    webgl: runtime.lastEnvironmentStatus ? runtime.lastEnvironmentStatus.webgl || null : null,
  };
}

function summarizeInteractionConfig() {
  const config = runtime.config.interactionEngine || {};
  const pointer = config.pointer || {};
  return {
    profileName: config.profileName || null,
    mode: config.mode || 'playwright_mouse',
    highFrequencyDispatch: Boolean(config.highFrequencyDispatch),
    defaultSeed: pointer.defaultSeed ?? config.defaultSeed ?? null,
    sampleRateHz: pointer.sampleRateHz ?? null,
    durationMs: pointer.durationMs ?? null,
    scroll: config.scroll || null,
    click: config.click || null,
    lastPathSummary: runtime.lastInteractionStatus ? runtime.lastInteractionStatus.lastPathSummary || null : null,
    lastDispatchSummary: runtime.lastInteractionStatus ? runtime.lastInteractionStatus.lastDispatchSummary || null : null,
  };
}

function summarizeWasmConfig() {
  const config = runtime.config.wasmTelemetry || {};
  const status = runtime.lastWasmStatus || {};
  return {
    enabled: config.enabled !== false,
    snapshotMode: config.snapshotMode || 'full',
    overloadPolicy: config.overloadPolicy || 'preserve_realism',
    maxFullSnapshotBytes: config.maxFullSnapshotBytes || null,
    sliceBytes: config.sliceBytes || null,
    persistRawBinary: config.persistRawBinary !== false,
    artifactDir: config.artifactDir || null,
    moduleCount: status.moduleCount || 0,
    instanceCount: status.instanceCount || 0,
    snapshotCount: status.snapshotCount || 0,
    pendingEventCount: status.pendingEventCount || 0,
  };
}

function renderSimulationInitScript(config) {
  return SIMULATION_INIT_SCRIPT_TEMPLATE.replace('__AXELO_SIMULATION_CONFIG__', JSON.stringify(config || {}));
}

function renderWasmConfigInitScript(config) {
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const configName = String(handles.wasmConfigName || randomStealthHandle('ax_wasm_cfg'));
  const wasmName = String(handles.wasmName || randomStealthHandle('ax_wasm'));
  return `(() => {
    const payload = ${JSON.stringify(config || {})};
    const configName = ${JSON.stringify(configName)};
    const wasmName = ${JSON.stringify(wasmName)};
    try {
      Object.defineProperty(window, configName, {
        value: payload,
        enumerable: false,
        configurable: true,
        writable: true,
      });
    } catch (_error) {
      window[configName] = payload;
    }
    if (window[wasmName] && typeof window[wasmName].configure === 'function') {
      window[wasmName].configure(payload);
    }
  })();`;
}

function simulationPayload() {
  const locale = runtime.config.locale || (runtime.config.sessionProfile && runtime.config.sessionProfile.locale) || 'en-US';
  const primaryLanguage = String(locale).split('-')[0] || 'en';
  const languages = [locale];
  if (primaryLanguage && primaryLanguage !== locale) languages.push(primaryLanguage);
  if (!languages.includes('en-US')) languages.push('en-US');
  if (!languages.includes('en')) languages.push('en');
  const sessionProfile = runtime.config.sessionProfile || {};
  return {
    environmentSimulation: runtime.config.environmentSimulation || {},
    interactionSimulation: runtime.config.interactionSimulation || {},
    browserIdentity: {
      locale,
      acceptLanguage: [locale, `${primaryLanguage};q=0.9`, 'en-US;q=0.8', 'en;q=0.7'].filter(Boolean).join(','),
      languages: Array.from(new Set(languages)),
      platform: sessionProfile.isMobile || sessionProfile.hasTouch ? 'iPhone' : 'Win32',
      userAgent: sessionProfile.userAgent || '',
    },
    sessionRuntime: {
      seed: Number(runtime.config.runtimeSeed || createRuntimeSeed()),
    },
    runtimeHandles: runtime.config.simulationHandles || defaultSimulationHandles(),
  };
}

function dependencyStatus() {
  return {
    playwrightAvailable: Boolean(playwright),
    playwrightModule: playwrightInfo ? playwrightInfo.name : null,
    installHint: playwright ? null : 'Install Playwright for Node.js, for example: npm install playwright',
  };
}

function summarizeRuntime() {
  return {
    status: runtime.phase === 'ready' ? 'ok' : runtime.phase,
    phase: runtime.phase,
    ready: runtime.phase === 'ready',
    reconnectCount: runtime.reconnectCount,
    lastUrl: runtime.lastUrl,
    lastTitle: runtime.lastTitle,
    lastError: runtime.lastError,
    lastErrorAt: runtime.lastErrorAt,
    lastChallenge: runtime.lastChallenge,
    lastEventId: runtime.nextEventId,
    dependency: dependencyStatus(),
    diagnosticsReady: Boolean(runtime.lastEnvironmentStatus && runtime.lastInteractionStatus),
    environment: summarizeEnvironmentConfig(),
    interaction: summarizeInteractionConfig(),
    wasm: summarizeWasmConfig(),
    automation_mode: true,
    config: {
      startUrl: runtime.config.startUrl,
      headless: runtime.config.headless,
      channel: runtime.config.channel || null,
      storageStatePath: runtime.config.storageStatePath || null,
      locale: runtime.config.locale,
      timezoneId: runtime.config.timezoneId,
      viewport: runtime.config.viewport,
      readinessSelector: runtime.config.readinessSelector || null,
      autoRestartOnCrash: runtime.config.autoRestartOnCrash,
      autoRestartOnDisconnect: runtime.config.autoRestartOnDisconnect,
      autoRestartOnChallenge: runtime.config.autoRestartOnChallenge,
      challengePolicy: runtime.config.challengePolicy,
      defaultSigner: runtime.config.defaultSigner || null,
      executorCandidateCount: Array.isArray(runtime.config.executorCandidates) ? runtime.config.executorCandidates.length : 0,
      sessionProfile: runtime.config.sessionProfile || {},
      interactionEngine: runtime.config.interactionEngine || {},
      environmentSimulation: runtime.config.environmentSimulation || {},
      interactionSimulation: runtime.config.interactionSimulation || {},
      wasmTelemetry: runtime.config.wasmTelemetry || {},
    },
    challengeState: runtime.challengeState,
    runtimeSessionId: runtime.runtimeSessionId,
  };
}

function serializeError(error) {
  if (!error) return null;
  return {
    message: error.message || String(error),
    stack: error.stack || null,
    statusCode: error.statusCode || null,
    details: error.details || null,
  };
}

function setRuntimeError(message, details) {
  runtime.lastError = message;
  runtime.lastErrorAt = nowIso();
  enqueueEvent('error', { message, details: details || null });
}

async function withTimeout(promise, timeoutMs, label) {
  let timer = null;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(createError(504, `${label} timed out after ${timeoutMs}ms`)), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function sanitizeConfigPatch(patch) {
  const allowed = new Set(Object.keys(defaultConfig()));
  const next = {};
  for (const [key, value] of Object.entries(patch || {})) {
    if (!allowed.has(key)) throw createError(400, `Unsupported init option: ${key}`);
    next[key] = value;
  }
  return next;
}

function readStorageStateIfAny() {
  if (runtime.cachedStorageState) return runtime.cachedStorageState;
  if (runtime.config.storageStatePath) {
    if (!fs.existsSync(runtime.config.storageStatePath)) {
      throw createError(400, `storageStatePath does not exist: ${runtime.config.storageStatePath}`);
    }
    return JSON.parse(fs.readFileSync(runtime.config.storageStatePath, 'utf8'));
  }
  return undefined;
}

async function installRuntimeScriptsOnPage(page) {
  const timeoutMs = Math.min(runtime.config.callTimeoutMs, 3000);
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  await withTimeout(page.evaluate(renderBridgeInitScript(handles)), timeoutMs, 'Bridge injection');
  await withTimeout(page.evaluate(renderWasmInitScript(handles)), timeoutMs, 'WASM injection');
  await withTimeout(page.evaluate(renderWasmConfigInitScript(runtime.config.wasmTelemetry || {})), timeoutMs, 'WASM config injection');
  await withTimeout(
    page.evaluate(renderSimulationInitScript(simulationPayload())),
    timeoutMs,
    'Simulation injection',
  );
}

async function refreshSimulationStatus(page) {
  const activePage = page || runtime.page;
  if (!activePage || activePage.isClosed()) return null;
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const status = await activePage.evaluate((api) => ({
    environment: window[api.envName] && typeof window[api.envName].getStatus === 'function'
      ? window[api.envName].getStatus()
      : null,
    interaction: window[api.interactionName] && typeof window[api.interactionName].getStatus === 'function'
      ? window[api.interactionName].getStatus()
      : null,
  }), handles).catch((error) => {
    setRuntimeError('Simulation status refresh failed', serializeError(error));
    return null;
  });
  if (!status) return null;
  runtime.lastEnvironmentStatus = status.environment || null;
  runtime.lastInteractionStatus = status.interaction || null;
  return status;
}

async function refreshWasmStatus(page) {
  const activePage = page || runtime.page;
  if (!activePage || activePage.isClosed()) return null;
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const payload = await activePage.evaluate((api) => (
    window[api.wasmName] && typeof window[api.wasmName].sync === 'function'
      ? window[api.wasmName].sync()
      : null
  ), handles).catch((error) => {
    setRuntimeError('WASM status refresh failed', serializeError(error));
    return null;
  });
  if (!payload) return null;
  runtime.lastWasmStatus = payload.status || null;
  for (const event of Array.isArray(payload.events) ? payload.events : []) {
    enqueueEvent(event.type || 'wasm_event', event.detail || {});
  }
  return payload.status || null;
}

function resetChallengeState() {
  runtime.challengeState = {
    status: 'idle',
    policy: runtime.config.challengePolicy,
    awaitingAuthorization: false,
    continueRequestedAt: null,
    continuedAt: null,
    tokenRequired: runtime.config.challengePolicy === 'wait_for_test_bypass_token',
    tokenVerified: false,
  };
}

function markChallengeDetected(source, findings) {
  runtime.lastChallenge = {
    at: nowIso(),
    source,
    url: runtime.lastUrl,
    title: runtime.lastTitle,
    findings,
    policy: runtime.config.challengePolicy,
  };
  const policy = runtime.config.challengePolicy || 'fail_fast';
  runtime.phase = 'challenge';
  runtime.challengeState = {
    status: policy === 'pause_and_report'
      ? 'paused'
      : policy === 'wait_for_test_bypass_token'
        ? 'waiting_for_test_bypass_token'
        : 'fail_fast',
    policy,
    awaitingAuthorization: policy !== 'fail_fast',
    continueRequestedAt: null,
    continuedAt: null,
    tokenRequired: policy === 'wait_for_test_bypass_token',
    tokenVerified: false,
  };
  enqueueEvent('challenge_detected', runtime.lastChallenge);
  if (policy === 'pause_and_report') enqueueEvent('challenge_paused', { challenge: runtime.lastChallenge });
  if (policy === 'wait_for_test_bypass_token') {
    enqueueEvent('challenge_waiting_for_bypass_token', { challenge: runtime.lastChallenge });
  }
}

function challengeStatusPayload() {
  return {
    phase: runtime.phase,
    policy: runtime.config.challengePolicy,
    challenge: runtime.lastChallenge,
    challengeState: runtime.challengeState,
    runtimeSessionId: runtime.runtimeSessionId,
    allowContinue: runtime.challengeState.awaitingAuthorization === true,
  };
}

async function collectEnvironmentObservation(page) {
  if (!page || page.isClosed()) return null;
  return page.evaluate(() => ({
    url: location.href,
    locale: navigator.language || null,
    languages: Array.isArray(navigator.languages) ? navigator.languages.slice(0, 5) : [],
    timezoneId: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
    viewport: {
      width: window.innerWidth || null,
      height: window.innerHeight || null,
      devicePixelRatio: window.devicePixelRatio || null,
    },
    deviceMemory: navigator.deviceMemory ?? null,
    hardwareConcurrency: navigator.hardwareConcurrency ?? null,
    maxTouchPoints: navigator.maxTouchPoints ?? null,
    automationLabel: {
      queryFlagPresent: /[?&]axeloAutomation=/.test(location.search),
      cookieFlagPresent: document.cookie.includes('axelo_automation='),
    },
  })).catch(() => null);
}

function buildConsistencyChecks(observed) {
  const profile = runtime.config.sessionProfile || {};
  const checks = [];
  const expectedViewport = profile.viewport || {};
  const localeValue = String(observed && observed.locale || '');
  const expectedLocale = String(profile.locale || '');

  if (expectedLocale) {
    checks.push({
      field: 'locale',
      expected: expectedLocale,
      observed: observed ? observed.locale : null,
      ok: !localeValue || localeValue.toLowerCase().startsWith(expectedLocale.toLowerCase().split('-')[0]),
    });
  }
  if (profile.timezoneId) {
    checks.push({
      field: 'timezoneId',
      expected: profile.timezoneId,
      observed: observed ? observed.timezoneId : null,
      ok: !observed || !observed.timezoneId || observed.timezoneId === profile.timezoneId,
    });
  }
  if (expectedViewport.width && expectedViewport.height) {
    checks.push({
      field: 'viewport',
      expected: expectedViewport,
      observed: observed ? observed.viewport : null,
      ok: !observed || !observed.viewport
        || (Math.abs(Number(observed.viewport.width || 0) - Number(expectedViewport.width || 0)) <= 2
        && Math.abs(Number(observed.viewport.height || 0) - Number(expectedViewport.height || 0)) <= 2),
    });
  }
  if (profile.deviceMemory != null) {
    checks.push({
      field: 'deviceMemory',
      expected: profile.deviceMemory,
      observed: observed ? observed.deviceMemory : null,
      ok: observed == null || observed.deviceMemory == null || Number(observed.deviceMemory) === Number(profile.deviceMemory),
    });
  }
  if (profile.hardwareConcurrency != null) {
    checks.push({
      field: 'hardwareConcurrency',
      expected: profile.hardwareConcurrency,
      observed: observed ? observed.hardwareConcurrency : null,
      ok: observed == null || observed.hardwareConcurrency == null || Number(observed.hardwareConcurrency) === Number(profile.hardwareConcurrency),
    });
  }
  if (profile.geoPolicy && profile.geoPolicy.expectedTimezoneId) {
    checks.push({
      field: 'geoPolicy.expectedTimezoneId',
      expected: profile.geoPolicy.expectedTimezoneId,
      observed: profile.timezoneId || null,
      ok: profile.timezoneId === profile.geoPolicy.expectedTimezoneId,
    });
  }

  return {
    ok: checks.every((item) => item.ok !== false),
    checks,
    mismatches: checks.filter((item) => item.ok === false),
  };
}

function applyAutomationLabelToUrl(rawUrl) {
  const label = runtime.config.sessionProfile && runtime.config.sessionProfile.automationLabel
    ? runtime.config.sessionProfile.automationLabel
    : null;
  if (!label || label.enabled === false || !label.queryName || label.queryValue == null || !rawUrl) return rawUrl;
  const url = new URL(rawUrl);
  if (!url.searchParams.has(String(label.queryName))) {
    url.searchParams.set(String(label.queryName), String(label.queryValue));
  }
  return url.toString();
}

function automationExtraHeaders() {
  const label = runtime.config.sessionProfile && runtime.config.sessionProfile.automationLabel
    ? runtime.config.sessionProfile.automationLabel
    : null;
  if (!label || label.enabled === false || !label.headerName || label.headerValue == null) return {};
  return { [String(label.headerName)]: String(label.headerValue) };
}

function automationCookies(targetUrl) {
  const label = runtime.config.sessionProfile && runtime.config.sessionProfile.automationLabel
    ? runtime.config.sessionProfile.automationLabel
    : null;
  if (!label || label.enabled === false || !label.cookieName || label.cookieValue == null || !targetUrl) return [];
  return [{ name: String(label.cookieName), value: String(label.cookieValue), url: targetUrl }];
}

function detectChallenge(snapshot) {
  const fields = [
    ['url', snapshot.url || '', runtime.config.challengeUrlPatterns],
    ['title', snapshot.title || '', runtime.config.challengeTitlePatterns],
    ['text', snapshot.text || '', runtime.config.challengeTextPatterns],
  ];
  const findings = [];
  for (const [field, value, patterns] of fields) {
    const lowered = String(value).toLowerCase();
    const hit = (patterns || []).find((pattern) => lowered.includes(String(pattern).toLowerCase()));
    if (hit) findings.push({ field, pattern: String(hit) });
  }
  return findings;
}

async function inspectManagedPage(source) {
  if (!runtime.page || runtime.page.isClosed()) return null;
  const snapshot = await runtime.page.evaluate(() => {
    const bodyText = document.body ? document.body.innerText || '' : '';
    return { url: location.href, title: document.title || '', readyState: document.readyState, text: bodyText.slice(0, 4000) };
  }).catch(() => ({ url: safePageUrl(runtime.page), title: '', readyState: 'unknown', text: '' }));

  runtime.lastUrl = snapshot.url || safePageUrl(runtime.page);
  runtime.lastTitle = snapshot.title || '';
  const findings = detectChallenge(snapshot);

  if (findings.length > 0) {
    markChallengeDetected(source, findings);
    if (runtime.config.autoRestartOnChallenge) scheduleRestart('challenge_detected');
  } else if (runtime.phase !== 'reconnecting' && runtime.phase !== 'starting') {
    runtime.lastChallenge = null;
    resetChallengeState();
    runtime.phase = 'ready';
  }

  await refreshSimulationStatus(runtime.page);
  await refreshWasmStatus(runtime.page);

  return { url: runtime.lastUrl, title: runtime.lastTitle, readyState: snapshot.readyState, challengeDetected: findings.length > 0, findings };
}

async function closeRuntime(preserveStorageState) {
  clearRestartTimer();
  runtime.shuttingDown = true;
  try {
    if (preserveStorageState && runtime.context && typeof runtime.context.storageState === 'function') {
      try {
        runtime.cachedStorageState = await runtime.context.storageState();
      } catch (_error) {
        runtime.cachedStorageState = runtime.cachedStorageState || null;
      }
    }
    if (runtime.context) await runtime.context.close().catch(() => {});
    if (runtime.browser) await runtime.browser.close().catch(() => {});
  } finally {
    runtime.browser = null;
    runtime.context = null;
    runtime.page = null;
    runtime.lastEnvironmentStatus = null;
    runtime.lastInteractionStatus = null;
    runtime.lastWasmStatus = null;
    resetChallengeState();
    runtime.shuttingDown = false;
  }
}

function scheduleRestart(reason) {
  if (runtime.restartTimer) return;
  runtime.phase = 'reconnecting';
  enqueueEvent('restart_scheduled', { reason });
  runtime.restartTimer = setTimeout(async () => {
    runtime.restartTimer = null;
    try {
      await restartRuntime(reason);
    } catch (error) {
      setRuntimeError('Restart failed', serializeError(error));
    }
  }, 1000);
}

function navigationOptions() {
  return { waitUntil: 'domcontentloaded', timeout: runtime.config.navigationTimeoutMs };
}

async function attachManagedPage(page, source) {
  runtime.page = page;
  enqueueEvent('page_attached', { source, url: safePageUrl(page) });

  page.on('crash', () => {
    if (runtime.shuttingDown) return;
    runtime.phase = 'crashed';
    setRuntimeError('Managed page crashed');
    enqueueEvent('page_crash', { url: safePageUrl(page) });
    if (runtime.config.autoRestartOnCrash) scheduleRestart('page_crash');
  });

  page.on('close', () => {
    if (runtime.shuttingDown) return;
    runtime.phase = 'disconnected';
    enqueueEvent('page_closed', { url: safePageUrl(page) });
    if (runtime.config.autoRestartOnCrash) scheduleRestart('page_closed');
  });

  page.on('domcontentloaded', async () => {
    if (!runtime.shuttingDown) {
      await installRuntimeScriptsOnPage(page).catch((error) => setRuntimeError('Runtime injection failed', serializeError(error)));
      await refreshSimulationStatus(page).catch(() => {});
      await refreshWasmStatus(page).catch(() => {});
    }
  });
  page.on('load', async () => {
    if (!runtime.shuttingDown) await inspectManagedPage('load');
  });
  page.on('framenavigated', async (frame) => {
    if (!runtime.shuttingDown && frame === page.mainFrame()) await inspectManagedPage('navigation');
  });

  await installRuntimeScriptsOnPage(page);
  await refreshSimulationStatus(page).catch(() => {});
  await refreshWasmStatus(page).catch(() => {});
}

async function createBrowserRuntime() {
  if (!playwright) throw createError(503, 'Playwright is not installed for Node.js.', dependencyStatus());
  const chromium = playwright.chromium;
  const browserOptions = {
    headless: runtime.config.headless,
    ignoreDefaultArgs: ['--enable-automation'],
    args: [
      '--disable-blink-features=AutomationControlled',
      '--disable-infobars',
    ],
  };
  if (runtime.config.channel) browserOptions.channel = runtime.config.channel;
  runtime.browser = await chromium.launch(browserOptions);

  const sessionProfile = runtime.config.sessionProfile || {};
  const contextOptions = {
    userAgent: sessionProfile.userAgent || runtime.config.userAgent || undefined,
    locale: sessionProfile.locale || runtime.config.locale,
    timezoneId: sessionProfile.timezoneId || runtime.config.timezoneId,
    viewport: sessionProfile.viewport || runtime.config.viewport,
  };
  const environment = runtime.config.environmentSimulation || {};
  if (environment.colorScheme) contextOptions.colorScheme = environment.colorScheme;
  if (environment.reducedMotion) contextOptions.reducedMotion = environment.reducedMotion;
  if (environment.deviceScaleFactor) contextOptions.deviceScaleFactor = environment.deviceScaleFactor;
  if (environment.hasTouch !== undefined) contextOptions.hasTouch = Boolean(environment.hasTouch);
  if (environment.isMobile !== undefined) contextOptions.isMobile = Boolean(environment.isMobile);
  if (sessionProfile.geolocation) {
    contextOptions.geolocation = sessionProfile.geolocation;
    contextOptions.permissions = ['geolocation'];
  }
  const storageState = readStorageStateIfAny();
  if (storageState) contextOptions.storageState = storageState;
  runtime.context = await runtime.browser.newContext(contextOptions);
  const extraHeaders = automationExtraHeaders();
  if (Object.keys(extraHeaders).length > 0 && typeof runtime.context.setExtraHTTPHeaders === 'function') {
    await runtime.context.setExtraHTTPHeaders(extraHeaders);
  }
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  await runtime.context.addInitScript(renderBridgeInitScript(handles));
  await runtime.context.addInitScript(renderWasmInitScript(handles));
  await runtime.context.addInitScript(renderWasmConfigInitScript(runtime.config.wasmTelemetry || {}));
  await runtime.context.addInitScript(renderSimulationInitScript(simulationPayload()));
  const automationCookiesToSet = automationCookies(runtime.config.startUrl);
  if (automationCookiesToSet.length > 0) {
    await runtime.context.addCookies(automationCookiesToSet).catch((error) => setRuntimeError('Failed to apply automation label cookies', serializeError(error)));
  }

  runtime.browser.on('disconnected', () => {
    if (runtime.shuttingDown) return;
    runtime.phase = 'disconnected';
    setRuntimeError('Browser disconnected');
    enqueueEvent('browser_disconnected', {});
    if (runtime.config.autoRestartOnDisconnect) scheduleRestart('browser_disconnected');
  });

  runtime.context.on('page', async (page) => {
    enqueueEvent('page_opened', { url: safePageUrl(page) });
    if (!runtime.page || runtime.page.isClosed()) await attachManagedPage(page, 'context_page');
  });
}

async function startRuntime(reason) {
  if (runtime.startPromise) return runtime.startPromise;
  runtime.startPromise = (async () => {
    runtime.phase = 'starting';
    resetChallengeState();
    enqueueEvent('runtime_starting', { reason, startUrl: runtime.config.startUrl });
    await closeRuntime(true);
    await createBrowserRuntime();

    let page = runtime.context.pages().find((item) => !item.isClosed());
    if (!page) page = await runtime.context.newPage();
    await attachManagedPage(page, 'startup');

    if (runtime.pendingCookies.length > 0) {
      await runtime.context.addCookies(runtime.pendingCookies).catch((error) => setRuntimeError('Failed to apply pending cookies', serializeError(error)));
      runtime.pendingCookies = [];
    }

    if (runtime.config.startUrl) {
      await withTimeout(page.goto(applyAutomationLabelToUrl(runtime.config.startUrl), navigationOptions()), runtime.config.navigationTimeoutMs, 'Initial navigation');
    }
    if (runtime.config.readinessSelector) {
      await withTimeout(page.waitForSelector(runtime.config.readinessSelector, { timeout: runtime.config.navigationTimeoutMs }), runtime.config.navigationTimeoutMs, 'Readiness selector wait');
    }
    if (runtime.config.pageReadyDelayMs > 0) await page.waitForTimeout(runtime.config.pageReadyDelayMs);
    await inspectManagedPage('startup');
    if (runtime.phase !== 'challenge') runtime.phase = 'ready';
    enqueueEvent('runtime_ready', summarizeRuntime());
    return summarizeRuntime();
  })();

  try {
    return await runtime.startPromise;
  } finally {
    runtime.startPromise = null;
  }
}

async function restartRuntime(reason, patch) {
  runtime.reconnectCount += 1;
  runtime.config = mergeConfig(runtime.config, sanitizeConfigPatch(patch || {}));
  enqueueEvent('runtime_restarting', { reason, reconnectCount: runtime.reconnectCount });
  return startRuntime(reason || 'restart');
}

async function ensureRuntimeReady(reason) {
  if (!runtime.context || !runtime.page || runtime.page.isClosed()) await startRuntime(reason || 'ensure_runtime');
  if (!runtime.page || runtime.page.isClosed()) throw createError(503, 'Managed page is not available');
  await installRuntimeScriptsOnPage(runtime.page);
  await refreshSimulationStatus(runtime.page);
  await refreshWasmStatus(runtime.page);
  await inspectManagedPage('ensure_runtime');
  if (String(runtime.phase).startsWith('challenge')) {
    throw createError(409, 'Challenge page detected', challengeStatusPayload());
  }
  if (runtime.phase !== 'ready') runtime.phase = 'ready';
  return runtime.page;
}

function extractToken(rawToken) {
  if (!rawToken) return '';
  if (rawToken.includes('_')) return rawToken.split('_')[0];
  return rawToken.slice(0, 32);
}

async function getCookieMap(urlForScope) {
  if (!runtime.context) return {};
  const cookies = await runtime.context.cookies(urlForScope ? [urlForScope] : undefined);
  return Object.fromEntries(cookies.map((cookie) => [cookie.name, cookie.value]));
}

function normalizeCookieInput(cookies, defaultUrl) {
  if (!cookies) return [];
  if (Array.isArray(cookies)) return cookies;
  if (typeof cookies !== 'object') throw createError(400, '"cookies" must be an object or an array');
  const targetUrl = defaultUrl || runtime.config.startUrl || DEFAULT_START_URL;
  return Object.entries(cookies).map(([name, value]) => ({ name, value: String(value), url: targetUrl }));
}

async function setCookies(body) {
  const cookies = normalizeCookieInput(body && body.cookies, body && body.url ? body.url : runtime.config.startUrl);
  if (cookies.length === 0) throw createError(400, 'No cookies to set');
  if (!runtime.context) {
    runtime.pendingCookies.push(...cookies);
    enqueueEvent('cookies_queued', { count: cookies.length });
    return { queued: true, count: cookies.length };
  }
  await runtime.context.addCookies(cookies);
  enqueueEvent('cookies_set', { count: cookies.length });
  return { queued: false, count: cookies.length };
}

async function listBridgeTargets() {
  const page = await ensureRuntimeReady('list_bridge_targets');
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  return withTimeout(
    page.evaluate((api) => {
      const runtimeApi = window[api.bridgeName];
      if (!runtimeApi || typeof runtimeApi.list !== 'function') throw new Error('Bridge runtime is unavailable');
      return runtimeApi.list();
    }, handles),
    runtime.config.callTimeoutMs,
    'Bridge list',
  );
}

async function registerBridgeTarget(body) {
  if (!body || !body.name) throw createError(400, 'Missing "name"');
  if (!body.globalPath && !body.resolverSource) throw createError(400, 'Missing "globalPath" or "resolverSource"');
  const page = await ensureRuntimeReady('register_bridge_target');
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  return withTimeout(page.evaluate(({ name, globalPath, ownerPath, resolverSource, resolverArg, api }) => {
    const runtimeApi = window[api.bridgeName];
    if (!runtimeApi) throw new Error('Bridge runtime is unavailable');
    if (globalPath) return runtimeApi.registerGlobal(name, globalPath, ownerPath);
    const factory = (0, eval)(`(${resolverSource})`);
    const resolved = factory(resolverArg || {});
    if (typeof resolved === 'function') return runtimeApi.register(name, resolved, window);
    if (resolved && typeof resolved.fn === 'function') return runtimeApi.register(name, resolved.fn, resolved.thisArg || window);
    if (resolved && typeof resolved.globalPath === 'string') return runtimeApi.registerGlobal(name, resolved.globalPath, resolved.ownerPath);
    throw new Error('resolverSource must return a function or { fn, thisArg }');
  }, {
    name: body.name,
    globalPath: body.globalPath || null,
    ownerPath: body.ownerPath || null,
    resolverSource: body.resolverSource || null,
    resolverArg: body.resolverArg || null,
    api: handles,
  }), runtime.config.callTimeoutMs, 'Bridge register');
}

async function callBridgeTarget(body) {
  if (!body || !body.name) throw createError(400, 'Missing "name"');
  const args = Array.isArray(body.args) ? body.args : body.payload !== undefined ? [body.payload] : [];
  const page = await ensureRuntimeReady('call_bridge_target');
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  return withTimeout(
    page.evaluate(({ name, args, api }) => {
      const runtimeApi = window[api.bridgeName];
      if (!runtimeApi || typeof runtimeApi.call !== 'function') throw new Error('Bridge runtime is unavailable');
      return runtimeApi.call(name, args);
    }, { name: body.name, args, api: handles }),
    runtime.config.callTimeoutMs,
    `Bridge call "${body.name}"`,
  );
}

function normalizeExecutorCandidate(candidate) {
  if (!candidate || typeof candidate !== 'object') return null;
  const normalized = {
    name: candidate.name ? String(candidate.name) : '',
    globalPath: candidate.globalPath ? String(candidate.globalPath) : '',
    ownerPath: candidate.ownerPath ? String(candidate.ownerPath) : '',
    resolverSource: candidate.resolverSource ? String(candidate.resolverSource) : '',
    resolverArg: candidate.resolverArg && typeof candidate.resolverArg === 'object' ? candidate.resolverArg : null,
    score: Number(candidate.score || 0),
    callable: Boolean(candidate.callable || candidate.globalPath || candidate.resolverSource),
    sinkField: candidate.sinkField ? String(candidate.sinkField) : '',
    evidenceFrames: Array.isArray(candidate.evidenceFrames) ? candidate.evidenceFrames.map((item) => String(item)) : [],
  };
  if (!normalized.name) return null;
  return normalized;
}

function executorCandidates() {
  const raw = Array.isArray(runtime.config.executorCandidates) ? runtime.config.executorCandidates : [];
  return raw.map(normalizeExecutorCandidate).filter(Boolean);
}

async function discoverExecutorCandidates(options) {
  const minScore = Number(options && options.minScore != null ? options.minScore : 0);
  const sinkField = options && options.sinkField ? String(options.sinkField) : '';
  const candidates = executorCandidates()
    .filter((candidate) => candidate.score >= minScore)
    .filter((candidate) => !sinkField || !candidate.sinkField || candidate.sinkField === sinkField)
    .sort((left, right) => right.score - left.score || left.name.localeCompare(right.name));
  return candidates;
}

async function registerExecutorCandidate(candidate) {
  if (!candidate) throw createError(404, 'Executor candidate not found');
  if (!candidate.globalPath && !candidate.resolverSource) {
    throw createError(409, `Executor candidate is not callable: ${candidate.name}`);
  }
  return registerBridgeTarget({
    name: candidate.name,
    globalPath: candidate.globalPath || null,
    ownerPath: candidate.ownerPath || null,
    resolverSource: candidate.resolverSource || null,
    resolverArg: candidate.resolverArg || { name: candidate.name },
  });
}

async function invokeExecutor(body) {
  if (!body || !body.name) throw createError(400, 'Missing "name"');
  const args = Array.isArray(body.args) ? body.args : body.payload !== undefined ? [body.payload] : [];
  const autoRegister = body.autoRegister !== false;
  const bridgeTargets = await listBridgeTargets();
  if (!bridgeTargets.includes(body.name) && autoRegister) {
    const candidate = (await discoverExecutorCandidates({
      minScore: Number(body.minScore || 0),
      sinkField: body.sinkField || '',
    })).find((item) => item.name === body.name);
    if (!candidate) {
      throw createError(404, `Executor candidate not found: ${body.name}`);
    }
    await registerExecutorCandidate(candidate);
  }
  return callBridgeTarget({ name: body.name, args });
}

async function signRequest(body) {
  await ensureRuntimeReady('sign_request');
  const inputUrl = body && body.url;
  if (!inputUrl) throw createError(400, 'Missing "url"');
  const urlObject = new URL(inputUrl);
  const params = Object.fromEntries(urlObject.searchParams.entries());
  const cookies = body.cookies && typeof body.cookies === 'object' && !Array.isArray(body.cookies) ? { ...body.cookies } : await getCookieMap(inputUrl);
  const token = extractToken(cookies._m_h5_tk || '');
  const t = params.t || String(Date.now());
  const appKey = params.appKey || body.appKey || runtime.config.appKey || DEFAULT_APP_KEY;
  const data = params.data || body.body || '';
  const sign = token ? md5(`${token}&${t}&${appKey}&${data}`) : '';

  const headers = { t };
  if (sign) headers.sign = sign;
  if (cookies._tb_token_) headers['x-csrf-token'] = cookies._tb_token_;
  if (cookies['x-csrf-token']) headers['x-csrf-token'] = cookies['x-csrf-token'];

  const signerName = body.signer || runtime.config.defaultSigner || '';
  if (signerName) {
    const signerResult = await invokeExecutor({
      name: signerName,
      autoRegister: body.autoRegister !== false,
      args: Array.isArray(body.signerArgs) ? body.signerArgs : [{
        url: inputUrl,
        method: body.method || 'GET',
        body: body.body || '',
        params,
        cookies,
        t,
        appKey,
        sign,
        data,
      }],
    });
    if (signerResult && typeof signerResult === 'object') Object.assign(headers, signerResult.headers || signerResult);
  }

  return {
    headers,
    meta: {
      signerUsed: signerName || null,
      tokenPresent: Boolean(token),
      cookieCount: Object.keys(cookies).length,
      challenge: runtime.lastChallenge,
    },
  };
}

async function navigate(body) {
  if (!body || !body.url) throw createError(400, 'Missing "url"');
  const page = await ensureRuntimeReady('navigate');
  const targetUrl = applyAutomationLabelToUrl(body.url);
  await withTimeout(page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: runtime.config.navigationTimeoutMs }), runtime.config.navigationTimeoutMs, 'Navigation');
  if (runtime.config.readinessSelector) {
    await withTimeout(page.waitForSelector(runtime.config.readinessSelector, { timeout: runtime.config.navigationTimeoutMs }), runtime.config.navigationTimeoutMs, 'Readiness selector wait');
  }
  if (runtime.config.pageReadyDelayMs > 0) await page.waitForTimeout(runtime.config.pageReadyDelayMs);
  const state = await inspectManagedPage('navigate');
  enqueueEvent('navigated', { url: targetUrl });
  if (String(runtime.phase).startsWith('challenge')) throw createError(409, 'Challenge page detected after navigation', challengeStatusPayload());
  return state;
}

async function environmentStatus() {
  if (!runtime.context || !runtime.page || runtime.page.isClosed()) {
    await startRuntime('environment_status');
  }
  const page = runtime.page;
  if (!page || page.isClosed()) throw createError(503, 'Managed page is not available');
  await installRuntimeScriptsOnPage(page).catch(() => {});
  const status = await refreshSimulationStatus(page);
  const wasmStatus = await refreshWasmStatus(page);
  const observed = await collectEnvironmentObservation(page);
  const consistency = buildConsistencyChecks(observed);
  return {
    environment: status ? status.environment : runtime.lastEnvironmentStatus,
    interaction: status ? status.interaction : runtime.lastInteractionStatus,
    wasm: wasmStatus || runtime.lastWasmStatus,
    sessionProfile: runtime.config.sessionProfile || {},
    consistency,
    observed,
    runtime: summarizeRuntime(),
  };
}

async function challengeStatus() {
  if (runtime.page && !runtime.page.isClosed()) await inspectManagedPage('challenge_status').catch(() => {});
  return challengeStatusPayload();
}

async function continueChallenge(body) {
  const policy = runtime.config.challengePolicy || 'fail_fast';
  if (!runtime.lastChallenge) throw createError(409, 'No active challenge to continue');
  if (policy === 'fail_fast') throw createError(409, 'Challenge policy is fail_fast', challengeStatusPayload());

  const bypassToken = body && body.bypassToken ? String(body.bypassToken) : '';
  const expectedToken = runtime.config.authorizedBypassToken ? String(runtime.config.authorizedBypassToken) : '';
  if (policy === 'wait_for_test_bypass_token') {
    if (!bypassToken) throw createError(403, 'Missing bypassToken for wait_for_test_bypass_token', challengeStatusPayload());
    if (expectedToken && bypassToken !== expectedToken) {
      throw createError(403, 'Invalid bypassToken', challengeStatusPayload());
    }
  }

  runtime.challengeState.continueRequestedAt = nowIso();
  runtime.challengeState.tokenVerified = policy === 'wait_for_test_bypass_token';
  runtime.challengeState.awaitingAuthorization = false;
  runtime.challengeState.continuedAt = nowIso();

  if (body && body.cookies) {
    await setCookies({ cookies: body.cookies, url: body.url || runtime.lastUrl || runtime.config.startUrl });
  }
  const page = await ensureRuntimeReady('challenge_continue').catch(() => runtime.page);
  if (page && !page.isClosed()) {
    const targetUrl = applyAutomationLabelToUrl(body && body.url ? body.url : runtime.lastUrl || runtime.config.startUrl);
    if (targetUrl) {
      await withTimeout(page.goto(targetUrl, navigationOptions()), runtime.config.navigationTimeoutMs, 'Challenge continue navigation');
      await inspectManagedPage('challenge_continue');
    }
  }
  enqueueEvent('challenge_continue_requested', { policy, targetUrl: body && body.url ? body.url : runtime.lastUrl || runtime.config.startUrl });
  return challengeStatusPayload();
}

function currentWasmTelemetryConfig() {
  return normalizeWasmTelemetryConfig(runtime.config.wasmTelemetry || {});
}

function sanitizeArtifactName(value) {
  return String(value || 'wasm').replace(/[^a-z0-9._-]+/gi, '_');
}

function ensureWasmArtifactDir() {
  const config = currentWasmTelemetryConfig();
  const artifactDir = path.resolve(String(config.artifactDir || path.join(__dirname, 'wasm_artifacts')));
  fs.mkdirSync(artifactDir, { recursive: true });
  return artifactDir;
}

function wasmRawBinaryPath(moduleId) {
  return path.join(ensureWasmArtifactDir(), `${sanitizeArtifactName(moduleId)}.wasm`);
}

function wasmReportPath(moduleId) {
  return path.join(ensureWasmArtifactDir(), `${sanitizeArtifactName(moduleId)}.report.json`);
}

function wasmSnapshotPath(instanceId, snapshotId) {
  return path.join(ensureWasmArtifactDir(), `${sanitizeArtifactName(instanceId)}.${sanitizeArtifactName(snapshotId)}.snapshot.json`);
}

function cloneData(value) {
  return value == null ? value ?? null : JSON.parse(JSON.stringify(value));
}

function persistWasmModuleReport(report) {
  const cloned = cloneData(report) || {};
  const moduleId = String(cloned.moduleId || '');
  if (!moduleId) throw createError(400, 'WASM report is missing moduleId');
  const artifactPaths = {
    report: wasmReportPath(moduleId),
    rawBinary: null,
  };
  const binary = cloned.binary && typeof cloned.binary === 'object' ? { ...cloned.binary } : {};
  if (binary.base64) {
    const buffer = Buffer.from(String(binary.base64), 'base64');
    binary.sha256 = crypto.createHash('sha256').update(buffer).digest('hex');
    if (currentWasmTelemetryConfig().persistRawBinary !== false) {
      artifactPaths.rawBinary = wasmRawBinaryPath(moduleId);
      fs.writeFileSync(artifactPaths.rawBinary, buffer);
    }
  }
  delete binary.base64;
  cloned.binary = binary;
  cloned.artifactPaths = artifactPaths;
  fs.writeFileSync(artifactPaths.report, JSON.stringify(cloned, null, 2), 'utf8');
  return {
    report: cloned,
    artifactPaths,
    binaryHash: binary.sha256 || null,
  };
}

function persistWasmSnapshots(snapshots) {
  return (Array.isArray(snapshots) ? snapshots : []).map((snapshot) => {
    const cloned = cloneData(snapshot) || {};
    const instanceId = String(cloned.instanceId || 'wasm-instance');
    const snapshotId = String(cloned.snapshotId || Date.now());
    const artifactPath = wasmSnapshotPath(instanceId, snapshotId);
    fs.writeFileSync(artifactPath, JSON.stringify(cloned, null, 2), 'utf8');
    cloned.artifactPath = artifactPath;
    return cloned;
  });
}

async function healthStatus() {
  if (runtime.page && !runtime.page.isClosed()) {
    await refreshSimulationStatus(runtime.page).catch(() => {});
    await refreshWasmStatus(runtime.page).catch(() => {});
  }
  return summarizeRuntime();
}

async function listWasmModules() {
  const page = await ensureRuntimeReady('list_wasm_modules');
  await refreshWasmStatus(page).catch(() => {});
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const modules = await withTimeout(
    page.evaluate((api) => {
      const runtimeApi = window[api.wasmName];
      if (!runtimeApi || typeof runtimeApi.listModules !== 'function') throw new Error('WASM runtime is unavailable');
      return runtimeApi.listModules();
    }, handles),
    runtime.config.callTimeoutMs,
    'WASM modules',
  );
  const hydrated = [];
  for (const moduleSummary of Array.isArray(modules) ? modules : []) {
    try {
      const report = await withTimeout(
        page.evaluate(({ moduleId, api }) => {
          const runtimeApi = window[api.wasmName];
          if (!runtimeApi || typeof runtimeApi.getReport !== 'function') throw new Error('WASM runtime is unavailable');
          return runtimeApi.getReport(moduleId, { includeBinary: true });
        }, { moduleId: moduleSummary.moduleId, api: handles }),
        runtime.config.callTimeoutMs,
        'WASM report hydrate',
      );
      const persisted = persistWasmModuleReport(report);
      hydrated.push({
        ...moduleSummary,
        binaryHash: persisted.binaryHash,
        artifactPaths: persisted.artifactPaths,
      });
    } catch (_error) {
      hydrated.push({
        ...moduleSummary,
        artifactPaths: {
          report: wasmReportPath(moduleSummary.moduleId),
          rawBinary: currentWasmTelemetryConfig().persistRawBinary !== false ? wasmRawBinaryPath(moduleSummary.moduleId) : null,
        },
      });
    }
  }
  return hydrated;
}

async function getWasmReport(moduleId) {
  if (!moduleId) throw createError(400, 'Missing moduleId');
  const page = await ensureRuntimeReady('get_wasm_report');
  await refreshWasmStatus(page).catch(() => {});
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const report = await withTimeout(
    page.evaluate(({ moduleId: targetModuleId, api }) => {
      const runtimeApi = window[api.wasmName];
      if (!runtimeApi || typeof runtimeApi.getReport !== 'function') throw new Error('WASM runtime is unavailable');
      return runtimeApi.getReport(targetModuleId, { includeBinary: true });
    }, { moduleId, api: handles }),
    runtime.config.callTimeoutMs,
    'WASM report',
  );
  return persistWasmModuleReport(report).report;
}

async function getWasmSnapshots(instanceId, sinceId) {
  const page = await ensureRuntimeReady('get_wasm_snapshots');
  await refreshWasmStatus(page).catch(() => {});
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const snapshots = await withTimeout(
    page.evaluate(({ instanceId: targetInstanceId, sinceId: targetSinceId, api }) => {
      const runtimeApi = window[api.wasmName];
      if (!runtimeApi || typeof runtimeApi.getSnapshots !== 'function') throw new Error('WASM runtime is unavailable');
      return runtimeApi.getSnapshots(targetInstanceId || null, targetSinceId);
    }, {
      instanceId: instanceId || null,
      sinceId: sinceId || 0,
      api: handles,
    }),
    runtime.config.callTimeoutMs,
    'WASM snapshots',
  );
  return persistWasmSnapshots(snapshots);
}

async function invokeWasmExport(body) {
  if (!body || !body.exportName) throw createError(400, 'Missing exportName');
  if (!body.moduleId && !body.instanceId) throw createError(400, 'Missing moduleId or instanceId');
  const page = await ensureRuntimeReady('invoke_wasm_export');
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const invocation = await withTimeout(
    page.evaluate((payload) => {
      const runtimeApi = window[payload.api.wasmName];
      if (!runtimeApi || typeof runtimeApi.invoke !== 'function') throw new Error('WASM runtime is unavailable');
      return runtimeApi.invoke(payload);
    }, {
      moduleId: body.moduleId || null,
      instanceId: body.instanceId || null,
      exportName: body.exportName,
      args: Array.isArray(body.args) ? body.args : body.payload !== undefined ? [body.payload] : [],
      bufferDescriptors: Array.isArray(body.bufferDescriptors) ? body.bufferDescriptors : [],
      captureMemory: body.captureMemory !== false,
      snapshotMode: body.snapshotMode || null,
      api: handles,
    }),
    runtime.config.callTimeoutMs,
    `WASM invoke "${body.exportName}"`,
  );
  await refreshWasmStatus(page).catch(() => {});
  const persistedSnapshots = invocation && invocation.snapshot ? persistWasmSnapshots([invocation.snapshot]) : [];
  return {
    ...invocation,
    snapshot: persistedSnapshots.length > 0 ? persistedSnapshots[0] : null,
  };
}

function normalizeTracePayload(body) {
  if (body && Array.isArray(body.points)) return body.points;
  if (body && Array.isArray(body.trace)) return body.trace;
  if (body && body.trace && Array.isArray(body.trace.points)) return body.trace.points;
  return null;
}

function readTraceFile(tracePath) {
  const resolved = path.resolve(String(tracePath));
  if (!fs.existsSync(resolved)) throw createError(400, `tracePath does not exist: ${resolved}`);
  let parsed = null;
  try {
    parsed = JSON.parse(fs.readFileSync(resolved, 'utf8'));
  } catch (error) {
    throw createError(400, `tracePath is not valid JSON: ${resolved}`, serializeError(error));
  }
  const points = normalizeTracePayload(parsed);
  if (!points) throw createError(400, `tracePath does not contain trace points: ${resolved}`);
  return { points, resolved };
}

async function buildPointerPath(body) {
  const page = await ensureRuntimeReady('build_pointer_path');
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const pathResult = await withTimeout(
    page.evaluate(({ options, api }) => {
      const runtimeApi = window[api.interactionName];
      if (!runtimeApi || typeof runtimeApi.buildPointerPath !== 'function') throw new Error('Interaction runtime is unavailable');
      return runtimeApi.buildPointerPath(options || {});
    }, { options: body || {}, api: handles }),
    runtime.config.callTimeoutMs,
    'Pointer path generation',
  );
  await refreshSimulationStatus(page);
  await refreshWasmStatus(page);
  return pathResult;
}

async function dispatchPointerPath(page, pathResult, body, metrics) {
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const dispatchResult = await withTimeout(
    page.evaluate(({ pathPayload, options, api }) => {
      const runtimeApi = window[api.interactionName];
      if (!runtimeApi || typeof runtimeApi.dispatchPointerPath !== 'function') throw new Error('Interaction runtime is unavailable');
      return runtimeApi.dispatchPointerPath(pathPayload, options || {});
    }, {
      pathPayload: pathResult,
      options: body || {},
      api: handles,
    }),
    runtime.config.callTimeoutMs,
    'Pointer dispatch',
  );
  metrics.eventsEmitted = dispatchResult && Number.isFinite(Number(dispatchResult.eventsEmitted))
    ? Number(dispatchResult.eventsEmitted)
    : metrics.points;
  return dispatchResult;
}

async function performMousePath(page, pathResult, metrics) {
  const points = Array.isArray(pathResult && pathResult.points) ? pathResult.points : [];
  if (points.length === 0) throw createError(400, 'Pointer path contains no points');
  let previousTs = 0;
  for (const point of points) {
    const delta = Math.max(0, Math.round(Number(point.ts || 0) - previousTs));
    if (delta > 0) await page.waitForTimeout(delta);
    await page.mouse.move(Number(point.x), Number(point.y), { steps: 1 });
    previousTs = Math.round(Number(point.ts || 0));
  }
  metrics.eventsEmitted = points.length;
}

function makeInteractionMetrics(mode, pathResult) {
  const points = Array.isArray(pathResult && pathResult.points) ? pathResult.points : [];
  const durationMs = points.length > 0 ? Math.round(Number(points[points.length - 1].ts || 0)) : Math.round(Number(pathResult && pathResult.durationMs || 0));
  return {
    runId: null,
    sessionId: runtime.runtimeSessionId,
    seed: pathResult && pathResult.seed != null ? pathResult.seed : null,
    points: points.length,
    durationMs,
    avgStepMs: points.length > 1 ? Number((durationMs / (points.length - 1)).toFixed(2)) : durationMs,
    mode,
    eventsEmitted: 0,
    errors: [],
  };
}

function interactionContext(body, pathResult) {
  const engine = runtime.config.interactionEngine || {};
  const fallbackSeed = engine.defaultSeed != null
    ? Number(engine.defaultSeed)
    : engine.pointer && engine.pointer.defaultSeed != null
      ? Number(engine.pointer.defaultSeed)
      : 1337;
  return {
    runId: body && body.runId ? String(body.runId) : createRuntimeSessionId(),
    sessionId: body && body.sessionId ? String(body.sessionId) : runtime.runtimeSessionId,
    seed: body && body.seed != null
      ? Number(body.seed)
      : pathResult && pathResult.seed != null
        ? Number(pathResult.seed)
        : fallbackSeed,
  };
}

function makeDeterministicRng(seed) {
  let value = Number(seed) >>> 0;
  if (!value) value = 1;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

async function runScrollPerturbation(page, step, context, metrics) {
  const config = runtime.config.interactionEngine && runtime.config.interactionEngine.scroll
    ? runtime.config.interactionEngine.scroll
    : {};
  const rng = makeDeterministicRng(context.seed + Number(step.index || 0));
  const baseDelta = Number(step.deltaY != null ? step.deltaY : (step.direction === 'up' ? -120 : 120));
  const jitter = Number(config.jitterPx != null ? config.jitterPx : 18);
  const stepDelayMs = Number(step.stepDelayMs != null ? step.stepDelayMs : (config.stepDelayMs != null ? config.stepDelayMs : 24));
  const repeats = Math.max(1, Math.round(Number(step.repeats != null ? step.repeats : 3)));
  for (let index = 0; index < repeats; index += 1) {
    const deltaY = baseDelta + ((rng() - 0.5) * jitter);
    await page.mouse.wheel(0, deltaY);
    metrics.eventsEmitted += 1;
    if (stepDelayMs > 0) await page.waitForTimeout(stepDelayMs);
  }
}

async function runClickDelay(page, step, context, metrics) {
  const config = runtime.config.interactionEngine && runtime.config.interactionEngine.click
    ? runtime.config.interactionEngine.click
    : {};
  const rng = makeDeterministicRng(context.seed + Number(step.index || 0) + 17);
  const baseDelayMs = Number(step.baseDelayMs != null ? step.baseDelayMs : (config.baseDelayMs != null ? config.baseDelayMs : 100));
  const jitterMs = Number(step.jitterMs != null ? step.jitterMs : (config.jitterMs != null ? config.jitterMs : 55));
  const delayMs = Math.max(0, Math.round(baseDelayMs + ((rng() - 0.5) * jitterMs)));
  if (delayMs > 0) await page.waitForTimeout(delayMs);

  if (step.selector) {
    const locator = page.locator(String(step.selector)).first();
    await locator.click({ delay: 0, button: step.button || 'left' });
  } else if (Number.isFinite(Number(step.x)) && Number.isFinite(Number(step.y))) {
    await page.mouse.click(Number(step.x), Number(step.y), { button: step.button || 'left', delay: 0 });
  } else {
    throw createError(400, 'Click step requires "selector" or "x"/"y" coordinates');
  }
  metrics.eventsEmitted += 1;
}

async function runPointerPath(body) {
  const page = await ensureRuntimeReady('run_pointer_path');
  const pathResult = await buildPointerPath(body || {});
  const context = interactionContext(body, pathResult);
  const requestedMode = body && body.dispatchMode ? String(body.dispatchMode) : '';
  const defaultMode = runtime.config.interactionSimulation && runtime.config.interactionSimulation.mode
    ? String(runtime.config.interactionSimulation.mode)
    : 'playwright_mouse';
  const mode = requestedMode || defaultMode;
  const metrics = makeInteractionMetrics(mode, pathResult);
  metrics.runId = context.runId;
  metrics.sessionId = context.sessionId;
  metrics.seed = context.seed;
  enqueueEvent('pointer_path_started', { runId: context.runId, sessionId: context.sessionId, seed: context.seed, mode });
  try {
    if (mode === 'dispatch') {
      await dispatchPointerPath(page, pathResult, body, metrics);
    } else {
      await performMousePath(page, pathResult, metrics);
    }
  } catch (error) {
    metrics.errors.push(serializeError(error));
    throw error;
  } finally {
    await refreshSimulationStatus(page).catch(() => {});
    await refreshWasmStatus(page).catch(() => {});
  }
  enqueueEvent('pointer_path_completed', metrics);
  return metrics;
}

async function replayPointerTrace(body) {
  const page = await ensureRuntimeReady('replay_pointer_trace');
  let points = normalizeTracePayload(body);
  let tracePath = null;
  if (!points && body && body.tracePath) {
    const loaded = readTraceFile(body.tracePath);
    points = loaded.points;
    tracePath = loaded.resolved;
  }
  if (!points) throw createError(400, 'Missing "points", "trace", or "tracePath"');
  const handles = runtime.config.simulationHandles || defaultSimulationHandles();
  const normalized = await withTimeout(
    page.evaluate(({ trace, api }) => {
      const runtimeApi = window[api.interactionName];
      if (!runtimeApi || typeof runtimeApi.normalizeTracePoints !== 'function') throw new Error('Interaction runtime is unavailable');
      return runtimeApi.normalizeTracePoints(trace);
    }, { trace: { points }, api: handles }),
    runtime.config.callTimeoutMs,
    'Trace normalization',
  );
  const pathResult = { points: normalized };
  const requestedMode = body && body.dispatchMode ? String(body.dispatchMode) : '';
  const defaultMode = runtime.config.interactionSimulation && runtime.config.interactionSimulation.mode
    ? String(runtime.config.interactionSimulation.mode)
    : 'playwright_mouse';
  const mode = requestedMode || defaultMode;
  const metrics = makeInteractionMetrics(mode, pathResult);
  const context = interactionContext(body, pathResult);
  metrics.runId = context.runId;
  metrics.sessionId = context.sessionId;
  metrics.seed = context.seed;
  if (tracePath) metrics.tracePath = tracePath;
  enqueueEvent('pointer_trace_started', { runId: context.runId, sessionId: context.sessionId, seed: context.seed, mode, tracePath });
  try {
    if (mode === 'dispatch') {
      await dispatchPointerPath(page, pathResult, body, metrics);
    } else {
      await performMousePath(page, pathResult, metrics);
    }
  } catch (error) {
    metrics.errors.push(serializeError(error));
    throw error;
  } finally {
    await refreshSimulationStatus(page).catch(() => {});
    await refreshWasmStatus(page).catch(() => {});
  }
  enqueueEvent('pointer_trace_completed', metrics);
  return metrics;
}

async function runInteractionScenario(body) {
  const page = await ensureRuntimeReady('run_interaction_scenario');
  const scenario = body && Array.isArray(body.steps)
    ? body.steps
    : body && body.scenario && Array.isArray(body.scenario.steps)
      ? body.scenario.steps
      : [];
  if (scenario.length === 0) throw createError(400, 'Interaction scenario requires a non-empty "steps" array');

  const context = interactionContext(body, null);
  const summary = {
    runId: context.runId,
    sessionId: context.sessionId,
    seed: context.seed,
    steps: [],
    eventsEmitted: 0,
    errors: [],
    challengeState: null,
  };
  enqueueEvent('interaction_scenario_started', { runId: context.runId, sessionId: context.sessionId, seed: context.seed, stepCount: scenario.length });

  for (let index = 0; index < scenario.length; index += 1) {
    const step = scenario[index] || {};
    const type = String(step.type || '');
    const stepSummary = { index, type, startedAt: nowIso() };
    try {
      if (type === 'pointer_path') {
        const metrics = await runPointerPath({ ...body, ...step, runId: context.runId, sessionId: context.sessionId, seed: step.seed != null ? step.seed : context.seed });
        stepSummary.metrics = metrics;
        summary.eventsEmitted += Number(metrics.eventsEmitted || 0);
      } else if (type === 'replay_pointer_trace') {
        const metrics = await replayPointerTrace({ ...body, ...step, runId: context.runId, sessionId: context.sessionId, seed: step.seed != null ? step.seed : context.seed });
        stepSummary.metrics = metrics;
        summary.eventsEmitted += Number(metrics.eventsEmitted || 0);
      } else if (type === 'scroll') {
        const metrics = makeInteractionMetrics('scroll', { seed: context.seed, points: [] });
        metrics.runId = context.runId;
        metrics.sessionId = context.sessionId;
        metrics.seed = context.seed;
        await runScrollPerturbation(page, { ...step, index }, context, metrics);
        stepSummary.metrics = metrics;
        summary.eventsEmitted += Number(metrics.eventsEmitted || 0);
      } else if (type === 'click') {
        const metrics = makeInteractionMetrics('click', { seed: context.seed, points: [] });
        metrics.runId = context.runId;
        metrics.sessionId = context.sessionId;
        metrics.seed = context.seed;
        await runClickDelay(page, { ...step, index }, context, metrics);
        stepSummary.metrics = metrics;
        summary.eventsEmitted += Number(metrics.eventsEmitted || 0);
      } else if (type === 'wait') {
        const waitMs = Math.max(0, Math.round(Number(step.durationMs != null ? step.durationMs : step.ms)));
        if (waitMs > 0) await page.waitForTimeout(waitMs);
        stepSummary.metrics = { mode: 'wait', durationMs: waitMs, eventsEmitted: 0, runId: context.runId, sessionId: context.sessionId, seed: context.seed };
      } else {
        throw createError(400, `Unsupported interaction step type: ${type}`);
      }
      stepSummary.completedAt = nowIso();
      summary.steps.push(stepSummary);
      await refreshSimulationStatus(page).catch(() => {});
      await refreshWasmStatus(page).catch(() => {});
      if (String(runtime.phase).startsWith('challenge')) {
        summary.challengeState = challengeStatusPayload();
        break;
      }
    } catch (error) {
      stepSummary.error = serializeError(error);
      stepSummary.completedAt = nowIso();
      summary.steps.push(stepSummary);
      summary.errors.push(serializeError(error));
      enqueueEvent('interaction_scenario_step_failed', { runId: context.runId, sessionId: context.sessionId, index, type, error: serializeError(error) });
      throw error;
    }
  }

  enqueueEvent('interaction_scenario_completed', summary);
  return summary;
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let chunks = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      chunks += chunk;
      if (Buffer.byteLength(chunks, 'utf8') > MAX_BODY_BYTES) {
        reject(createError(413, 'Request body is too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!chunks.trim()) return resolve({});
      try {
        resolve(JSON.parse(chunks));
      } catch (error) {
        reject(createError(400, 'Invalid JSON request body', serializeError(error)));
      }
    });
    req.on('error', (error) => reject(createError(400, 'Failed to read request body', serializeError(error))));
  });
}

function sendJson(res, statusCode, payload) {
  const body = Buffer.from(JSON.stringify(payload, null, 2));
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': String(body.length),
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

function drainEvents(sinceId) {
  const since = Number.isFinite(Number(sinceId)) ? Number(sinceId) : 0;
  return runtime.events.filter((event) => event.id > since);
}

async function routeRequest(req, res) {
  const parsedUrl = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const pathname = parsedUrl.pathname;
  const method = req.method || 'GET';

  if (method === 'GET' && pathname === '/health') return sendJson(res, 200, await healthStatus());
  if (method === 'GET' && pathname === '/events') {
    if (runtime.page && !runtime.page.isClosed()) await refreshWasmStatus(runtime.page).catch(() => {});
    return sendJson(res, 200, { events: drainEvents(parsedUrl.searchParams.get('since')), nextCursor: runtime.nextEventId });
  }
  if (method === 'GET' && pathname === '/bridge/list') return sendJson(res, 200, { targets: await listBridgeTargets() });
  if (method === 'GET' && pathname === '/executor/discover') {
    return sendJson(res, 200, {
      candidates: await discoverExecutorCandidates({
        minScore: parsedUrl.searchParams.get('min_score'),
        sinkField: parsedUrl.searchParams.get('sink_field'),
      }),
    });
  }
  if (method === 'GET' && pathname === '/wasm/modules') return sendJson(res, 200, { modules: await listWasmModules() });
  if (method === 'GET' && pathname === '/wasm/report') {
    return sendJson(res, 200, await getWasmReport(parsedUrl.searchParams.get('moduleId') || ''));
  }
  if (method === 'GET' && pathname === '/wasm/snapshots') {
    return sendJson(res, 200, {
      snapshots: await getWasmSnapshots(parsedUrl.searchParams.get('instanceId') || '', parsedUrl.searchParams.get('since') || 0),
    });
  }
  if (method === 'GET' && pathname === '/environment/status') return sendJson(res, 200, await environmentStatus());
  if (method === 'GET' && pathname === '/challenge/status') return sendJson(res, 200, await challengeStatus());
  if (method !== 'POST') return sendJson(res, 404, { error: 'Not found' });

  const body = await readJsonBody(req);
  if (pathname === '/init') return sendJson(res, 200, await restartRuntime('init', body));
  if (pathname === '/restart') return sendJson(res, 200, await restartRuntime('manual_restart', body));
  if (pathname === '/stop') return sendJson(res, 200, await closeRuntime(true).then(() => { runtime.phase = 'stopped'; return summarizeRuntime(); }));
  if (pathname === '/navigate') return sendJson(res, 200, await navigate(body));
  if (pathname === '/set-cookies') return sendJson(res, 200, await setCookies(body));
  if (pathname === '/challenge/continue') return sendJson(res, 200, await continueChallenge(body));
  if (pathname === '/bridge/register') return sendJson(res, 200, await registerBridgeTarget(body));
  if (pathname === '/bridge/call') return sendJson(res, 200, { result: await callBridgeTarget(body) });
  if (pathname === '/wasm/invoke') return sendJson(res, 200, await invokeWasmExport(body));
  if (pathname === '/executor/invoke') return sendJson(res, 200, { result: await invokeExecutor(body) });
  if (pathname === '/interaction/run-pointer-path') return sendJson(res, 200, await runPointerPath(body));
  if (pathname === '/interaction/replay-pointer-trace') return sendJson(res, 200, await replayPointerTrace(body));
  if (pathname === '/interaction/run-scenario') return sendJson(res, 200, await runInteractionScenario(body));
  if (pathname === '/sign') return sendJson(res, 200, await signRequest(body));
  return sendJson(res, 404, { error: 'Not found' });
}

function attachProcessHandlers(server) {
  const shutdown = async (signal) => {
    enqueueEvent('process_shutdown', { signal });
    try {
      await closeRuntime(true);
    } finally {
      server.close(() => process.exit(0));
      setTimeout(() => process.exit(0), 1500).unref();
    }
  };
  process.on('SIGINT', () => shutdown('SIGINT').catch(() => process.exit(1)));
  process.on('SIGTERM', () => shutdown('SIGTERM').catch(() => process.exit(1)));
  process.on('uncaughtException', (error) => setRuntimeError('Uncaught exception', serializeError(error)));
  process.on('unhandledRejection', (error) => setRuntimeError('Unhandled rejection', serializeError(error)));
}

const server = http.createServer((req, res) => {
  routeRequest(req, res).catch((error) => {
    const statusCode = error.statusCode || 500;
    if (statusCode >= 500) setRuntimeError(error.message || 'Unhandled bridge error', serializeError(error));
    sendJson(res, statusCode, { error: error.message || 'Internal server error', details: error.details || null, runtime: summarizeRuntime() });
  });
});

attachProcessHandlers(server);

server.listen(PORT, () => {
  console.log(`[bridge] Server listening on http://127.0.0.1:${PORT}`);
  console.log(`[bridge] ${playwright ? `Playwright module loaded: ${playwrightInfo.name}` : 'Playwright module not installed; /init will return 503 until installed.'}`);
  enqueueEvent('server_started', { port: PORT, dependency: dependencyStatus() });
});
