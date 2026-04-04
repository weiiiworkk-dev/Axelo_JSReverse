'use strict';

const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { URL } = require('url');

const PORT = Number(process.env.AXELO_BRIDGE_PORT || __AXELO_BRIDGE_PORT__);
const DEFAULT_START_URL = process.env.AXELO_BRIDGE_START_URL || __AXELO_START_URL__;
const DEFAULT_STORAGE_STATE_PATH = process.env.AXELO_BRIDGE_STORAGE_STATE || __AXELO_STORAGE_STATE_PATH__;
const DEFAULT_APP_KEY = process.env.AXELO_BRIDGE_APP_KEY || __AXELO_DEFAULT_APP_KEY__;
const MAX_BODY_BYTES = 1024 * 1024;
const MAX_EVENTS = 200;

const playwrightInfo = tryRequire(['playwright', 'playwright-core']);
const playwright = playwrightInfo ? playwrightInfo.module : null;

const BRIDGE_INIT_SCRIPT = String.raw`
(() => {
  const root = window;
  const apiName = "__AXELO_BRIDGE__";
  const stateKey = Symbol.for("axelo.bridge.runtime");
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
})();
`;

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
  lastUrl: '',
  lastTitle: '',
  nextEventId: 0,
  events: [],
  config: defaultConfig(),
};

function defaultConfig() {
  return {
    startUrl: DEFAULT_START_URL,
    appKey: DEFAULT_APP_KEY,
    headless: process.env.AXELO_BRIDGE_HEADLESS === 'false' ? false : true,
    channel: process.env.AXELO_BRIDGE_CHANNEL || undefined,
    storageStatePath: DEFAULT_STORAGE_STATE_PATH || '',
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
    defaultSigner: '',
    challengeUrlPatterns: ['captcha', 'challenge', 'verify', 'punish', 'x5secdata'],
    challengeTitlePatterns: ['captcha', 'challenge', 'verify'],
    challengeTextPatterns: ['captcha', 'challenge', 'verify', 'slider', 'human', 'fail_sys_user_validate', 'rgv587_error', 'x5secdata'],
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

function mergeConfig(current, patch) {
  const next = { ...current };
  for (const [key, value] of Object.entries(patch || {})) {
    if (value === undefined) continue;
    if (key === 'viewport' && value && typeof value === 'object') {
      next.viewport = { ...current.viewport, ...value };
      continue;
    }
    next[key] = value;
  }
  return next;
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
      defaultSigner: runtime.config.defaultSigner || null,
    },
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

async function installBridgeOnPage(page) {
  await withTimeout(page.evaluate(BRIDGE_INIT_SCRIPT), Math.min(runtime.config.callTimeoutMs, 3000), 'Bridge injection');
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
    runtime.lastChallenge = { at: nowIso(), source, url: runtime.lastUrl, title: runtime.lastTitle, findings };
    runtime.phase = 'challenge';
    enqueueEvent('challenge_detected', runtime.lastChallenge);
    if (runtime.config.autoRestartOnChallenge) scheduleRestart('challenge_detected');
  } else if (runtime.phase !== 'reconnecting' && runtime.phase !== 'starting') {
    runtime.lastChallenge = null;
    runtime.phase = 'ready';
  }

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
    if (!runtime.shuttingDown) await installBridgeOnPage(page).catch((error) => setRuntimeError('Bridge injection failed', serializeError(error)));
  });
  page.on('load', async () => {
    if (!runtime.shuttingDown) await inspectManagedPage('load');
  });
  page.on('framenavigated', async (frame) => {
    if (!runtime.shuttingDown && frame === page.mainFrame()) await inspectManagedPage('navigation');
  });

  await installBridgeOnPage(page);
}

async function createBrowserRuntime() {
  if (!playwright) throw createError(503, 'Playwright is not installed for Node.js.', dependencyStatus());
  const chromium = playwright.chromium;
  const browserOptions = { headless: runtime.config.headless };
  if (runtime.config.channel) browserOptions.channel = runtime.config.channel;
  runtime.browser = await chromium.launch(browserOptions);

  const contextOptions = {
    locale: runtime.config.locale,
    timezoneId: runtime.config.timezoneId,
    viewport: runtime.config.viewport,
  };
  const storageState = readStorageStateIfAny();
  if (storageState) contextOptions.storageState = storageState;
  runtime.context = await runtime.browser.newContext(contextOptions);
  await runtime.context.addInitScript(BRIDGE_INIT_SCRIPT);

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
      await withTimeout(page.goto(runtime.config.startUrl, navigationOptions()), runtime.config.navigationTimeoutMs, 'Initial navigation');
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
  runtime.config = mergeConfig(runtime.config, patch || {});
  enqueueEvent('runtime_restarting', { reason, reconnectCount: runtime.reconnectCount });
  return startRuntime(reason || 'restart');
}

async function ensureRuntimeReady(reason) {
  if (!runtime.context || !runtime.page || runtime.page.isClosed()) await startRuntime(reason || 'ensure_runtime');
  if (!runtime.page || runtime.page.isClosed()) throw createError(503, 'Managed page is not available');
  await installBridgeOnPage(runtime.page);
  await inspectManagedPage('ensure_runtime');
  if (runtime.phase === 'challenge') throw createError(409, 'Challenge page detected', runtime.lastChallenge);
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
  return withTimeout(page.evaluate(() => window.__AXELO_BRIDGE__.list()), runtime.config.callTimeoutMs, 'Bridge list');
}

async function registerBridgeTarget(body) {
  if (!body || !body.name) throw createError(400, 'Missing "name"');
  if (!body.globalPath && !body.resolverSource) throw createError(400, 'Missing "globalPath" or "resolverSource"');
  const page = await ensureRuntimeReady('register_bridge_target');
  return withTimeout(page.evaluate(({ name, globalPath, ownerPath, resolverSource, resolverArg }) => {
    if (globalPath) return window.__AXELO_BRIDGE__.registerGlobal(name, globalPath, ownerPath);
    const factory = (0, eval)(`(${resolverSource})`);
    const resolved = factory(resolverArg || {});
    if (typeof resolved === 'function') return window.__AXELO_BRIDGE__.register(name, resolved, window);
    if (resolved && typeof resolved.fn === 'function') return window.__AXELO_BRIDGE__.register(name, resolved.fn, resolved.thisArg || window);
    if (resolved && typeof resolved.globalPath === 'string') return window.__AXELO_BRIDGE__.registerGlobal(name, resolved.globalPath, resolved.ownerPath);
    throw new Error('resolverSource must return a function or { fn, thisArg }');
  }, {
    name: body.name,
    globalPath: body.globalPath || null,
    ownerPath: body.ownerPath || null,
    resolverSource: body.resolverSource || null,
    resolverArg: body.resolverArg || null,
  }), runtime.config.callTimeoutMs, 'Bridge register');
}

async function callBridgeTarget(body) {
  if (!body || !body.name) throw createError(400, 'Missing "name"');
  const args = Array.isArray(body.args) ? body.args : body.payload !== undefined ? [body.payload] : [];
  const page = await ensureRuntimeReady('call_bridge_target');
  return withTimeout(page.evaluate(({ name, args }) => window.__AXELO_BRIDGE__.call(name, args), { name: body.name, args }), runtime.config.callTimeoutMs, `Bridge call "${body.name}"`);
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
    const signerResult = await callBridgeTarget({
      name: signerName,
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
  await withTimeout(page.goto(body.url, { waitUntil: 'domcontentloaded', timeout: runtime.config.navigationTimeoutMs }), runtime.config.navigationTimeoutMs, 'Navigation');
  if (runtime.config.readinessSelector) {
    await withTimeout(page.waitForSelector(runtime.config.readinessSelector, { timeout: runtime.config.navigationTimeoutMs }), runtime.config.navigationTimeoutMs, 'Readiness selector wait');
  }
  if (runtime.config.pageReadyDelayMs > 0) await page.waitForTimeout(runtime.config.pageReadyDelayMs);
  const state = await inspectManagedPage('navigate');
  enqueueEvent('navigated', { url: body.url });
  if (runtime.phase === 'challenge') throw createError(409, 'Challenge page detected after navigation', state);
  return state;
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

  if (method === 'GET' && pathname === '/health') return sendJson(res, 200, summarizeRuntime());
  if (method === 'GET' && pathname === '/events') return sendJson(res, 200, { events: drainEvents(parsedUrl.searchParams.get('since')), nextCursor: runtime.nextEventId });
  if (method === 'GET' && pathname === '/bridge/list') return sendJson(res, 200, { targets: await listBridgeTargets() });
  if (method !== 'POST') return sendJson(res, 404, { error: 'Not found' });

  const body = await readJsonBody(req);
  if (pathname === '/init') return sendJson(res, 200, await restartRuntime('init', body));
  if (pathname === '/restart') return sendJson(res, 200, await restartRuntime('manual_restart', body));
  if (pathname === '/stop') return sendJson(res, 200, await closeRuntime(true).then(() => { runtime.phase = 'stopped'; return summarizeRuntime(); }));
  if (pathname === '/navigate') return sendJson(res, 200, await navigate(body));
  if (pathname === '/set-cookies') return sendJson(res, 200, await setCookies(body));
  if (pathname === '/bridge/register') return sendJson(res, 200, await registerBridgeTarget(body));
  if (pathname === '/bridge/call') return sendJson(res, 200, { result: await callBridgeTarget(body) });
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
