export type ThreadItemKind =
  | 'user_message'
  | 'router_message'
  | 'agent_activity_block'
  | 'deliverable_block'
  | 'checkpoint_message'
  | 'system_notice'

export interface ChatThreadItem {
  item_id: string
  session_id: string
  run_id?: string
  kind: ThreadItemKind
  created_at: string
  actor_type: 'user' | 'router' | 'agent' | 'system'
  actor_id: string
  title?: string
  content?: string
  status?: string
  meta?: Record<string, any>
}

export interface SessionSummary {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  status: string
  latest_run_id?: string
  latest_run_status?: string
  is_legacy?: boolean
}

export interface SessionView extends SessionSummary {
  intake_id?: string
  current_run_id?: string
  run_ids?: string[]
  ready_to_run?: boolean
  thread_items?: ChatThreadItem[]
}

export interface RunEvent {
  event_id: string
  session_id?: string
  run_id: string
  seq: number
  ts: string
  kind: string
  actor_type: 'user' | 'router' | 'agent' | 'system'
  actor_id: string
  phase: string
  payload: Record<string, any>
}

export interface PlanStepView {
  step_id: string
  title: string
  status: 'pending' | 'running' | 'completed' | 'blocked' | 'failed' | 'skipped'
  agent_id?: string
  note?: string
  updated_at?: string
}

export interface AgentStateView {
  agent_id: string
  label: string
  status: 'idle' | 'running' | 'blocked' | 'failed' | 'completed'
  current_task?: string
  last_update?: string
}

export interface ArtifactRef {
  artifact_id: string
  run_id: string
  title: string
  artifact_type: string
  status: string
  uri: string
  summary?: string
}

export interface CheckpointRecord {
  checkpoint_id: string
  run_id: string
  question: string
  status: 'waiting' | 'approved' | 'rejected' | 'expired'
  created_at: string
  resolved_at?: string
  resolution?: string
}

export interface RunView {
  run_id: string
  session_id?: string
  status: 'idle' | 'running' | 'blocked' | 'failed' | 'completed'
  phase: 'intake' | 'planning' | 'running' | 'blocked' | 'completed' | 'failed'
  objective_text: string
  phase_label: string
  plan_steps: PlanStepView[]
  agents: AgentStateView[]
  checkpoints: CheckpointRecord[]
  artifacts: ArtifactRef[]
  recent_event: string
  connection_status: string
  last_seq: number
}
