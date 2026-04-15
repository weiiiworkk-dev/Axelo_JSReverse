/**
 * Intake store — manages pre-execution requirement discussion state.
 * Separate from missionStore (which tracks execution state).
 *
 * Model interfaces are auto-generated from axelo/models/contracts.py.
 * To regenerate: python scripts/gen_ts_contracts.py
 */

export type IntakePhase = 'welcome' | 'discussing' | 'contract_ready' | 'executing' | 'complete' | 'failed'

// Auto-generated from axelo/models/contracts.py — import into local scope and re-export for consumers
import type {
  AuthSpec,
  ExecutionSpec,
  FieldEvidence,
  FieldSpec,
  MissionContract,
  OutputSpec,
  ReadinessAssessment,
  ScopeDefinition,
} from '../generated/contracts'

export type {
  AuthSpec,
  ExecutionSpec,
  FieldEvidence,
  FieldSpec,
  MissionContract,
  OutputSpec,
  ReadinessAssessment,
  ScopeDefinition,
}

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
  turn_id: string
  ts: string
  annotation_type?: string
}

export interface IntakeState {
  intakeId: string
  phase: IntakePhase
  contract: MissionContract | null
  chatHistory: ChatTurn[]
  readiness: ReadinessAssessment | null
  isWaitingForAI: boolean
  lastContractDelta: Partial<MissionContract> | null
  sessionId: string   // populated after Start
  error: string
}

type Listener = (state: IntakeState) => void

const EMPTY_READINESS: ReadinessAssessment = {
  confidence: 0,
  is_ready: false,
  missing_info: [],
  blocking_gaps: [],
  suggestions: [],
  assessed_at: '',
}

function makeInitialState(): IntakeState {
  return {
    intakeId: '',
    phase: 'welcome',
    contract: null,
    chatHistory: [],
    readiness: EMPTY_READINESS,
    isWaitingForAI: false,
    lastContractDelta: null,
    sessionId: '',
    error: '',
  }
}

class IntakeStore {
  private state: IntakeState = makeInitialState()
  private listeners: Set<Listener> = new Set()

  getState(): IntakeState { return this.state }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private notify(): void {
    for (const fn of this.listeners) fn(this.state)
  }

  private patch(update: Partial<IntakeState>): void {
    this.state = { ...this.state, ...update }
    this.notify()
  }

  setIntakeId(intakeId: string): void { this.patch({ intakeId }) }
  setPhase(phase: IntakePhase): void { this.patch({ phase }) }
  setWaiting(isWaitingForAI: boolean): void { this.patch({ isWaitingForAI }) }
  setError(error: string): void { this.patch({ error }) }

  setContract(contract: MissionContract, delta?: Partial<MissionContract>): void {
    const readiness = contract.readiness_assessment || EMPTY_READINESS
    this.patch({ contract, readiness, lastContractDelta: delta || null })
  }

  appendUserMessage(content: string, turnId: string): void {
    const turn: ChatTurn = { role: 'user', content, turn_id: turnId, ts: new Date().toISOString() }
    this.patch({ chatHistory: [...this.state.chatHistory, turn] })
  }

  appendAssistantMessage(content: string, turnId: string): void {
    const turn: ChatTurn = { role: 'assistant', content, turn_id: turnId, ts: new Date().toISOString() }
    this.patch({ chatHistory: [...this.state.chatHistory, turn] })
  }

  setExecuting(sessionId: string): void {
    this.patch({ phase: 'executing', sessionId })
  }

  reset(): void {
    this.state = makeInitialState()
    this.notify()
  }
}

export const intakeStore = new IntakeStore()

// ── API helpers ─────────────────────────────────────────────────────────────

export async function createIntakeSession(): Promise<string> {
  const resp = await fetch('/api/intake/session', { method: 'POST' })
  if (!resp.ok) throw new Error(`Failed to create intake session: ${resp.status}`)
  const data = await resp.json()
  return data.intake_id as string
}

export async function sendIntakeMessage(
  intakeId: string,
  message: string,
): Promise<{ ai_reply: string; contract: MissionContract; readiness: ReadinessAssessment; phase: string; contract_delta: Partial<MissionContract>; turn_id: string }> {
  const resp = await fetch(`/api/intake/${intakeId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, role: 'user' }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(String(err.detail || resp.statusText))
  }
  return resp.json()
}

export async function startMissionFromContract(
  intakeId: string,
): Promise<{ session_id: string; intake_id: string; phase: string; effective_goal: string }> {
  const resp = await fetch(`/api/intake/${intakeId}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(String(err.detail || resp.statusText))
  }
  return resp.json()
}

export async function sendAnnotation(
  intakeId: string,
  message: string,
  annotationType = 'note',
): Promise<void> {
  await fetch(`/api/intake/${intakeId}/annotate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, annotation_type: annotationType }),
  })
}
