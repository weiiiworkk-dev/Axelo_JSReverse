export async function loadBabelParser() {
  const mod = await import('@babel/parser');
  return mod.default?.parse ? mod.default : mod;
}

export async function loadBabelTraverse() {
  const mod = await import('@babel/traverse');
  return mod.default?.default ?? mod.default ?? mod;
}

export async function loadBabelGenerator() {
  const mod = await import('@babel/generator');
  return mod.default?.default ?? mod.default ?? mod.generate;
}

export async function loadBabelTypes() {
  const mod = await import('@babel/types');
  return mod.default ?? mod;
}
