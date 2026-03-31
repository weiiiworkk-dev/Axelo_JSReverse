/**
 * Babel AST 提取与变换工具
 */

/**
 * 将 JS 源码解析为 AST JSON，同时提取关键元数据
 */
export async function extractAst({ source }) {
  const parser = await import('@babel/parser');
  const traverse = (await import('@babel/traverse')).default;
  const t = await import('@babel/types');

  let ast;
  try {
    ast = parser.parse(source, {
      sourceType: 'unambiguous',
      plugins: ['jsx', 'typescript'],
      errorRecovery: true,
    });
  } catch (err) {
    return { success: false, error: err.message };
  }

  // 提取函数列表
  const functions = [];
  // 提取加密API使用
  const cryptoUsages = [];
  // 提取字符串常量
  const stringLiterals = new Set();
  // 提取环境访问
  const envAccess = new Set();

  const cryptoPatterns = [
    /crypto/i, /CryptoJS/i, /md5/i, /sha/i, /hmac/i, /aes/i, /des/i,
    /base64/i, /btoa/i, /atob/i, /subtle/i, /forge/i,
  ];

  const envPatterns = [
    /navigator\.\w+/, /window\.\w+/, /document\.\w+/,
    /location\.\w+/, /screen\.\w+/,
  ];

  traverse(ast, {
    'FunctionDeclaration|FunctionExpression|ArrowFunctionExpression'(path) {
      const node = path.node;
      const name =
        (t.isFunctionDeclaration(node) && node.id?.name) ||
        (path.parent.type === 'VariableDeclarator' && path.parent.id?.name) ||
        (path.parent.type === 'AssignmentExpression' && memberExprToString(path.parent.left)) ||
        null;

      const params = (node.params || []).map(p => {
        if (t.isIdentifier(p)) return p.name;
        if (t.isRestElement(p) && t.isIdentifier(p.argument)) return `...${p.argument.name}`;
        return '?';
      });

      functions.push({
        name,
        line: node.loc?.start?.line ?? 0,
        col: node.loc?.start?.column ?? 0,
        params,
        isAsync: node.async ?? false,
      });
    },

    MemberExpression(path) {
      const str = memberExprToString(path.node);
      if (!str) return;

      for (const pat of cryptoPatterns) {
        if (pat.test(str)) {
          cryptoUsages.push(str);
          break;
        }
      }
      for (const pat of envPatterns) {
        if (pat.test(str)) {
          envAccess.add(str);
          break;
        }
      }
    },

    StringLiteral(path) {
      const val = path.node.value;
      if (val.length > 4 && val.length < 200) {
        stringLiterals.add(val);
      }
    },
  });

  return {
    success: true,
    functions,
    cryptoUsages: [...new Set(cryptoUsages)],
    stringLiterals: [...stringLiterals].slice(0, 200),
    envAccess: [...envAccess],
    // AST 本身太大，不直接返回，只返回元数据
    // 如果需要完整 AST 则通过文件路径操作
  };
}

/**
 * 应用一组命名变换到源码
 */
export async function applyTransforms({ source, transforms }) {
  // 目前 babel-manual 变换在 deobfuscate.mjs 中实现
  // 这里预留接口，后续可扩展为独立的 transform 插件
  return { success: true, code: source, applied: [] };
}

function memberExprToString(node) {
  if (!node) return null;
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'MemberExpression') {
    const obj = memberExprToString(node.object);
    const prop = node.computed
      ? null
      : node.property?.name ?? null;
    if (obj && prop) return `${obj}.${prop}`;
  }
  return null;
}
