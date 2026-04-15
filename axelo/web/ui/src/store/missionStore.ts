/**
 * 全局状态管理（Zustand-like 轻量实现，无依赖）
 * 存储当前会话的所有任务状态，供 Scene 和 Dashboard 共用。
 */

export type AgentStatus = 'idle' | 'working' | 'done' | 'failed'

export interface AgentState {
  role: string
  status: AgentStatus
  currentTask: string
  evidenceCount: number
}

export interface CoverageMap {
  acquisition: number
  protocol: number
  reverse: number
  runtime: number
  schema: number
  extraction: number
  build: number
  verify: number
  [key: string]: number
}

export interface MissionState {
  sessionId: string
  targetUrl: string
  missionStatus: string
  missionOutcome: string
  step: number
  maxSteps: number
  evidenceCount: number
  hypothesisCount: number
  coverage: CoverageMap
  trustScore: number
  executionTrustScore: number
  mechanismTrustScore: number
  currentFocus: string
  currentUncertainty: string
  dominantHypothesis: string
  mechanismBlockers: string[]
  activeAgentRole: string
  agents: Record<string, AgentState>
  events: WsEvent[]
  connected: boolean
}

export interface WsEvent {
  type: string
  kind: string
  message: string
  agentRole?: string
  objective?: string
  publishedAt?: string
  state?: Partial<MissionState>
  // New fields for verdict/reconciliation/risk events
  step?: number | string
  tier?: string
  actions?: string[]
  field_evidence?: any[]
  coverage_snapshot?: Record<string, number>
}

export interface SessionSnapshot {
  session_id?: string
  site_code?: string
  site_key?: string
  url?: string
  goal?: string
  status?: string
  outcome?: string
  success?: boolean
  request?: Record<string, any>
  principal_state?: Record<string, any>
  mission_report?: Record<string, any>
  artifact_index?: Record<string, any>
}

type Listener = (state: MissionState) => void

const AGENT_ROLES = [
  'recon-agent',
  'transport-agent',
  'reverse-agent',
  'runtime-agent',
  'schema-agent',
  'builder-agent',
  'verifier-agent',
  'critic-agent',
  'memory-agent',
]

function makeInitialAgents(): Record<string, AgentState> {
  const agents: Record<string, AgentState> = {}
  for (const role of AGENT_ROLES) {
    agents[role] = { role, status: 'idle', currentTask: '', evidenceCount: 0 }
  }
  return agents
}

const DEFAULT_COVERAGE: CoverageMap = {
  acquisition: 0, protocol: 0, reverse: 0, runtime: 0,
  schema: 0, extraction: 0, build: 0, verify: 0,
}

class MissionStore {
  private state: MissionState = {
    sessionId: '',
    targetUrl: '',
    missionStatus: 'idle',
    missionOutcome: 'unknown',
    step: 0,
    maxSteps: 12,
    evidenceCount: 0,
    hypothesisCount: 0,
    coverage: { ...DEFAULT_COVERAGE },
    trustScore: 0,
    executionTrustScore: 0,
    mechanismTrustScore: 0,
    currentFocus: '',
    currentUncertainty: '',
    dominantHypothesis: '',
    mechanismBlockers: [],
    activeAgentRole: '',
    agents: makeInitialAgents(),
    events: [],
    connected: false,
  }

  private listeners: Set<Listener> = new Set()

  getState(): MissionState { return this.state }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private notify(): void {
    for (const fn of this.listeners) fn(this.state)
  }

  setConnected(connected: boolean): void {
    this.state = { ...this.state, connected }
    this.notify()
  }

  selectSession(sessionId: string): void {
    this.state = {
      ...this.state,
      sessionId,
      targetUrl: '',
      missionStatus: 'idle',
      missionOutcome: 'unknown',
      evidenceCount: 0,
      hypothesisCount: 0,
      trustScore: 0,
      executionTrustScore: 0,
      mechanismTrustScore: 0,
      currentFocus: '',
      currentUncertainty: '',
      dominantHypothesis: '',
      mechanismBlockers: [],
      activeAgentRole: '',
      agents: makeInitialAgents(),
      events: [],
      step: 0,
      coverage: { ...DEFAULT_COVERAGE },
    }
    this.notify()
  }

  hydrateSession(snapshot: SessionSnapshot): void {
    const principal = snapshot.principal_state || {}
    const mission = (principal.mission || {}) as Record<string, any>
    const trust = (principal.trust || {}) as Record<string, any>
    const mechanism = (principal.mechanism || {}) as Record<string, any>
    const evidenceGraph = (principal.evidence_graph || {}) as Record<string, any>
    const artifactIndex = snapshot.artifact_index || {}
    const artifacts = Array.isArray(artifactIndex.artifacts) ? artifactIndex.artifacts : []
    const agentRunCount = artifacts.filter((item: any) => item && item.category === 'agent_runs').length
    const evidenceCount = Array.isArray(principal.evidence) ? principal.evidence.length : this.state.evidenceCount
    const hypothesisCount = Array.isArray(principal.hypotheses) ? principal.hypotheses.length : this.state.hypothesisCount
    const currentUncertainty = String(mission.current_uncertainty || snapshot.mission_report?.current_uncertainty || this.state.currentUncertainty)
    const blockers = Array.isArray(mechanism.blocking_conditions) ? mechanism.blocking_conditions : []
    const effectiveBlockers = blockers.length
      ? blockers
      : (String(snapshot.status || mission.status || this.state.missionStatus) === 'failed' && currentUncertainty ? [currentUncertainty] : this.state.mechanismBlockers)
    this.state = {
      ...this.state,
      sessionId: snapshot.session_id || this.state.sessionId,
      targetUrl: snapshot.url || mission.target_url || this.state.targetUrl,
      missionStatus: String(snapshot.status || mission.status || this.state.missionStatus),
      missionOutcome: String(snapshot.outcome || mission.outcome || this.state.missionOutcome),
      step: agentRunCount || this.state.step,
      evidenceCount,
      hypothesisCount,
      coverage: normalizeCoverage(evidenceGraph.coverage || {}),
      trustScore: toNumber(trust.score, this.state.trustScore),
      executionTrustScore: toNumber(trust.execution_score, this.state.executionTrustScore),
      mechanismTrustScore: toNumber(trust.mechanism_score, this.state.mechanismTrustScore),
      currentFocus: String(mission.current_focus || this.state.currentFocus),
      currentUncertainty,
      dominantHypothesis: String(mechanism.dominant_hypothesis_id || this.state.dominantHypothesis),
      mechanismBlockers: effectiveBlockers,
    }
    this.notify()
  }

  applyEvent(event: WsEvent): void {
    const s = normalizePatch(event.state || {})

    // Update active agent
    const activeRole = event.agentRole || ''
    const agents = { ...this.state.agents }
    if (activeRole && agents[activeRole]) {
      // Reset all others to idle
      for (const role of AGENT_ROLES) {
        if (role !== activeRole && agents[role].status === 'working') {
          agents[role] = { ...agents[role], status: 'idle' }
        }
      }
      // Mark current as working or done
      if (event.kind === 'dispatch') {
        agents[activeRole] = { ...agents[activeRole], status: 'working', currentTask: event.message }
      } else if (event.kind === 'complete') {
        agents[activeRole] = { ...agents[activeRole], status: 'done', currentTask: '' }
      }
    }

    // Determine step from event log length
    const step = event.kind === 'dispatch' ? this.state.step + 1 : this.state.step

    this.state = {
      ...this.state,
      missionStatus: s.missionStatus || this.state.missionStatus,
      missionOutcome: s.missionOutcome || this.state.missionOutcome,
      evidenceCount: s.evidenceCount ?? this.state.evidenceCount,
      hypothesisCount: s.hypothesisCount ?? this.state.hypothesisCount,
      coverage: { ...this.state.coverage, ...(s.coverage || {}) },
      trustScore: s.trustScore ?? this.state.trustScore,
      executionTrustScore: s.executionTrustScore ?? this.state.executionTrustScore,
      mechanismTrustScore: s.mechanismTrustScore ?? this.state.mechanismTrustScore,
      currentFocus: s.currentFocus ?? this.state.currentFocus,
      currentUncertainty: s.currentUncertainty ?? this.state.currentUncertainty,
      dominantHypothesis: s.dominantHypothesis ?? this.state.dominantHypothesis,
      mechanismBlockers: s.mechanismBlockers ?? this.state.mechanismBlockers,
      activeAgentRole: activeRole || this.state.activeAgentRole,
      agents,
      step,
      events: [...this.state.events.slice(-49), event],
    }
    if (!this.state.mechanismBlockers.length && this.state.missionStatus === 'failed' && this.state.currentUncertainty) {
      this.state.mechanismBlockers = [this.state.currentUncertainty]
    }
    this.notify()
  }
}

export const missionStore = new MissionStore()

function toNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function normalizeCoverage(raw: Record<string, unknown>): CoverageMap {
  const normalized: CoverageMap = { ...DEFAULT_COVERAGE }
  for (const [key, value] of Object.entries(raw || {})) {
    const numeric = toNumber(value)
    if (key === 'codegen') {
      normalized.build = numeric
    } else {
      normalized[key] = numeric
    }
  }
  return normalized
}

function normalizePatch(raw: Record<string, unknown>) {
  return {
    missionStatus: raw.missionStatus !== undefined || raw.mission_status !== undefined
      ? String(raw.missionStatus ?? raw.mission_status ?? '')
      : undefined,
    missionOutcome: raw.missionOutcome !== undefined || raw.mission_outcome !== undefined
      ? String(raw.missionOutcome ?? raw.mission_outcome ?? '')
      : undefined,
    evidenceCount: typeof (raw.evidenceCount ?? raw.evidence_count) === 'number' ? Number(raw.evidenceCount ?? raw.evidence_count) : undefined,
    hypothesisCount: typeof (raw.hypothesisCount ?? raw.hypothesis_count) === 'number' ? Number(raw.hypothesisCount ?? raw.hypothesis_count) : undefined,
    coverage: raw.coverage ? normalizeCoverage(raw.coverage as Record<string, unknown>) : undefined,
    trustScore: typeof (raw.trustScore ?? raw.trust_score) === 'number' ? Number(raw.trustScore ?? raw.trust_score) : undefined,
    executionTrustScore: typeof (raw.executionTrustScore ?? raw.execution_trust_score) === 'number'
      ? Number(raw.executionTrustScore ?? raw.execution_trust_score)
      : undefined,
    mechanismTrustScore: typeof (raw.mechanismTrustScore ?? raw.mechanism_trust_score) === 'number'
      ? Number(raw.mechanismTrustScore ?? raw.mechanism_trust_score)
      : undefined,
    currentFocus: raw.currentFocus !== undefined || raw.current_focus !== undefined
      ? String(raw.currentFocus ?? raw.current_focus ?? '')
      : undefined,
    currentUncertainty: raw.currentUncertainty !== undefined || raw.current_uncertainty !== undefined
      ? String(raw.currentUncertainty ?? raw.current_uncertainty ?? '')
      : undefined,
    dominantHypothesis: raw.dominantHypothesis !== undefined || raw.dominant_hypothesis !== undefined
      ? String(raw.dominantHypothesis ?? raw.dominant_hypothesis ?? '')
      : undefined,
    mechanismBlockers: Array.isArray(raw.mechanismBlockers ?? raw.mechanism_blockers)
      ? [...((raw.mechanismBlockers ?? raw.mechanism_blockers) as string[])]
      : undefined,
  }
}
