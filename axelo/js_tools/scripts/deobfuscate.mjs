import {
  loadBabelGenerator,
  loadBabelParser,
  loadBabelTraverse,
  loadBabelTypes,
} from './babel_compat.mjs';

/**
 * 计算代码可读性分数 (0-1)
 */
function readabilityScore(code) {
  const lines = code.split('\n');
  const avgLineLen = lines.reduce((sum, line) => sum + line.length, 0) / (lines.length || 1);
  const identMatches = code.match(/\b[a-zA-Z_$][a-zA-Z0-9_$]*\b/g) || [];
  const avgIdentLen = identMatches.length
    ? identMatches.reduce((sum, ident) => sum + ident.length, 0) / identMatches.length
    : 0;

  const lineLenScore = Math.min(1, 80 / (avgLineLen || 80));
  const identScore = Math.min(1, avgIdentLen / 8);

  return lineLenScore * 0.4 + identScore * 0.6;
}

export async function deobfuscate({ source, tool }) {
  const originalScore = readabilityScore(source);

  if (tool === 'webcrack') {
    try {
      const { webcrack } = await import('webcrack');
      const result = await webcrack(source);
      const output = result.code;
      return {
        success: true,
        code: output,
        tool: 'webcrack',
        originalScore,
        outputScore: readabilityScore(output),
        modules: Object.keys(result.bundle?.modules || {}),
      };
    } catch (err) {
      return { success: false, tool: 'webcrack', error: err.message, originalScore, outputScore: 0 };
    }
  }

  if (tool === 'synchrony' || tool === 'deobfuscator') {
    try {
      const { deobfuscate: syncDeob } = await import('synchrony');
      const output = await syncDeob(source);
      return {
        success: true,
        code: output,
        tool: 'synchrony',
        originalScore,
        outputScore: readabilityScore(output),
        modules: [],
      };
    } catch (err) {
      return { success: false, tool: 'synchrony', error: err.message, originalScore, outputScore: 0 };
    }
  }

  if (tool === 'babel-manual') {
    try {
      const output = await babelManualTransform(source);
      return {
        success: true,
        code: output,
        tool: 'babel-manual',
        originalScore,
        outputScore: readabilityScore(output),
        modules: [],
      };
    } catch (err) {
      return { success: false, tool: 'babel-manual', error: err.message, originalScore, outputScore: 0 };
    }
  }

  return { success: false, tool, error: `Unknown tool: ${tool}`, originalScore, outputScore: 0 };
}

/**
 * Babel 手动变换：处理常见简单混淆。
 */
async function babelManualTransform(source) {
  const parser = await loadBabelParser();
  const traverse = await loadBabelTraverse();
  const generate = await loadBabelGenerator();
  const t = await loadBabelTypes();

  const ast = parser.parse(source, {
    sourceType: 'unambiguous',
    plugins: ['jsx'],
    errorRecovery: true,
  });

  traverse(ast, {
    UnaryExpression(path) {
      if (path.node.operator === 'void' && t.isNumericLiteral(path.node.argument, { value: 0 })) {
        path.replaceWith(t.identifier('undefined'));
        return;
      }
      if (path.node.operator !== '!') return;
      if (t.isNumericLiteral(path.node.argument, { value: 0 })) {
        path.replaceWith(t.booleanLiteral(true));
      } else if (t.isNumericLiteral(path.node.argument, { value: 1 })) {
        path.replaceWith(t.booleanLiteral(false));
      }
    },

    NumericLiteral(path) {
      if (path.node.extra?.raw?.startsWith('0x')) {
        path.node.extra = { raw: String(path.node.value), rawValue: path.node.value };
      }
    },
  });

  return generate(ast, { retainLines: false, compact: false }).code;
}
