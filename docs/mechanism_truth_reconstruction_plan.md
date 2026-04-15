# Mechanism-Truth Reconstruction Plan

## 1. Plan Objective

This plan changes the system from:

- a crawler/replay production line that can produce runnable artifacts

into:

- a reverse-discovery system that can distinguish:
  - operational success
  - replay-only success
  - mechanism-understood success

The core requirement is simple:

- the system must stop rewarding "can run" as if it were equal to "mechanism understood"
- the system must maintain competing hypotheses instead of one privileged story
- the system must treat refuting evidence as first-class state
- the system must make runtime discovery a mission gate for targets where replay alone is insufficient evidence

This document is not a generic architecture proposal. It is a corrective plan directly derived from the current system failure mode.

## 2. Current Failure Pattern

The current engine exhibits a consistent bias:

1. It equates artifact completeness with truth.
2. It seeds one dominant hypothesis too early.
3. It rarely invalidates hypotheses once seeded.
4. It underweights runtime evidence.
5. It promotes advisory signals into logs but not into hard mission gates.

As a result, the engine can truthfully say:

- "the crawler works"

while falsely implying:

- "the protocol is understood"

That distinction must become explicit in state, decision-making, and UI.

## 3. System-Wide Redesign Principles

The redesign follows six principles.

### 3.1 Separate execution truth from mechanism truth

The system must maintain two independent judgments:

- `execution_truth`
  - can the current artifact run and produce target data?
- `mechanism_truth`
  - do we understand the actual causal mechanism that makes the target request succeed?

These two values must never be collapsed into one score.

### 3.2 Competing hypotheses, not one story

The principal agent must maintain parallel explanations, for example:

- true signing algorithm
- runtime fingerprint generation
- cookie/session binding
- replay-only transport reuse
- mixed mechanism

The runtime should not commit to one explanation before evidence has discriminated between them.

### 3.3 Evidence must support and refute

Every important evidence item must be able to:

- support a hypothesis
- weaken a hypothesis
- invalidate a hypothesis

If the engine cannot express "this evidence makes hypothesis H less plausible", then its reasoning loop is structurally biased.

### 3.4 Runtime discovery is a gate, not an optional branch

For targets with anti-bot, fingerprint, or runtime-generated inputs, runtime discovery must be required before the system can declare mechanism understanding.

### 3.5 Critic must block, not just comment

`critic` findings must be able to prevent finalization when the mission claims mechanism understanding without sufficient evidence.

### 3.6 Memory must diversify, not reinforce bias

Memory retrieval must pull:

- successful analogues
- failed analogues
- invalidated analogues

Otherwise memory acts as confirmation bias amplification.

## 4. New Outcome Model

The engine must stop using one binary mission outcome.

### 4.1 New mission outcomes

Add a formal mission outcome enum with at least:

- `failed`
- `operational_success`
- `replay_success`
- `mechanism_partial`
- `mechanism_validated`

Meaning:

- `operational_success`
  - artifacts run, but no strong claim about the underlying mechanism
- `replay_success`
  - the target can be replayed reliably, but the mechanism is not understood
- `mechanism_partial`
  - some structural understanding exists, but causal closure is incomplete
- `mechanism_validated`
  - the mechanism has evidence-backed explanation and verification

### 4.2 Mission completion rule

The system may only declare:

- `mission.status = success`

when either:

- the operator explicitly requested replay-only delivery, or
- the engine reached `mechanism_validated`

If the engine only has runnable replay, it must end as:

- `mission.status = partial`
- `mission.outcome = replay_success`

## 5. New Trust Model

The current trust model is task-completion weighted. That must be split.

### 5.1 Replace single trust score with two top-level scores

- `execution_trust`
- `mechanism_trust`

### 5.2 Execution trust should depend on

- verify pass quality
- extraction coverage
- response correctness
- endpoint stability
- absence of warnings and drift

### 5.3 Mechanism trust should depend on

- explicit required headers or token fields identified
- runtime source linkage identified
- hypothesis competition resolved
- refuting evidence accounted for
- algorithm / fingerprint / cookie/session model explained
- causal consistency between observed success and claimed mechanism

### 5.4 Output contract

UI and artifacts must display both scores independently.

Examples:

- `execution_trust = high`, `mechanism_trust = low`
- `execution_trust = high`, `mechanism_trust = medium`
- `execution_trust = high`, `mechanism_trust = high`

The first case is common and must no longer be mislabeled as overall success.

## 6. Hypothesis System Redesign

### 6.1 Replace single seeded hypothesis with a hypothesis set

At mission start, the engine should create a `HypothesisBoard` with multiple candidate explanations.

Minimum initial set:

- `H-signature`: request succeeds because a signature algorithm is required
- `H-replay`: request succeeds because replaying stable transport/session state is enough
- `H-runtime-fingerprint`: success depends on runtime-generated fingerprint/token material
- `H-session-binding`: success depends mainly on cookie/session/auth state
- `H-mixed`: success depends on a mixture of transport state and dynamic token material

### 6.2 Hypothesis fields

Each hypothesis should maintain:

- prior probability
- posterior probability
- support evidence ids
- refute evidence ids
- unresolved contradictions
- discriminating next test
- mechanism class
- closure state

### 6.3 Hypothesis update engine

Evidence ingestion must update:

- support
- contradiction
- posterior

Not just append summary strings.

### 6.4 Hypothesis invalidation

A hypothesis should be demoted or invalidated when:

- static repeatedly yields `unknown`
- signature extractor has zero confidence
- protocol shows zero token-sensitive fields
- runtime hooks show no dynamic token generation where the hypothesis expects it
- replay succeeds without the supposedly required mechanism

### 6.5 Stop condition for mechanism claim

The engine may not claim mechanism understanding until:

- the dominant hypothesis has clearly outranked alternatives
- the alternatives have explicit refuting evidence
- the dominant hypothesis explains the successful run causally

## 7. Evidence Graph Redesign

The current evidence graph is link-heavy but belief-light.

### 7.1 Expand graph semantics

The graph must track:

- request -> token usage
- token -> runtime source
- token -> static source
- hypothesis -> supporting evidence
- hypothesis -> refuting evidence
- task -> produced evidence
- evidence -> changed belief state

### 7.2 Add evidence impact objects

Each evidence item should include:

- `supports`
- `refutes`
- `neutral`
- `impact_strength`
- `why`

This lets the engine say:

- "protocol evidence with zero token-sensitive fields weakens `H-signature`"

instead of just:

- "protocol completed successfully"

### 7.3 Add causal completeness markers

For mechanism truth, the graph should explicitly record whether the system has explained:

- target endpoint selection
- required headers
- required query/body params
- timestamp or nonce generation
- fingerprint generation
- session or cookie dependence
- success/failure differences

This should become a formal `MechanismAssessment`, not an implied narrative.

## 8. Runtime Discovery Redesign

Runtime discovery must become a core phase, not an opportunistic side branch.

### 8.1 Mandatory runtime branch conditions

Force runtime discovery when any of the following are true:

- `observed_replay` is chosen
- static confidence is below threshold
- required headers remain unknown
- signature extractor confidence is below threshold
- protocol evidence is insufficient
- target category is known to be browser-state sensitive

### 8.2 Runtime objectives

Runtime discovery should aim to answer:

- what values are created at runtime?
- where do those values come from?
- are they deterministic, session-bound, or page-instance-bound?
- do they explain success/failure?

### 8.3 Required runtime capabilities

The runtime hook executor must move beyond planning metadata.

Required instrumentation targets:

- `fetch`
- `XMLHttpRequest`
- `crypto.subtle`
- `Date.now`
- `Math.random`
- `localStorage`
- `sessionStorage`
- `document.cookie`
- `performance` and browser fingerprint surfaces

### 8.4 Runtime closure

Mechanism validation cannot be granted when:

- runtime coverage remains near zero
- but the current dominant hypothesis depends on runtime-generated signals

## 9. Verify Redesign

Verify must stop acting as a generic "artifact works" checker only.

### 9.1 Split verify into two verdicts

Every verify result must emit:

- `execution_verdict`
- `mechanism_verdict`

Possible mechanism verdicts:

- `unknown`
- `unsupported`
- `partial`
- `validated`

### 9.2 Replay is not mechanism validation

If codegen strategy is `observed_replay`, verify may produce:

- `execution_verdict = pass`
- `mechanism_verdict = unknown` or `partial`

unless there is independent evidence for:

- source of required values
- causal explanation of success
- alternative hypotheses invalidated

### 9.3 Mechanism-specific verify checks

Add verification checks for:

- required header necessity
- field mutation necessity
- runtime token dependence
- success/failure sensitivity to token omission
- response degradation under controlled perturbation

### 9.4 Verification outputs

The verifier must produce:

- why the request succeeds
- what is still unexplained
- whether success depends on replay state only

## 10. Critic Redesign

`critic` must become a mission gate.

### 10.1 Critic should be able to block finalization

If critic reports any of these:

- missing canonical required headers
- unsupported dominant hypothesis
- unresolved mechanism contradiction
- runtime coverage below threshold for the active hypothesis

then:

- `produce` must be disallowed for mechanism-validating outcomes

### 10.2 Critic outputs

Critic should emit structured blockers:

- `blocking_conditions`
- `non_blocking_gaps`
- `dominant_hypothesis_risk`
- `recommended_discriminating_test`

### 10.3 Planner integration

Critic output must feed:

- branch creation
- branch reprioritization
- mission outcome downgrade

## 11. Protocol and Target-Surface Selection Redesign

The current engine can lock onto a replayable but low-value endpoint.

### 11.1 Separate easy transport surface from core anti-bot surface

Protocol analysis should rank targets by:

- request importance to the operator objective
- sensitivity to token omission
- pagination or listing relevance
- anti-bot richness
- replay sensitivity

### 11.2 New protocol objective

The engine should identify:

- primary business endpoint
- support/config endpoint
- anti-bot or token bootstrap endpoint

and keep them distinct.

### 11.3 Selection policy

The engine must avoid declaring mission completion if it only mastered:

- a low-risk config endpoint

while leaving the actual data-bearing surface unexplained.

## 12. Memory Redesign

Memory currently reinforces prior paths too strongly.

### 12.1 Two memory classes

- `episodic_memory`
  - past runs, branching decisions, failure reasons
- `semantic_memory`
  - reusable patterns, mechanism motifs, runtime token classes

### 12.2 Balanced retrieval

Memory agent should retrieve:

- best matching successes
- best matching failures
- best matching invalidated hypotheses

### 12.3 Retrieval ranking

Ranking should reward:

- explanatory diversity
- mechanism relevance
- contradiction value

not just similarity to previously successful runs.

### 12.4 Memory safety rule

No memory result should be allowed to directly boost trust.
Memory may only:

- suggest probes
- seed hypotheses
- supply alternative explanations

It must not act as evidence.

## 13. UI and Artifact Redesign

The UI currently implies stronger success than the engine actually knows.

### 13.1 Add separate visible mission fields

Display:

- mission outcome
- execution trust
- mechanism trust
- dominant hypothesis
- refuted hypotheses
- unresolved contradictions
- runtime coverage

### 13.2 Replace "Mission success" with outcome-aware labels

Examples:

- `Operational success`
- `Replay success`
- `Mechanism partially understood`
- `Mechanism validated`

### 13.3 Evidence dashboard additions

Add panels for:

- competing hypotheses
- refutation count
- runtime closure
- endpoint significance
- mechanism blockers

### 13.4 Artifact changes

Final report must include:

- outcome type
- execution trust
- mechanism trust
- dominant hypothesis
- competing hypotheses and why they lost
- what remains unproven
- replay-only disclaimer when applicable

## 14. File-Level Implementation Plan

### Phase A: Outcome and trust split

Files:

- `axelo/engine/models.py`
- `axelo/engine/runtime.py`
- `axelo/engine/constitution.py`
- `axelo/engine/ui.py`
- `axelo/engine/artifacts.py`

Work:

- add mission outcome enum and mechanism assessment
- split trust into execution and mechanism trust
- remove direct mapping from verify success to mission success

Exit:

- a successful replay run no longer appears as mechanism-validated by default

### Phase B: Competing hypotheses and invalidation

Files:

- `axelo/engine/models.py`
- `axelo/engine/runtime.py`
- `axelo/engine/principal.py`
- `axelo/engine/constitution.py`

Work:

- seed multiple hypotheses
- add posterior updates
- add invalidation rules
- store support and refute edges explicitly

Exit:

- `hypothesis_refute` is populated by actual evidence
- `hyp-01` can be demoted or invalidated

### Phase C: Runtime discovery as gate

Files:

- `axelo/engine/constitution.py`
- `axelo/engine/subagents.py`
- `axelo/engine/runtime.py`
- `axelo/tools/verify_tool.py`

Work:

- make runtime discovery mandatory in qualifying cases
- convert runtime hook from optional branch into mandatory gate where appropriate
- require runtime closure for mechanism validation

Exit:

- `observed_replay` with low runtime evidence cannot end as full reverse success

### Phase D: Verify redesign

Files:

- `axelo/tools/verify_tool.py`
- `axelo/engine/runtime.py`
- `axelo/engine/artifacts.py`

Work:

- add `execution_verdict` and `mechanism_verdict`
- add perturbation checks
- record replay-only disclaimers

Exit:

- verify can pass execution while withholding mechanism validation

### Phase E: Critic as gate

Files:

- `axelo/engine/subagents.py`
- `axelo/engine/runtime.py`
- `axelo/engine/constitution.py`

Work:

- add blocking conditions to critic output
- prohibit `produce` under unresolved blockers

Exit:

- critic can prevent finalization

### Phase F: Protocol surface ranking

Files:

- `axelo/engine/subagents.py`
- `axelo/engine/runtime.py`
- `axelo/engine/models.py`

Work:

- distinguish config/bootstrap/data surfaces
- rank endpoint significance

Exit:

- system no longer treats mastering an easy config endpoint as core mission success

### Phase G: Memory de-biasing

Files:

- `axelo/engine/subagents.py`
- `axelo/engine/runtime.py`
- `axelo/memory/db.py`

Work:

- retrieve counterexamples
- retrieve invalidated analogues
- separate memory suggestions from evidence

Exit:

- memory broadens the search space instead of narrowing it prematurely

## 15. Acceptance Criteria

The redesign is successful only if all of the following are true:

1. A replay-only success is no longer labeled as full reverse success.
2. A dominant hypothesis can be demoted or invalidated by counter-evidence.
3. `hypothesis_refute` is populated in real runs.
4. Runtime coverage becomes mandatory for mechanism-validating outcomes.
5. Critic blockers can prevent mission finalization.
6. Verify distinguishes runnable replay from understood mechanism.
7. Trust is split into execution and mechanism components.
8. Final report explicitly tells the operator what is still unknown.
9. Memory retrieval includes counterexamples.
10. The engine can complete a run and honestly say:
   - "artifact works, but mechanism is still not established"

## 16. Execution Order

Recommended implementation order:

1. Phase A
2. Phase B
3. Phase D
4. Phase C
5. Phase E
6. Phase F
7. Phase G

Reason:

- first fix the semantics of success
- then fix belief management
- then fix verifier outputs
- then harden runtime gating
- then let critic enforce it
- then improve endpoint selection and memory bias

## 17. What This Plan Explicitly Rejects

This plan does not attempt to:

- patch individual sites with hard-coded special cases
- equate replay reliability with reverse understanding
- use memory as a shortcut to truth
- hide uncertainty behind a single trust score

The target state is not:

- "the crawler works"

The target state is:

- "the system can explicitly say what it knows, what it does not know, and why it believes the current mechanism explanation is or is not valid"
