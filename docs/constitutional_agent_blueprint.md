# Constitutional Agent Blueprint

## Goal

Move the system from a tool-and-rule control runtime into a true long-horizon agent runtime:

- one principal agent owns the end-to-end mission
- specialist sub-agents execute bounded work with clear responsibilities
- a constitution replaces most hard-coded routing heuristics
- memory, evidence, and agenda state give the system continuity
- the UI exposes action and cognition summaries instead of opaque tool churn

This is not a proposal to remove all constraints. It is a proposal to replace brittle task-specific branching with durable constitutional guidance, explicit state, and stronger agent contracts.

## Historical Limitation

The old split runtime was mostly:

- a coordinator built a finite task graph
- workers ran against that graph
- review logic inspected specific outputs
- fixed review rules inserted a small number of fallback tasks

That gets reliability, but it does not yet produce a genuinely persistent agent with:

- long-horizon intent maintenance
- self-directed branch exploration
- adaptive decomposition
- explicit world model updates
- durable context across runs

## Target Runtime

The target runtime should have five layers.

### 1. Constitution Layer

This is the invariant contract for the principal agent.

It should define:

- mission priority: obtain trustworthy crawl and reverse artifacts
- truth priority: evidence beats intuition, verification beats speculation
- persistence priority: keep working until success criteria or explicit stop condition
- efficiency priority: prefer the cheapest next evidence that can reduce uncertainty
- artifact priority: every conclusion must produce traceable artifacts
- safety priority: obey legal, rate, auth, and operator constraints

The constitution should not hard-code site logic. It should define decision principles.

### 2. Cognitive State Layer

The principal agent needs explicit state objects instead of relying only on prompt history.

Recommended state objects:

- `MissionState`
  - target
  - operator objective
  - success criteria
  - risk envelope
- `EvidenceGraph`
  - requests
  - responses
  - headers
  - cookies
  - tokens
  - inferred relationships
  - provenance links
- `HypothesisBoard`
  - current hypotheses
  - supporting evidence
  - refuting evidence
  - confidence
  - next cheapest test
- `Agenda`
  - active branches
  - deferred branches
  - blocked branches
  - completion criteria
- `RunMemory`
  - prior attempts
  - successful patterns
  - failure classes
  - reusable artifacts

This is what gives the agent continuity and “big-picture” awareness.

### 3. Principal Agent Layer

One principal agent should own the full mission.

Its job is to:

- interpret the operator intent
- maintain mission state
- choose the next branch to explore
- spawn sub-agents
- merge evidence into the evidence graph
- decide whether to continue, branch, retry, or stop
- decide whether a result is trustworthy enough to ship

This principal agent should not call every tool itself. It should delegate.

### 4. Specialist Sub-Agent Layer

Sub-agents should be capability-specialized, not site-specialized.

Recommended sub-agents:

- `ReconAgent`
  - navigation
  - page-state discovery
  - request capture
  - anti-bot surface detection
- `BundleAgent`
  - JS bundle fetch
  - source mapping
  - import graph reconstruction
- `ReverseAgent`
  - token path discovery
  - crypto hint extraction
  - function candidate ranking
- `RuntimeHookAgent`
  - runtime instrumentation
  - hook injection
  - token material observation
- `ProtocolAgent`
  - endpoint clustering
  - request schema inference
  - transport replay strategy
- `ExtractionAgent`
  - DOM/API field mapping
  - extractor synthesis
  - response schema normalization
- `CodegenAgent`
  - crawler assembly
  - replay builder
  - signature implementation
- `VerifierAgent`
  - request correctness
  - extraction coverage
  - trust scoring
- `CriticAgent`
  - challenge weak assumptions
  - flag evidence gaps
  - propose the next discriminating test
- `MemoryAgent`
  - session compaction
  - reusable artifact indexing
  - cross-run retrieval

Each sub-agent should emit structured outputs and confidence, not just free text.

### 5. Tool Runtime Layer

Tools remain necessary, but they should become execution affordances behind agent intent:

- browser automation
- traffic interception
- HAR diff
- JS AST/static analysis
- runtime hook injection
- DOM snapshotting
- cookie/storage export
- transport replay
- extractor evaluation
- artifact packaging

Tools should not own orchestration logic.

## Replace Hard Rules With Constitutional Review

Do not remove all rules. Move rules to a more durable form.

Hard-coded routing branches like “if static is weak then add trace” should become:

- evaluate evidence coverage
- identify the highest-value uncertainty
- choose the cheapest next observation that can reduce that uncertainty
- select the sub-agent best suited for that observation

The principal agent should reason from state and principles, not from fixed site trees.

## Continuous Thinking Without Exposing Raw Chain-of-Thought

The runtime should support sustained deliberation, but the UI should not dump raw hidden reasoning.

Recommended public cognition model:

- `Current objective`
- `Current hypothesis`
- `Evidence confidence`
- `Why the next action was chosen`
- `What changed after the action`
- `What remains uncertain`

That gives operators transparency without depending on verbatim internal chain-of-thought.

## Long-Horizon Execution Model

The agent loop should become:

1. read mission state
2. inspect evidence graph
3. choose the next uncertainty worth reducing
4. spawn the right sub-agent
5. merge results into memory and evidence graph
6. re-score hypotheses
7. update agenda
8. continue until success or explicit stop condition

This loop should persist across long runs without returning control after every small step.

## Memory Model

Three memory classes are needed.

### Working Memory

Short-lived, run-scoped.

Examples:

- latest captured requests
- current target endpoints
- active token candidates
- current extraction schema

### Episodic Memory

Session-level history.

Examples:

- branches tried
- failures observed
- what verification rejected
- what evidence changed the plan

### Semantic Memory

Cross-run reusable knowledge.

Examples:

- common anti-bot patterns
- replay strategies that worked
- reusable extraction recipes
- common token morphologies

## Stronger Reverse and Crawling Capability

To materially raise the ceiling, the system should gain these generic tools:

- runtime hook injector for `fetch`, `XMLHttpRequest`, `crypto.subtle`, `atob`, `btoa`, `WebSocket`
- storage-state exporter for cookies, localStorage, sessionStorage, indexedDB hints
- request diff tool that compares successful and failed requests
- response schema profiler
- JS import graph explorer
- deobfuscation trace recorder
- DOM-to-API field alignment tool
- anti-bot fingerprint profiler
- headful fallback executor

These are capability upgrades, not site patches.

## UI Direction

The UI should show one coherent surface:

- mission status
- action trace
- cognition summaries
- current branch
- evidence coverage
- trust level
- produced artifacts

The UI should not show duplicated modal headers or mixed old/new dashboard fragments.

## Migration Path

### Phase 1

- keep current unified engine
- add explicit `MissionState`, `EvidenceGraph`, `Agenda`, and `HypothesisBoard`
- surface cognition and action summaries in the UI

### Phase 2

- replace fixed review rules with a principal-agent review loop
- let the principal agent choose the next branch from state
- keep hard stop conditions and artifact invariants

### Phase 3

- expand the sub-agent catalog
- move more work from fixed stages into agent-selected strategies
- keep tools as execution primitives

### Phase 4

- add persistent semantic memory
- allow cross-run reuse of strategies and evidence patterns
- add branch scoring and budget-aware execution

## Non-Negotiable Constraints

Even in a more autonomous runtime, these must stay explicit:

- budget limits
- max branch depth
- verification gate before success
- artifact completeness requirements
- operator-specified legal or auth constraints

Removing those would not make the system more intelligent. It would make it less controllable.

## Recommendation

Yes, the system should evolve toward a real principal-agent plus specialist sub-agent runtime.

But the correct path is:

- fewer brittle site/task rules
- more constitutional guidance
- stronger explicit state
- stronger memory
- stronger evidence graph
- stronger verification

Do not aim for “no structure”. Aim for “stateful autonomy under durable principles”.
