import type { AgentStateView, PlanStepView, RunEvent, RunView } from '../workbench/types'

interface RunState {
  current: RunView | null
  events: RunEvent[]
  connected: boolean
  error: string
}

type Listener = (state: RunState) => void

function updatePlan(steps: PlanStepView[], event: RunEvent): PlanStepView[] {
  const objective = String(event.payload.objective || '')
  if (!objective) return steps
  const title = String(event.payload.objective_label || objective.replace(/_/g, ' '))
  const status = String(event.payload.status || (event.kind === 'run.failed' ? 'failed' : 'running'))
  const note = String(event.payload.message || '')
  const index = steps.findIndex(step => step.step_id === objective)
  const next = [...steps]
  const value: PlanStepView = {
    step_id: objective,
    title,
    status: (status === 'completed' || status === 'failed' || status === 'blocked' || status === 'running' ? status : 'pending') as PlanStepView['status'],
    agent_id: event.actor_id,
    note,
    updated_at: event.ts,
  }
  if (index === -1) next.push(value)
  else next[index] = { ...next[index], ...value }
  return next
}

function updateAgents(agents: AgentStateView[], event: RunEvent): AgentStateView[] {
  if (event.actor_type !== 'agent') return agents
  const index = agents.findIndex(agent => agent.agent_id === event.actor_id)
  const status = String(event.payload.status || 'running')
  const next = [...agents]
  const value: AgentStateView = {
    agent_id: event.actor_id,
    label: event.actor_id,
    status: (status === 'completed' || status === 'failed' || status === 'blocked' || status === 'running' ? status : 'idle') as AgentStateView['status'],
    current_task: String(event.payload.objective_label || event.payload.message || ''),
    last_update: event.ts,
  }
  if (index === -1) next.push(value)
  else next[index] = { ...next[index], ...value }
  return next
}

class RunStore {
  private state: RunState = {
    current: null,
    events: [],
    connected: false,
    error: '',
  }

  private listeners = new Set<Listener>()

  getState(): RunState { return this.state }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private patch(patch: Partial<RunState>): void {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach(listener => listener(this.state))
  }

  reset(): void {
    this.patch({ current: null, events: [], connected: false, error: '' })
  }

  async loadRun(runId: string): Promise<void> {
    const resp = await fetch(`/api/runs/${encodeURIComponent(runId)}`)
    if (!resp.ok) throw new Error(`Failed to load run ${runId}`)
    const current = await resp.json() as RunView
    this.patch({ current, events: [] })
  }

  setConnected(connected: boolean): void {
    const current = this.state.current
    this.patch({
      connected,
      current: current ? { ...current, connection_status: connected ? 'connected' : 'offline' } : current,
    })
  }

  applyEvent(event: RunEvent): void {
    const current = this.state.current
    if (current && current.run_id !== event.run_id) return
    if (this.state.events.some(existing => existing.event_id === event.event_id)) return

    const events = [...this.state.events, event].sort((a, b) => a.seq - b.seq)
    const baseCurrent = current || {
      run_id: event.run_id,
      session_id: event.session_id || '',
      status: 'running',
      phase: 'running',
      objective_text: String(event.payload.objective_label || event.payload.objective || event.run_id),
      phase_label: 'Running',
      plan_steps: [],
      agents: [],
      checkpoints: [],
      artifacts: [],
      recent_event: '',
      connection_status: this.state.connected ? 'connected' : 'offline',
      last_seq: 0,
    } as RunView

    let nextRun: RunView = {
      ...baseCurrent,
      last_seq: Math.max(baseCurrent.last_seq || 0, event.seq),
      recent_event: String(event.payload.message || baseCurrent.recent_event || ''),
      phase: event.phase as RunView['phase'],
      phase_label: event.phase.charAt(0).toUpperCase() + event.phase.slice(1),
    }

    if (event.kind === 'run.failed') nextRun.status = 'failed'
    else if (event.kind === 'run.completed') nextRun.status = 'completed'
    else if (event.kind === 'agent.activity') nextRun.status = String(event.payload.status || 'running') === 'blocked' ? 'blocked' : 'running'

    nextRun.plan_steps = updatePlan(baseCurrent.plan_steps || [], event)
    nextRun.agents = updateAgents(baseCurrent.agents || [], event)
    this.patch({ current: nextRun, events })
  }
}

export const runStore = new RunStore()
