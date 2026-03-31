/**
 * Axelo JSReverse Node.js Worker
 *
 * 通过 stdin/stdout 的换行分隔 JSON-RPC 与 Python 通信。
 * 协议：
 *   请求: {"id": "...", "method": "...", "params": {...}}\n
 *   响应: {"id": "...", "result": {...}}\n
 *         {"id": "...", "error": "..."}\n
 */

import { createInterface } from 'readline';
import { deobfuscate } from './deobfuscate.mjs';
import { extractAst, applyTransforms } from './ast_tools.mjs';
import { executeSandboxed } from './execute_hook.mjs';

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });

const METHODS = {
  deobfuscate,
  extractAst,
  applyTransforms,
  executeSandboxed,
  ping: async () => ({ pong: true }),
};

rl.on('line', async (line) => {
  line = line.trim();
  if (!line) return;

  let req;
  try {
    req = JSON.parse(line);
  } catch {
    respond({ id: null, error: 'Invalid JSON' });
    return;
  }

  const { id, method, params = {} } = req;

  if (!METHODS[method]) {
    respond({ id, error: `Unknown method: ${method}` });
    return;
  }

  try {
    const result = await METHODS[method](params);
    respond({ id, result });
  } catch (err) {
    respond({ id, error: err.message || String(err) });
  }
});

function respond(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

// 通知 Python 端已就绪
respond({ id: '__init__', result: { ready: true } });
