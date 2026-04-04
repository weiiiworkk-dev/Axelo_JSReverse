from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from axelo.models.execution import VerificationMode
from axelo.presentation import verification_status_markup, verification_was_skipped
from axelo.wizard import _failure_insight, _target_hint_required


def test_target_hint_required_for_generic_product_page():
    assert _target_hint_required("https://www.lazada.com.my/#?", "逆向电商接口签名，生成商品详情或价格爬虫") is True
    assert _target_hint_required("https://www.lazada.com.my/catalog/?q=iphone", "逆向电商接口签名，生成商品详情或价格爬虫") is False


def test_failure_insight_explains_dns_host_guess_issue(tmp_path: Path):
    session_dir = tmp_path / "session"
    output_dir = session_dir / "output"
    output_dir.mkdir(parents=True)

    (session_dir / "workflow_trace.json").write_text(
        json.dumps(
            {
                "checkpoints": [
                    {
                        "stage_name": "s8_verify",
                        "status": "failed",
                        "summary": "crawl() execution failed: [Errno 11001] getaddrinfo failed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "run_report.json").write_text(
        json.dumps({"result": {"verification_notes": "crawl() execution failed: [Errno 11001] getaddrinfo failed"}}),
        encoding="utf-8",
    )
    (output_dir / "verify_report.txt").write_text(
        "crawl() execution failed: [Errno 11001] getaddrinfo failed",
        encoding="utf-8",
    )

    result = SimpleNamespace(completed=True, verified=False, error=None)
    insight = _failure_insight(result, session_dir)

    assert insight["stage"] == "s8_verify"
    assert "API 主机不可解析" in insight["cause"]


def test_failure_insight_marks_compliance_skip_as_skipped(tmp_path: Path):
    session_dir = tmp_path / "session"
    output_dir = session_dir / "output"
    output_dir.mkdir(parents=True)

    (session_dir / "workflow_trace.json").write_text(
        json.dumps(
            {
                "checkpoints": [
                    {
                        "stage_name": "s7_codegen",
                        "status": "skipped",
                        "summary": "Code generation disabled by compliance-aware execution plan",
                    },
                    {
                        "stage_name": "s8_verify",
                        "status": "skipped",
                        "summary": "Verification disabled by compliance-aware execution plan",
                    },
                    {
                        "stage_name": "memory_write",
                        "status": "completed",
                        "summary": "Memory updated",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "run_report.json").write_text(json.dumps({"result": {}}), encoding="utf-8")

    result = SimpleNamespace(
        completed=True,
        verified=False,
        error=None,
        execution_plan=SimpleNamespace(verification_mode=VerificationMode.NONE, skip_codegen=True),
    )

    insight = _failure_insight(result, session_dir)

    assert insight["title"] == "验证已跳过摘要"
    assert insight["stage"] == "s8_verify"
    assert "不是验证失败" in insight["cause"]


def test_verification_status_markup_reports_skipped():
    result = SimpleNamespace(
        verified=False,
        execution_plan=SimpleNamespace(verification_mode=VerificationMode.NONE, skip_codegen=True),
    )

    assert verification_was_skipped(result) is True
    assert verification_status_markup(result) == "[cyan]已跳过[/cyan]"
