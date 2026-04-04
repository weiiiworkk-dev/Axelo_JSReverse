#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

function tryRequire(names) {
  for (const name of names) {
    try {
      return { name, module: require(name) };
    } catch (_error) {
      continue;
    }
  }
  return null;
}

function readArg(flag) {
  const index = process.argv.indexOf(flag);
  if (index === -1 || index + 1 >= process.argv.length) {
    return '';
  }
  return process.argv[index + 1];
}

function addCheck(checks, name, ok, details) {
  checks.push({ name, ok, details });
}

async function main() {
  const checks = [];
  const storageStatePath = readArg('--storage-state');
  const nodeMajor = Number(process.versions.node.split('.')[0] || '0');
  addCheck(
    checks,
    'node_version',
    nodeMajor >= 18,
    {
      version: process.version,
      required: '>=18',
    },
  );

  const playwrightInfo = tryRequire(['playwright', 'playwright-core']);
  addCheck(
    checks,
    'playwright_package',
    Boolean(playwrightInfo),
    playwrightInfo
      ? { module: playwrightInfo.name }
      : { install: 'npm install playwright' },
  );

  if (storageStatePath) {
    const resolved = path.resolve(storageStatePath);
    if (!fs.existsSync(resolved)) {
      addCheck(checks, 'storage_state_file', false, { path: resolved, error: 'File not found' });
    } else {
      try {
        JSON.parse(fs.readFileSync(resolved, 'utf8'));
        addCheck(checks, 'storage_state_file', true, { path: resolved });
      } catch (error) {
        addCheck(checks, 'storage_state_file', false, { path: resolved, error: error.message });
      }
    }
  }

  if (playwrightInfo) {
    let browser = null;
    let context = null;
    try {
      browser = await playwrightInfo.module.chromium.launch({ headless: true });
      addCheck(checks, 'chromium_launch', true, {});

      context = await browser.newContext();
      const page = await context.newPage();
      await page.goto('data:text/html,<title>axelo-bridge-env</title><h1>ok</h1>', {
        waitUntil: 'domcontentloaded',
        timeout: 10000,
      });
      const title = await page.title();
      addCheck(checks, 'page_bootstrap', title === 'axelo-bridge-env', { title });
    } catch (error) {
      addCheck(checks, 'chromium_launch', false, { error: error.message });
    } finally {
      if (context) {
        await context.close().catch(() => {});
      }
      if (browser) {
        await browser.close().catch(() => {});
      }
    }
  }

  const ok = checks.every((check) => check.ok);
  const report = {
    ok,
    nodeVersion: process.version,
    checks,
    recommendations: [
      'Use playwright for the bridge runtime.',
      'Do not add stealth or anti-detection plugins to this environment check.',
      'Install browsers with: npx playwright install chromium',
    ],
  };

  console.log(JSON.stringify(report, null, 2));
  process.exit(ok ? 0 : 1);
}

main().catch((error) => {
  console.error(JSON.stringify({
    ok: false,
    fatal: error.message,
  }, null, 2));
  process.exit(1);
});
