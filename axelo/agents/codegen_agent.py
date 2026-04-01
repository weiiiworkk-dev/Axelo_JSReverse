from __future__ import annotations
import json
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from axelo.agents.base import BaseAgent
from axelo.ai.hypothesis import CodeGenOutput
from axelo.models.analysis import StaticAnalysis, DynamicAnalysis, AIHypothesis
from axelo.models.target import TargetSite
from axelo.memory.retriever import MemoryRetriever
import structlog

log = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent.parent / "ai" / "prompts"

CODEGEN_SYSTEM = """你是一位爬虫工程师兼代码生成专家（CodeGen Agent）。

你的任务是将 JS 逆向分析结果转化为**完整可运行的 Python 爬虫文件**。

## 输出结构要求
1. `_sign(url, method, body) -> dict[str, str]`：私有方法，实现签名/Token 生成逻辑
2. `crawl(**kwargs) -> dict`：公开方法，内部调用 `_sign()` → 发送 httpx 请求 → 返回解析后的 JSON 数据
3. `if __name__ == "__main__"` 块：包含一个实际可运行的调用示例
4. 脚本可直接 `python crawler.py` 运行并输出结果

## 其他要求
- 所有 import 在文件顶部声明
- 每个关键签名步骤注释标注对应的 JS 逻辑
- 如果有动态 Hook 数据，用实际参数值验证签名实现
- 必须使用 httpx 发送真实 HTTP 请求

## 参考模板
{template_code}
"""


class CodeGenAgent(BaseAgent):
    """
    代码生成角色：将算法假设 → 可运行 Python 代码。
    也会参考记忆库中的模板，避免重复造轮子。
    """
    role = "codegen"
    default_model = "claude-opus-4-6"

    def __init__(self, *args, retriever: MemoryRetriever, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._retriever = retriever
        self._jinja = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

    async def generate(
        self,
        target: TargetSite,
        hypothesis: AIHypothesis,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None,
        output_dir: Path,
    ) -> dict[str, Path]:
        # 查找最相关的模板
        algo_type = _infer_algo_type(hypothesis)
        templates = self._retriever.get_all_templates()
        template_code = ""
        for t in templates:
            if t.algorithm_type == algo_type and t.python_code:
                template_code = f"# 参考模板 '{t.name}':\n{t.python_code}"
                break

        system_prompt = CODEGEN_SYSTEM.format(template_code=template_code or "（无相似模板）")

        # 构建 prompt 上下文
        source_snippets = _collect_snippets(hypothesis, static_results)
        hook_data = _collect_hook_data(dynamic)

        if hypothesis.codegen_strategy == "python_reconstruct":
            template = self._jinja.get_template("generate_python.j2")
            user_msg = template.render(
                hypothesis=hypothesis,
                source_snippets=source_snippets,
                hook_data=hook_data,
            )
        else:
            first_bundle = next(
                (str(output_dir.parent / "bundles" / f"{bid}.raw.js")
                 for bid in static_results), ""
            )
            template = self._jinja.get_template("generate_bridge.j2")
            user_msg = template.render(
                hypothesis=hypothesis,
                bundle_path=first_bundle,
                bridge_port=8721,
            )

        client = self._build_client()
        output: CodeGenOutput = await client.analyze(
            system_prompt=system_prompt,
            user_message=user_msg,
            output_schema=CodeGenOutput,
            tool_name="codegen",
            max_tokens=8192,
        )

        self._cost.add_ai_call(
            model=self._select_model(),
            input_tok=len(user_msg) // 4,
            output_tok=800,
            stage="codegen",
        )

        # 写文件
        artifacts: dict[str, Path] = {}
        output_dir.mkdir(parents=True, exist_ok=True)

        if output.crawler_code:
            p = output_dir / "crawler.py"
            p.write_text(output.crawler_code, encoding="utf-8")
            artifacts["crawler_script"] = p
        if output.bridge_server_code:
            p = output_dir / "bridge_server.js"
            p.write_text(output.bridge_server_code, encoding="utf-8")
            artifacts["bridge_server"] = p
        if output.dependencies:
            p = output_dir / "requirements.txt"
            p.write_text("\n".join(output.dependencies), encoding="utf-8")
            artifacts["requirements"] = p

        log.info("codegen_done", files=list(artifacts.keys()))
        return artifacts


def _infer_algo_type(h: AIHypothesis) -> str:
    desc = h.algorithm_description.lower()
    for kw, t in [("hmac", "hmac"), ("rsa", "rsa"), ("aes", "aes"),
                  ("md5", "md5"), ("canvas", "fingerprint"), ("fingerprint", "fingerprint")]:
        if kw in desc:
            return t
    return "custom"


def _collect_snippets(hypothesis: AIHypothesis, static_results: dict) -> str:
    snippets = []
    for sa in static_results.values():
        for c in sa.token_candidates:
            if c.func_id in hypothesis.generator_func_ids and c.source_snippet:
                snippets.append(f"// {c.func_id}\n{c.source_snippet[:600]}")
    return "\n\n".join(snippets[:4]) or "（未找到源码片段）"


def _collect_hook_data(dynamic: DynamicAnalysis | None) -> str:
    if not dynamic or not dynamic.hook_intercepts:
        return "（无动态数据）"
    return json.dumps(
        [ic.model_dump(mode="json") for ic in dynamic.hook_intercepts[:5]],
        ensure_ascii=False, indent=2,
    )
