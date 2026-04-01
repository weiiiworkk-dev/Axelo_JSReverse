/**
 * 去混淆工具封装
 * 支持: webcrack (webpack), deobfuscator/synchrony (obfuscator.io), 以及简单的 babel 变换
 */

/**
 * 计算代码可读性分数 (0-1)
 * 启发式：基于标识符熵、字符串字面量比例、平均行长度
 */
function readabilityScore(code) {
  const lines = code.split('\n');
  const avgLineLen = lines.reduce((s, l) => s + l.length, 0) / (lines.length || 1);

  // 标识符长度分布
  const identMatches = code.match(/\b[a-zA-Z_$][a-zA-Z0-9_$]*\b/g) || [];
  const avgIdentLen = identMatches.length
    ? identMatches.reduce((s, id) => s + id.length, 0) / identMatches.length
    : 0;

  // 字符串混淆通常行很长
  const lineLenScore = Math.min(1, 80 / (avgLineLen || 80));
  // 标识符越长（有意义的名字）越可读
  const identScore = Math.min(1, avgIdentLen / 8);

  return (lineLenScore * 0.4 + identScore * 0.6);
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
 * Babel 手动变换：处理常见混淆模式
 * - 常量折叠（字符串数组查找替换）
 * - 十六进制字面量转十进制
 * - 简化 void 0 → undefined
 */
async function babelManualTransform(source) {
  const parser = await import('@babel/parser');
  const traverse = (await import('@babel/traverse')).default;
  const generate = (await import('@babel/generator')).default;
  const t = await import('@babel/types');

  const ast = parser.parse(source, {
    sourceType: 'unambiguous',
    plugins: ['jsx'],
    errorRecovery: true,
  });

  traverse(ast, {
    // void 0 → undefined
    UnaryExpression(path) {
      if (path.node.operator === 'void' && t.isNumericLiteral(path.node.argument, { value: 0 })) {
        path.replaceWith(t.identifier('undefined'));
      }
    },
    // 十六进制数字字面量转十进制
    NumericLiteral(path) {
      if (path.node.extra?.raw?.startsWith('0x')) {
        path.node.extra = { raw: String(path.node.value), rawValue: path.node.value };
      }
    },
    // !0 → true, !1 → false
    UnaryExpression2: {
      enter(path) {
        if (path.node.operator !== '!') return;
        if (t.isNumericLiteral(path.node.argument, { value: 0 })) {
          path.replaceWith(t.booleanLiteral(true));
        } else if (t.isNumericLiteral(path.node.argument, { value: 1 })) {
          path.replaceWith(t.booleanLiteral(false));
        }
      },
    },
  });

  return generate(ast, { retainLines: false, compact: false }).code;
}
