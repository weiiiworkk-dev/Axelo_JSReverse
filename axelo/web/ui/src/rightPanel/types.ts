// ── Domain types ─────────────────────────────────────────────────────────────

export type TaskStatus = 'idle' | 'planning' | 'executing' | 'paused' | 'complete' | 'failed'
export type StepStatus  = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
export type CheckpointStatus = 'waiting' | 'approved' | 'rejected'
export type DirtyCard   = 'goal' | 'plan' | 'timeline' | 'checkpoint'

// ── Agent event union (input from WebSocket / intakeStore) ────────────────────

export type AgentEvent =
  | { type: 'goal_set';            description: string; url?: string }
  | { type: 'plan_created';        steps: PlanStepInit[] }
  | { type: 'step_started';        stepId: string; tool?: string }
  | { type: 'step_completed';      stepId: string; success: boolean; note?: string }
  | { type: 'tool_called';         stepId?: string; toolName: string; summary?: string }
  | { type: 'checkpoint_waiting';  id: string; question: string }
  | { type: 'checkpoint_resolved'; id: string; approved: boolean }
  | { type: 'note';                content: string }
  | { type: 'mission_complete' }
  | { type: 'mission_failed';      reason?: string }

export interface PlanStepInit {
  id: string
  title: string
  tool?: string
}

// ── State shapes ──────────────────────────────────────────────────────────────

export interface Goal {
  description: string
  url?: string
  setAt: number
}

export interface PlanStep {
  id: string
  title: string
  status: StepStatus
  tool?: string
  startedAt?: number
  completedAt?: number
  note?: string
}

export interface ActionEvent {
  id: string
  type: AgentEvent['type']
  timestamp: number
  stepId?: string
  content: string
}

export interface Checkpoint {
  id: string
  question: string
  status: CheckpointStatus
  createdAt: number
}

export interface RightPanelState {
  taskStatus: TaskStatus
  currentGoal: Goal | null
  planSteps: PlanStep[]
  actionEvents: ActionEvent[]
  checkpoints: Checkpoint[]
}
