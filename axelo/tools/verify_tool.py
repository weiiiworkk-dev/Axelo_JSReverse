"""
Verification tool.

Consumes a canonical crawler source when available, executes the generated
code under the current Python interpreter, and reports whether the crawler is
grounded enough to trust.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from axelo.config import settings
from axelo.models.signature import SignatureSpec
from axelo.tools.base import (
    BaseTool,
    ToolCategory,
    ToolInput,
    ToolOutput,
    ToolResult,
    ToolSchema,
    ToolState,
    ToolStatus,
    get_registry,
)

log = structlog.get_logger(__name__)


@dataclass
class VerifyOutput:
    success: bool = False
    score: float = 0.0
    execution_verdict: str = "fail"
    structural_verdict: str = ""
    semantic_verdict: str = ""
    mechanism_verdict: str = "unknown"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mechanism_blockers: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    execution_result: dict[str, Any] = field(default_factory=dict)


class VerifyTool(BaseTool):
    @property
    def name(self) -> str:
        return "verify"

    @property
    def description(self) -> str:
        return "Verify generated crawler code against a canonical execution contract."

    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.VERIFY,
            input_schema=[
                ToolInput(name="code", type="string", description="Code to verify", required=False),
                ToolInput(name="target_url", type="string", description="Target URL", required=True),
                ToolInput(name="test_params", type="object", description="Test parameters", required=False, default={}),
                ToolInput(name="run_actual_test", type="boolean", description="Execute generated code", required=False, default=True),
                ToolInput(name="crawler_source", type="object", description="Canonical crawler source", required=False),
                ToolInput(name="signature_spec", type="object", description="Canonical signature specification", required=False),
            ],
            output_schema=[
                ToolOutput(name="success", type="boolean", description="Verification success"),
                ToolOutput(name="score", type="number", description="Verification score"),
                ToolOutput(name="execution_verdict", type="string", description="Execution verdict"),
                ToolOutput(name="mechanism_verdict", type="string", description="Mechanism verdict"),
                ToolOutput(name="errors", type="array", description="Errors"),
                ToolOutput(name="warnings", type="array", description="Warnings"),
                ToolOutput(name="mechanism_blockers", type="array", description="Mechanism blockers"),
                ToolOutput(name="details", type="object", description="Verification details"),
                ToolOutput(name="execution_result", type="object", description="Execution result"),
            ],
            timeout_seconds=120,
            retry_enabled=True,
            max_retries=2,
        )

    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        code, code_source = self._resolve_code_input(input_data)
        target_url = input_data.get("target_url") or input_data.get("page_url") or input_data.get("url")
        run_actual_test = input_data.get("run_actual_test", True)
        signature_spec = self._coerce_signature_spec(
            input_data.get("signature_spec_model") or input_data.get("signature_spec")
        )

        if not code:
            return ToolResult(tool_name=self.name, status=ToolStatus.FAILED, error="Missing required input: code")
        if not target_url:
            return ToolResult(tool_name=self.name, status=ToolStatus.FAILED, error="Missing required input: target_url")

        try:
            errors, warnings = self._syntax_check(code)
            should_validate_signature = self._requires_signature_validation(code, signature_spec)

            missing_deps = self._check_dependencies(code)
            if missing_deps:
                warnings.append(f"Possible missing dependencies: {', '.join(missing_deps)}")

            acceptable_urls = [target_url]
            if signature_spec and signature_spec.transport_profile:
                acceptable_urls.extend(
                    [
                        signature_spec.transport_profile.get("url", ""),
                        signature_spec.transport_profile.get("url_pattern", ""),
                    ]
                )

            if not self._code_mentions_any_target(code, acceptable_urls):
                warnings.append("Generated code URL does not match the target URL.")

            warnings.extend(self._check_signature_alignment(code, signature_spec))

            execution_result: dict[str, Any] = {}
            if not errors and run_actual_test and "async def" in code:
                execution_result = await self._run_actual_test(code, target_url)
                if not should_validate_signature:
                    execution_result["signature_tested"] = False
                    execution_result["signature_works"] = True
                if execution_result.get("execution_failed"):
                    errors.append(f"Execution failed: {execution_result.get('error', 'unknown error')}")
                elif execution_result.get("is_blocked"):
                    block_reason = execution_result.get("block_reason", "unknown")
                    errors.append(f"Blocked by anti-bot controls: {block_reason}")
                    warnings.append("Recommendation: verify UA, cookies, signature inputs, and browser context.")
                elif execution_result.get("no_data"):
                    warnings.append("The response contained no data; request parameters may need adjustment.")

                if should_validate_signature and execution_result.get("signature_tested") and not execution_result.get("signature_works"):
                    warnings.append(f"Signature check failed: {execution_result.get('signature_error', 'unknown')}")

            base_score = 100
            has_placeholder_secret = any(
                "placeholder secret" in warning.lower() or "placeholder key" in warning.lower()
                for warning in warnings
            )
            signature_failed = should_validate_signature and bool(
                execution_result
                and execution_result.get("signature_tested")
                and not execution_result.get("signature_works")
            )
            if execution_result:
                if execution_result.get("is_blocked"):
                    base_score -= 30
                if execution_result.get("no_data"):
                    base_score -= 15
                if signature_failed:
                    base_score -= 25
            if has_placeholder_secret:
                base_score -= 20

            output_score = max(0, base_score - (len(errors) * 20) - (len(warnings) * 5)) / 100.0
            success = len(errors) == 0 and output_score >= 0.7 and not has_placeholder_secret and not signature_failed
            execution_verdict = "pass" if success else "fail"
            strategy_used = ""
            if isinstance(execution_result, dict):
                strategy_used = str(
                    execution_result.get("strategy_used")
                    or input_data.get("crawler_source", {}).get("strategy_used")
                    or (signature_spec.codegen_strategy if signature_spec else "")
                ).strip()
            mechanism_verdict, mechanism_blockers, mechanism_summary = self._assess_mechanism_verdict(
                success=success,
                signature_spec=signature_spec,
                warnings=warnings,
                execution_result=execution_result,
                strategy_used=strategy_used,
            )

            # Derive three-layer structural and semantic verdicts for coverage scoring.
            # constitution.py uses structural_verdict and semantic_verdict to compute
            # verify coverage; without them the score is capped at 0.425 (exec-only).
            actually_ran = bool(execution_result and "returncode" in execution_result)
            is_blocked_exec = bool(execution_result.get("is_blocked")) if execution_result else False
            no_data_exec = bool(execution_result.get("no_data")) if execution_result else False

            if execution_verdict == "pass":
                if actually_ran and not is_blocked_exec and not no_data_exec:
                    # Code ran, returned data, not blocked → full structural pass
                    structural_verdict = "pass"
                    semantic_verdict = "validated" if len(warnings) <= 2 and not has_placeholder_secret else "suspicious"
                elif actually_ran and not is_blocked_exec:
                    # Code ran but returned no data
                    structural_verdict = "partial"
                    semantic_verdict = "suspicious"
                elif actually_ran:
                    # Code ran but was blocked
                    structural_verdict = "partial"
                    semantic_verdict = ""
                else:
                    # Syntax-only check (no actual execution) — conservative
                    structural_verdict = "partial"
                    semantic_verdict = "suspicious"
            else:
                structural_verdict = ""
                semantic_verdict = ""

            details = {
                "syntax_errors": len(errors),
                "warnings_count": len(warnings),
                "code_length": len(code),
                "execution_enabled": run_actual_test,
                "code_source": code_source,
                "signature_algorithm": signature_spec.algorithm_id if signature_spec else "",
                "strategy_used": strategy_used,
                "execution_verdict": execution_verdict,
                "structural_verdict": structural_verdict,
                "semantic_verdict": semantic_verdict,
                "mechanism_verdict": mechanism_verdict,
                "mechanism_summary": mechanism_summary,
            }

            output = VerifyOutput(
                success=success,
                score=output_score,
                execution_verdict=execution_verdict,
                structural_verdict=structural_verdict,
                semantic_verdict=semantic_verdict,
                mechanism_verdict=mechanism_verdict,
                errors=errors,
                warnings=warnings,
                mechanism_blockers=mechanism_blockers,
                details=details,
                execution_result=execution_result,
            )

            session_id = getattr(state, "session_id", None)
            if session_id:
                session_dir = settings.session_dir(session_id)
                session_dir.mkdir(parents=True, exist_ok=True)
                report = {
                    "success": output.success,
                    "score": output.score,
                    "execution_verdict": output.execution_verdict,
                    "structural_verdict": output.structural_verdict,
                    "semantic_verdict": output.semantic_verdict,
                    "mechanism_verdict": output.mechanism_verdict,
                    "errors": output.errors,
                    "warnings": output.warnings,
                    "mechanism_blockers": output.mechanism_blockers,
                    "details": output.details,
                    "execution_result": output.execution_result,
                    "verified_at": datetime.now().isoformat(),
                }
                (session_dir / "verify_report.json").write_text(
                    json.dumps(report, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                log.info("verify_report_saved", session=session_id, file="verify_report.json")

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS if output.success else ToolStatus.FAILED,
                output={
                    "success": output.success,
                    "score": output.score,
                    "execution_verdict": output.execution_verdict,
                    "structural_verdict": output.structural_verdict,
                    "semantic_verdict": output.semantic_verdict,
                    "mechanism_verdict": output.mechanism_verdict,
                    "errors": output.errors,
                    "warnings": output.warnings,
                    "mechanism_blockers": output.mechanism_blockers,
                    "details": output.details,
                    "execution_result": output.execution_result,
                },
            )
        except Exception as exc:
            log.error("verify_tool_failed", error=str(exc))
            return ToolResult(tool_name=self.name, status=ToolStatus.FAILED, error=str(exc))

    @staticmethod
    def _coerce_signature_spec(candidate: Any) -> SignatureSpec | None:
        if isinstance(candidate, SignatureSpec):
            return candidate
        if isinstance(candidate, dict) and candidate:
            try:
                return SignatureSpec.model_validate(candidate)
            except Exception:
                return None
        return None

    def _resolve_code_input(self, input_data: dict[str, Any]) -> tuple[str, str]:
        crawler_source = input_data.get("crawler_source") or {}
        if isinstance(crawler_source, dict):
            python_code = str(crawler_source.get("python_code") or "")
            js_code = str(crawler_source.get("js_code") or "")
            path = crawler_source.get("path") or crawler_source.get("crawler_path")
            if not python_code and path:
                try:
                    python_code = Path(path).read_text(encoding="utf-8")
                except Exception:
                    python_code = ""
            if python_code.strip():
                return python_code, str(crawler_source.get("source") or "crawler_source.python")
            if js_code.strip():
                return js_code, str(crawler_source.get("source") or "crawler_source.js")

        code = str(input_data.get("code") or "")
        if code.strip():
            return code, "ambient_code"
        python_code = str(input_data.get("python_code") or "")
        if python_code.strip():
            return python_code, "python_code"
        js_code = str(input_data.get("js_code") or "")
        if js_code.strip():
            return js_code, "js_code"
        return "", "missing"

    def _check_signature_alignment(self, code: str, signature_spec: SignatureSpec | None) -> list[str]:
        if signature_spec is None:
            return []
        warnings: list[str] = []
        output_fields = list((signature_spec.signing_outputs or signature_spec.output_fields).keys())
        if output_fields and not any(field in code for field in output_fields):
            warnings.append("Generated code does not reference the SignatureSpec signing output fields.")
        required_headers = signature_spec.header_policy.get("required", []) if signature_spec.header_policy else []
        missing_headers = [header for header in required_headers if header not in code]
        if missing_headers:
            warnings.append(
                f"Generated code does not cover SignatureSpec required headers: {', '.join(missing_headers[:5])}"
            )
        return warnings

    @staticmethod
    def _code_mentions_any_target(code: str, targets: list[str]) -> bool:
        for target in targets:
            normalized = str(target or "").strip()
            if not normalized:
                continue
            compact = normalized.replace("https://", "").replace("http://", "")
            if normalized in code or compact in code:
                return True
        return False

    @staticmethod
    def _requires_signature_validation(code: str, signature_spec: SignatureSpec | None) -> bool:
        if signature_spec and signature_spec.codegen_strategy == "observed_replay":
            return False
        lowered = code.lower()
        return any(marker in lowered for marker in ("generate_signature", "secret_key", "crypto.", "hashlib.", "hmac.new"))

    @staticmethod
    def _assess_mechanism_verdict(
        *,
        success: bool,
        signature_spec: SignatureSpec | None,
        warnings: list[str],
        execution_result: dict[str, Any],
        strategy_used: str,
    ) -> tuple[str, list[str], str]:
        blockers: list[str] = []
        if not success:
            return "unknown", ["Execution did not pass, so mechanism claims remain unsupported."], "Execution failed."

        algorithm_id = str(signature_spec.algorithm_id if signature_spec else "").strip().lower()
        required_headers = list(
            signature_spec.header_policy.get("required", []) if signature_spec and signature_spec.header_policy else []
        )
        codegen_strategy = str(signature_spec.codegen_strategy if signature_spec else strategy_used or "").strip().lower()
        replay_strategies = {"observed_replay", "live_replay", "snapshot_replay"}

        if codegen_strategy in replay_strategies:
            blockers.append("Execution succeeded via replay-oriented strategy; causal mechanism remains unproven.")
        if not signature_spec:
            blockers.append("Canonical signature specification is missing.")
        elif not algorithm_id or algorithm_id == "unknown":
            blockers.append("Canonical signature specification does not identify a mechanism.")
        if not required_headers:
            blockers.append("Canonical required headers are unresolved.")
        if any("required headers" in str(warning).lower() or "signaturespec" in str(warning).lower() for warning in warnings):
            blockers.append("Generated code does not fully cover canonical signature requirements.")
        if execution_result and execution_result.get("signature_tested") and not execution_result.get("signature_works"):
            blockers.append("Signature-specific execution check did not succeed.")

        if blockers:
            verdict = "replay_only" if codegen_strategy in replay_strategies else "partial"
            return verdict, blockers, "Execution passed, but the mechanism is not yet validated."

        return "validated", [], "Execution and mechanism evidence are aligned."

    async def _run_actual_test(self, code: str, target_url: str) -> dict[str, Any]:
        log.info("verify_running_actual_test", url=target_url)
        test_code = code.strip()
        timeout_seconds = 60.0 if "async_playwright" in test_code else 30.0
        if 'if __name__' not in test_code:
            test_code += f'''

async def quick_test():
    try:
        result = await make_request("{target_url}", {{"page": 1}})
        print(f"RESULT: {{result}}")
        return result
    except Exception as exc:
        print(f"ERROR: {{exc}}")
        return {{"error": str(exc)}}

if __name__ == "__main__":
    import asyncio
    asyncio.run(quick_test())
'''

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as handle:
                handle.write(test_code)
                temp_path = handle.name

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            stdout_text = stdout.decode("utf-8", errors="ignore")
            stderr_text = stderr.decode("utf-8", errors="ignore")
            return self._analyze_execution_output(stdout_text, stderr_text, process.returncode)
        except asyncio.TimeoutError:
            return {"execution_failed": True, "error": f"Execution timed out ({int(timeout_seconds)}s)", "is_blocked": False}
        except Exception as exc:
            return {"execution_failed": True, "error": str(exc), "is_blocked": False}
        finally:
            if temp_path:
                try:
                    # Ensure the subprocess has fully released the file before deletion.
                    # 'process' may be unbound if subprocess creation itself failed.
                    if "process" in dir():
                        try:
                            await asyncio.wait_for(process.wait(), timeout=2.0)
                        except Exception:
                            pass
                    Path(temp_path).unlink(missing_ok=True)
                except Exception as exc:
                    import structlog as _sl
                    _sl.get_logger().warning("verify_temp_cleanup_failed", path=temp_path, error=str(exc))

    def _analyze_execution_output(self, stdout: str, stderr: str, returncode: int) -> dict[str, Any]:
        result = {
            "returncode": returncode,
            "signature_tested": True,
            "signature_works": False,
            "is_blocked": False,
            "no_data": False,
        }
        if returncode != 0:
            error_msg = stderr[:500] if stderr else (stdout[:500] if stdout else "unknown error")
            if "NameError" in stdout or "NameError" in stderr:
                error_msg = f"Code error: unresolved variable or function name - {error_msg[:200]}"
            elif "SyntaxError" in stdout or "SyntaxError" in stderr:
                error_msg = f"Syntax error: {error_msg[:200]}"
            elif "ConnectionError" in stdout or "ConnectionError" in stderr:
                error_msg = f"Connection error: unable to reach the target URL - {error_msg[:200]}"
            elif "TimeoutError" in stdout or "TimeoutError" in stderr:
                error_msg = f"Request timeout: {error_msg[:200]}"
            result["execution_failed"] = True
            result["error"] = error_msg
            return result

        output = stdout + stderr
        blocked_patterns = [
            "captcha",
            "blocked",
            "too many requests",
            "anti-bot",
            "cloudflare",
            "turnstile",
            "recaptcha",
            "hcaptcha",
            "access denied",
            "forbidden",
        ]
        for pattern in blocked_patterns:
            if pattern in output.lower():
                result["is_blocked"] = True
                result["block_reason"] = f"Detected anti-bot marker: {pattern}"
                break
        if not result["is_blocked"]:
            status_matches = re.findall(r'["\']status["\']\s*:\s*(\d{3})', output)
            if any(code in {"403", "429"} for code in status_matches):
                blocked_code = next(code for code in status_matches if code in {"403", "429"})
                result["is_blocked"] = True
                result["block_reason"] = f"Detected blocked status code {blocked_code}"

        has_data = any(token in output.lower() for token in ("result", "data", "json", "status", "products", "items"))
        if not has_data:
            result["no_data"] = True
        if "signature" in output.lower() and "error" not in output.lower():
            result["signature_works"] = True
        return result

    def _syntax_check(self, code: str) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        if "import asyncio" in code or "async def" in code:
            try:
                compile(code, "<string>", "exec")
            except SyntaxError as exc:
                errors.append(f"Syntax error: {exc.msg} at line {exc.lineno}")
        if "TODO" in code:
            warnings.append("Code contains TODO markers and may be incomplete.")
        placeholder_markers = [
            "YOUR_SECRET_KEY",
            "YOUR_32BYTE_KEY_HERE",
            "YOUR_PRIVATE_KEY_HERE",
            "REPLACE WITH ACTUAL KEY",
        ]
        if any(marker in code for marker in placeholder_markers):
            warnings.append("Code contains placeholder keys and must be replaced.")
        return errors, warnings

    @staticmethod
    def _check_dependencies(code: str) -> list[str]:
        needed: list[str] = []
        if "httpx" in code and "import httpx" not in code:
            needed.append("httpx")
        if "playwright" in code and "from playwright" not in code:
            needed.append("playwright")
        if "Crypto." in code and "pycryptodome" not in code:
            needed.append("pycryptodome")
        return needed


get_registry().register(VerifyTool())
