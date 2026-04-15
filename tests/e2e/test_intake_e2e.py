"""
End-to-end intake pipeline tests for 8 e-commerce platforms.

Tests:
  Step 1: IntakeAIProcessor.process_message() — no exceptions, Chinese reply,
          contract fields populated, is_ready after 1-2 turns.
  Step 2: MissionContract → RequirementSheet bridge (to_requirement_sheet_kwargs,
          RequirementSheet(**kwargs), to_prompt()).
  Step 3: classify_outcome() verdict structures.
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

# Force UTF-8 output on Windows to avoid cp1252 encode errors with CJK chars
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── ensure project root is on sys.path ────────────────────────────────────────
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── imports ───────────────────────────────────────────────────────────────────
from axelo.engine.principal import IntakeAIProcessor
from axelo.models.contracts import MissionContract
from axelo.engine.models import RequirementSheet, VerdictTier
from axelo.engine.constitution import EngineConstitution
from axelo.engine.models import MissionState, PrincipalAgentState


# ── Platform definitions ──────────────────────────────────────────────────────

@dataclass
class PlatformCase:
    name: str
    message_turn1: str          # first natural-language user message
    message_turn2: str = ""     # optional second turn to push is_ready → True
    expected_url_fragment: str = ""
    expected_fields_min: int = 3   # minimum acceptable requested_fields count


PLATFORMS: list[PlatformCase] = [
    PlatformCase(
        name="Amazon",
        message_turn1=(
            "I want to scrape iPhone 15 product listings from amazon.com. "
            "Give me title, price, rating, number of reviews, ASIN, and seller info for each product. "
            "I need about 50 items."
        ),
        expected_url_fragment="amazon.com",
        expected_fields_min=4,
    ),
    PlatformCase(
        name="eBay",
        message_turn1=(
            "Collect used iPhone 15 listings from https://www.ebay.com/sch/i.html?_nkw=iphone+15+used. "
            "Fields I want: item title, price, condition, seller username, seller feedback score, "
            "shipping cost, listing URL, number of bids. Grab around 50 listings."
        ),
        expected_url_fragment="ebay.com",
        expected_fields_min=4,
    ),
    PlatformCase(
        name="Lazada",
        message_turn1=(
            "Scrape phone listings from https://www.lazada.com.my/catalog/?q=phone. "
            "I want product name, price, discount percentage, rating, number of reviews, "
            "seller/shop name, and product URL. Get 50 items."
        ),
        expected_url_fragment="lazada.com.my",
        expected_fields_min=4,
    ),
    PlatformCase(
        name="Shopee",
        message_turn1=(
            "Extract phone product listings from https://shopee.com/search?keyword=phone. "
            "Fields: product name, price, number sold, rating, shop name, location, product URL. "
            "About 50 results please."
        ),
        expected_url_fragment="shopee.com",
        expected_fields_min=4,
    ),
    PlatformCase(
        name="Temu",
        message_turn1=(
            "Crawl electronics listings from https://www.temu.com/search_result.html?search_key=electronics. "
            "Get product title, price, original price, discount, rating, number of reviews, product URL. "
            "50 items."
        ),
        expected_url_fragment="temu.com",
        expected_fields_min=4,
    ),
    PlatformCase(
        name="JD.com",
        message_turn1=(
            "Scrape iPhone listings from https://search.jd.com/Search?keyword=iPhone. "
            "I need: product title, price, shop name, number of comments, rating, product URL, SKU ID. "
            "50 listings."
        ),
        expected_url_fragment="jd.com",
        expected_fields_min=4,
    ),
    PlatformCase(
        name="Taobao",
        message_turn1=(
            "Extract phone listings from https://s.taobao.com/search?q=手机. "
            "Fields wanted: product title, price, monthly sales, shop name, location, product URL. "
            "Get 50 items."
        ),
        expected_url_fragment="taobao.com",
        expected_fields_min=4,
    ),
    PlatformCase(
        name="Pinduoduo",
        message_turn1=(
            "Crawl phone listings from https://www.pinduoduo.com/search_result.html?search_key=手机. "
            "I need: title, price, number of orders, shop name, product URL, images URL. "
            "50 items."
        ),
        expected_url_fragment="pinduoduo.com",
        expected_fields_min=4,
    ),
]


# ── Result collector ──────────────────────────────────────────────────────────

@dataclass
class PlatformResult:
    platform: str
    step1_pass: bool = False
    step2_pass: bool = False
    step3_pass: bool = False
    overall_pass: bool = False

    # Step 1 details
    ai_reply_turn1: str = ""
    ai_reply_turn2: str = ""
    requested_fields: list[str] = field(default_factory=list)
    is_ready_turn1: bool = False
    is_ready_turn2: bool = False
    target_url_set: bool = False
    objective_set: bool = False
    objective_type: str = ""
    mechanism_required: bool = False
    item_limit: int = 0
    blocking_gaps: list[str] = field(default_factory=list)
    contract_version_after_t2: int = 0

    # Step 2 details
    requirement_sheet_prompt: str = ""

    # Step 3 details
    verdict_tier: str = ""

    # Errors
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_chinese(text: str) -> bool:
    """Heuristic: at least 3 CJK codepoints → counts as Chinese."""
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return cjk >= 3


def _build_minimal_state(contract: MissionContract, execution_success: bool = True) -> PrincipalAgentState:
    ms = MissionState(
        session_id=contract.session_id or "test-session",
        target_url=contract.target_url,
        objective=contract.objective,
        mechanism_required=contract.mechanism_required,
    )
    return PrincipalAgentState(mission=ms)


# ── Per-platform test ─────────────────────────────────────────────────────────

async def run_platform(case: PlatformCase) -> PlatformResult:
    res = PlatformResult(platform=case.name)
    intake = IntakeAIProcessor()
    contract = MissionContract()
    history: list[dict[str, str]] = []

    # ── STEP 1a — Turn 1 ──────────────────────────────────────────────────────
    try:
        result1 = await intake.process_message(case.message_turn1, contract, history)
        ai_reply1 = result1["ai_reply"]
        contract = result1["updated_contract"]
        readiness1 = result1["readiness"]
        res.ai_reply_turn1 = ai_reply1[:200]
        res.is_ready_turn1 = readiness1.is_ready

        # Validate: ai_reply is Chinese
        if not _is_chinese(ai_reply1):
            res.add_error(f"Turn1 ai_reply not Chinese: {ai_reply1[:100]!r}")

        # Validate: core contract fields
        if not contract.target_url:
            res.add_error("target_url not set after turn 1")
        else:
            res.target_url_set = True

        if not contract.objective or len(contract.objective.strip()) < 15:
            res.add_error(f"objective too short or missing: {contract.objective!r}")
        else:
            res.objective_set = True

        res.requested_fields = [f.field_name for f in contract.requested_fields]
        res.objective_type = contract.objective_type
        res.mechanism_required = contract.mechanism_required
        res.item_limit = contract.item_limit
        res.blocking_gaps = list(readiness1.blocking_gaps)

        # Check requested_fields count
        if len(contract.requested_fields) < case.expected_fields_min:
            res.add_error(
                f"requested_fields count {len(contract.requested_fields)} < expected {case.expected_fields_min}: "
                f"{res.requested_fields}"
            )

        # Update history
        history.append({"role": "user", "content": case.message_turn1})
        history.append({"role": "assistant", "content": ai_reply1})

    except Exception as exc:
        res.add_error(f"Turn1 exception: {exc}\n{traceback.format_exc()}")
        return res  # can't continue without a contract

    # ── STEP 1b — Turn 2 (push to is_ready=True if not already) ───────────────
    if not res.is_ready_turn1:
        # Generic push: confirm defaults and ask to start
        turn2_msg = case.message_turn2 or (
            "Those fields are correct. Please start now — use 50 items and JSON output."
        )
        try:
            result2 = await intake.process_message(turn2_msg, contract, history)
            ai_reply2 = result2["ai_reply"]
            contract = result2["updated_contract"]
            readiness2 = result2["readiness"]
            res.ai_reply_turn2 = ai_reply2[:200]
            res.is_ready_turn2 = readiness2.is_ready
            res.blocking_gaps = list(readiness2.blocking_gaps)
            res.contract_version_after_t2 = contract.contract_version

            if not _is_chinese(ai_reply2):
                res.add_error(f"Turn2 ai_reply not Chinese: {ai_reply2[:100]!r}")

            history.append({"role": "user", "content": turn2_msg})
            history.append({"role": "assistant", "content": ai_reply2})
        except Exception as exc:
            res.add_error(f"Turn2 exception: {exc}")
    else:
        res.is_ready_turn2 = True  # already ready after turn 1

    # Readiness check — must be ready after ≤2 turns
    is_ready_final = res.is_ready_turn1 or res.is_ready_turn2
    if not is_ready_final:
        res.add_error(
            f"is_ready still False after 2 turns. blocking_gaps={res.blocking_gaps}"
        )

    # Step 1 passes if no errors so far
    res.step1_pass = not res.errors

    # ── STEP 2 — RequirementSheet bridge ─────────────────────────────────────
    try:
        kwargs = contract.to_requirement_sheet_kwargs()
        # Must have required keys
        for required_key in ("target_url", "objective", "fields", "item_limit"):
            if required_key not in kwargs:
                raise AssertionError(f"Missing key in to_requirement_sheet_kwargs: {required_key!r}")
        if not kwargs["target_url"]:
            raise AssertionError("to_requirement_sheet_kwargs returned empty target_url")
        if not kwargs["objective"]:
            raise AssertionError("to_requirement_sheet_kwargs returned empty objective")

        sheet = RequirementSheet(**kwargs)
        prompt_text = sheet.to_prompt()
        if not prompt_text or len(prompt_text.strip()) < 20:
            raise AssertionError(f"to_prompt() too short: {prompt_text!r}")
        res.requirement_sheet_prompt = prompt_text[:200]
        res.step2_pass = True
    except Exception as exc:
        res.add_error(f"Step2 RequirementSheet bridge error: {exc}")
        res.step2_pass = False

    # ── STEP 3 — classify_outcome verdict ────────────────────────────────────
    try:
        state = _build_minimal_state(contract, execution_success=True)
        verdict = EngineConstitution.classify_outcome(state, execution_success=True, contract=contract)

        # Validate verdict structure
        for key in ("status", "outcome", "verdict_tier", "summary", "verdict_chain"):
            if key not in verdict:
                raise AssertionError(f"classify_outcome missing key: {key!r}")

        tier = verdict["verdict_tier"]
        if tier not in {v.value for v in VerdictTier}:
            raise AssertionError(f"Unknown verdict_tier: {tier!r}")

        res.verdict_tier = tier
        res.step3_pass = True
    except Exception as exc:
        res.add_error(f"Step3 classify_outcome error: {exc}")
        res.step3_pass = False

    res.overall_pass = res.step1_pass and res.step2_pass and res.step3_pass
    return res


# ── Main runner ───────────────────────────────────────────────────────────────

async def run_all() -> list[PlatformResult]:
    results: list[PlatformResult] = []
    for case in PLATFORMS:
        print(f"\n{'='*60}")
        print(f"Testing: {case.name}")
        print(f"{'='*60}")
        t0 = time.time()
        result = await run_platform(case)
        elapsed = time.time() - t0
        results.append(result)

        status = "PASS" if result.overall_pass else "FAIL"
        print(f"  [{status}] in {elapsed:.1f}s")
        if result.ai_reply_turn1:
            print(f"  AI Reply T1: {result.ai_reply_turn1[:120]!r}")
        if result.ai_reply_turn2:
            print(f"  AI Reply T2: {result.ai_reply_turn2[:120]!r}")
        print(f"  is_ready T1={result.is_ready_turn1}  T2={result.is_ready_turn2}")
        print(f"  target_url_set={result.target_url_set}  objective_set={result.objective_set}")
        print(f"  objective_type={result.objective_type}  mechanism_required={result.mechanism_required}")
        print(f"  item_limit={result.item_limit}")
        print(f"  requested_fields ({len(result.requested_fields)}): {result.requested_fields}")
        print(f"  blocking_gaps: {result.blocking_gaps}")
        print(f"  Step1={result.step1_pass}  Step2={result.step2_pass}  Step3={result.step3_pass}")
        print(f"  verdict_tier={result.verdict_tier}")
        if result.errors:
            print(f"  ERRORS:")
            for e in result.errors:
                print(f"    - {e}")

    return results


def print_summary(results: list[PlatformResult]) -> None:
    print("\n\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    passed = [r for r in results if r.overall_pass]
    failed = [r for r in results if not r.overall_pass]
    print(f"  Passed: {len(passed)}/{len(results)}")
    print(f"  Failed: {len(failed)}/{len(results)}")
    print()

    for r in results:
        status = "[PASS]" if r.overall_pass else "[FAIL]"
        ready = "ready" if (r.is_ready_turn1 or r.is_ready_turn2) else "NOT_READY"
        fields_summary = f"{len(r.requested_fields)} fields"
        print(f"  {status}  {r.platform:<15} {ready:<12} {fields_summary}")
        if not r.overall_pass:
            for e in r.errors:
                short = e.split('\n')[0][:100]
                print(f"             ERROR: {short}")

    print()
    print("Per-step pass rates:")
    s1 = sum(1 for r in results if r.step1_pass)
    s2 = sum(1 for r in results if r.step2_pass)
    s3 = sum(1 for r in results if r.step3_pass)
    n = len(results)
    print(f"  Step1 (IntakeAI):            {s1}/{n}")
    print(f"  Step2 (RequirementSheet):    {s2}/{n}")
    print(f"  Step3 (classify_outcome):    {s3}/{n}")


if __name__ == "__main__":
    results = asyncio.run(run_all())
    print_summary(results)
    # Exit with non-zero if any platform failed
    sys.exit(0 if all(r.overall_pass for r in results) else 1)
