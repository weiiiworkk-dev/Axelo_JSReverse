/**
 * isolated-vm 沙箱执行
 * 在安全隔离的 V8 上下文中运行目标 JS，注入 Hook 记录 API 调用
 */

/**
 * @param {object} params
 * @param {string} params.source       - 要执行的 JS 源码
 * @param {string[]} params.hookTargets - 需要 Hook 的 API 路径列表
 * @param {string} params.callExpr     - 执行后调用的入口表达式，如 "sign('hello')"
 * @param {number} params.timeoutMs    - 执行超时（毫秒）
 */
export async function executeSandboxed({ source, hookTargets = [], callExpr = '', timeoutMs = 5000 }) {
  let ivm;
  try {
    ivm = await import('isolated-vm');
  } catch {
    return {
      success: false,
      error: 'isolated-vm not installed. Run: npm install in axelo/js_tools/scripts/',
      intercepts: [],
    };
  }

  const isolate = new ivm.Isolate({ memoryLimit: 128 });
  const context = await isolate.createContext();
  const jail = context.global;

  // 注入最小浏览器 shim
  await jail.set('global', jail.derefInto());
  await context.eval(`
    var window = global;
    var navigator = {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      platform: 'Win32',
      language: 'zh-CN',
      languages: ['zh-CN', 'en'],
      cookieEnabled: true,
      hardwareConcurrency: 8,
    };
    var document = { cookie: '', referrer: '' };
    var location = { href: 'https://example.com/', hostname: 'example.com', protocol: 'https:' };
    var screen = { width: 1920, height: 1080, colorDepth: 24 };
    var localStorage = { _d: {}, getItem(k){ return this._d[k]||null; }, setItem(k,v){ this._d[k]=v; } };
    var sessionStorage = { _d: {}, getItem(k){ return this._d[k]||null; }, setItem(k,v){ this._d[k]=v; } };
    function btoa(s){ return Buffer.from(s,'binary').toString('base64'); }
    function atob(s){ return Buffer.from(s,'base64').toString('binary'); }
  `);

  // Hook 记录收集器
  const intercepts = [];
  const hookLog = new ivm.Reference(function(api, argsJson, returnJson, stackJson) {
    intercepts.push({
      api_name: api,
      args_repr: argsJson,
      return_repr: returnJson,
      stack_trace: JSON.parse(stackJson || '[]'),
      timestamp: Date.now() / 1000,
      sequence: intercepts.length,
    });
  });
  await jail.set('__axelo_hook_log', hookLog);

  // 生成 Hook 注入代码
  const hookCode = buildHookCode(hookTargets);
  if (hookCode) {
    await context.eval(hookCode);
  }

  // 执行目标代码
  let execResult = null;
  let execError = null;
  try {
    await context.eval(source, { timeout: timeoutMs });
    if (callExpr) {
      execResult = await context.eval(callExpr, { timeout: timeoutMs });
    }
  } catch (err) {
    execError = err.message;
  } finally {
    isolate.dispose();
  }

  return {
    success: execError === null,
    error: execError,
    intercepts,
    result: execResult,
  };
}

/**
 * 根据 Hook 目标列表生成 Proxy 拦截代码
 */
function buildHookCode(targets) {
  if (!targets.length) return '';

  const lines = [
    '(function() {',
    '  function __hook(api, orig) {',
    '    return function(...args) {',
    '      let ret;',
    '      try { ret = orig.apply(this, args); } catch(e) { throw e; }',
    '      try {',
    '        const argsJson = JSON.stringify(args, safeReplacer);',
    '        const retJson = JSON.stringify(ret, safeReplacer);',
    '        const stack = new Error().stack.split("\\n").slice(2, 6);',
    '        __axelo_hook_log.applyIgnored(undefined, [api, argsJson, retJson, JSON.stringify(stack)]);',
    '      } catch(_) {}',
    '      return ret;',
    '    };',
    '  }',
    '  function safeReplacer(k, v) {',
    '    if (v instanceof ArrayBuffer) return { __type: "ArrayBuffer", hex: bufToHex(v) };',
    '    if (v instanceof Uint8Array) return { __type: "Uint8Array", hex: bufToHex(v.buffer) };',
    '    if (typeof v === "function") return "[Function]";',
    '    return v;',
    '  }',
    '  function bufToHex(buf) {',
    '    return Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,"0")).join("");',
    '  }',
  ];

  for (const target of targets) {
    const parts = target.split('.');
    if (parts.length < 2) continue;
    const obj = parts.slice(0, -1).join('.');
    const method = parts[parts.length - 1];
    lines.push(
      `  try {`,
      `    if (typeof ${obj} !== 'undefined' && typeof ${obj}.${method} === 'function') {`,
      `      ${obj}.${method} = __hook(${JSON.stringify(target)}, ${obj}.${method}.bind(${obj}));`,
      `    }`,
      `  } catch(_) {}`,
    );
  }

  lines.push('})();');
  return lines.join('\n');
}
