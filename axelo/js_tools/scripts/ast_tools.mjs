import {
  loadBabelParser,
  loadBabelTraverse,
  loadBabelTypes,
} from './babel_compat.mjs';

/**
 * 将 JS 源码解析为 AST 元数据，并提取静态分析所需的关键信号。
 */
export async function extractAst({ source }) {
  const parser = await loadBabelParser();
  const traverse = await loadBabelTraverse();
  const t = await loadBabelTypes();

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

  const functions = [];
  const cryptoUsages = [];
  const stringLiterals = new Set();
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

      const params = (node.params || []).map((param) => {
        if (t.isIdentifier(param)) return param.name;
        if (t.isRestElement(param) && t.isIdentifier(param.argument)) {
          return `...${param.argument.name}`;
        }
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
      const value = memberExprToString(path.node);
      if (!value) return;

      for (const pattern of cryptoPatterns) {
        if (pattern.test(value)) {
          cryptoUsages.push(value);
          break;
        }
      }
      for (const pattern of envPatterns) {
        if (pattern.test(value)) {
          envAccess.add(value);
          break;
        }
      }
    },

    StringLiteral(path) {
      const value = path.node.value;
      if (value.length > 4 && value.length < 200) {
        stringLiterals.add(value);
      }
    },
  });

  return {
    success: true,
    functions,
    cryptoUsages: [...new Set(cryptoUsages)],
    stringLiterals: [...stringLiterals].slice(0, 200),
    envAccess: [...envAccess],
  };
}

/**
 * 预留的变换入口，后续可以扩展为更细粒度的 Babel transform。
 */
export async function applyTransforms({ source, transforms }) {
  void transforms;
  return { success: true, code: source, applied: [] };
}

function memberExprToString(node) {
  if (!node) return null;
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'MemberExpression') {
    const objectName = memberExprToString(node.object);
    const propertyName = node.computed ? null : node.property?.name ?? null;
    if (objectName && propertyName) return `${objectName}.${propertyName}`;
  }
  return null;
}
