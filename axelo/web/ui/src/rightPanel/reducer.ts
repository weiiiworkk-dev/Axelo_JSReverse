import type {
  RightPanelState, AgentEvent, PlanStep, ActionEvent, Checkpoint, DirtyCard,
} from './types'

// ── Helpers ───────────────────────────────────────────────────────────────────

let _counter = 0
function nextId(): string { return `evt-${++_counter}` }

function makeActionEvent(
  type: AgentEvent['type'],
  content: string,
  stepId?: string,
): ActionEvent {
  return { id: nextId(), type, timestamp: Date.now(), stepId, content }
}

// ── Initial state ─────────────────────────────────────────────────────────────

export function initialRightPanelState(): RightPanelState {
  return {
    taskStatus:   'idle',
    currentGoal:  null,
    planSteps:    [],
    actionEvents: [],
    checkpoints:  [],
  }
}

// ── Pure reducer ──────────────────────────────────────────────────────────────
//
// Returns the next state AND a set of dirty card slots.
// Callers use dirty to decide which DOM sections to re-render.

export function applyAgentEvent(
  state: RightPanelState,
  event: AgentEvent,
): { state: RightPanelState; dirty: DirtyCard[] } {

  switch (event.type) {

    case 'goal_set': {
      const ae = makeActionEvent('goal_set', event.description)
      return {
        state: {
          ...state,
          taskStatus:   'planning',
          currentGoal:  { description: event.description, url: event.url, setAt: Date.now() },
          actionEvents: [...state.actionEvents, ae],
        },
        dirty: ['goal', 'timeline'],
      }
    }

    case 'plan_created': {
      const steps: PlanStep[] = event.steps.map(s => ({
        id: s.id, title: s.title, status: 'pending', tool: s.tool,
      }))
      const ae = makeActionEvent('plan_created', `计划已生成，共 ${steps.length} 步`)
      return {
        state: {
          ...state,
          taskStatus:   'executing',
          planSteps:    steps,
          actionEvents: [...state.actionEvents, ae],
        },
        dirty: ['plan', 'timeline'],
      }
    }

    case 'step_started': {
      const steps = state.planSteps.map(s =>
        s.id === event.stepId
          ? { ...s, status: 'running' as const, startedAt: Date.now(), tool: event.tool ?? s.tool }
          : s
      )
      const label = steps.find(s => s.id === event.stepId)?.title ?? event.stepId
      const ae = makeActionEvent('step_started', `开始：${label}`, event.stepId)
      return {
        state: { ...state, planSteps: steps, actionEvents: [...state.actionEvents, ae] },
        dirty: ['plan', 'timeline'],
      }
    }

    case 'step_completed': {
      const steps = state.planSteps.map(s =>
        s.id === event.stepId
          ? {
              ...s,
              status:      event.success ? 'completed' as const : 'failed' as const,
              completedAt: Date.now(),
              note:        event.note,
            }
          : s
      )
      const label = steps.find(s => s.id === event.stepId)?.title ?? event.stepId
      const ae = makeActionEvent(
        'step_completed',
        `${event.success ? '完成' : '失败'}：${label}`,
        event.stepId,
      )
      return {
        state: { ...state, planSteps: steps, actionEvents: [...state.actionEvents, ae] },
        dirty: ['plan', 'timeline'],
      }
    }

    case 'tool_called': {
      const text = event.summary
        ? `${event.toolName}: ${event.summary}`
        : event.toolName
      const ae = makeActionEvent('tool_called', text, event.stepId)
      return {
        state: { ...state, actionEvents: [...state.actionEvents, ae] },
        dirty: ['timeline'],
      }
    }

    case 'checkpoint_waiting': {
      const cp: Checkpoint = {
        id: event.id, question: event.question, status: 'waiting', createdAt: Date.now(),
      }
      const ae = makeActionEvent('checkpoint_waiting', `需要确认：${event.question}`)
      return {
        state: {
          ...state,
          taskStatus:   'paused',
          checkpoints:  [...state.checkpoints, cp],
          actionEvents: [...state.actionEvents, ae],
        },
        dirty: ['checkpoint', 'timeline'],
      }
    }

    case 'checkpoint_resolved': {
      const checkpoints = state.checkpoints.map(cp =>
        cp.id === event.id
          ? { ...cp, status: event.approved ? 'approved' as const : 'rejected' as const }
          : cp
      )
      const ae = makeActionEvent(
        'checkpoint_resolved',
        event.approved ? '已批准' : '已拒绝',
      )
      return {
        state: {
          ...state,
          taskStatus:   'executing',
          checkpoints,
          actionEvents: [...state.actionEvents, ae],
        },
        dirty: ['checkpoint', 'timeline'],
      }
    }

    case 'note': {
      const ae = makeActionEvent('note', event.content)
      return {
        state: { ...state, actionEvents: [...state.actionEvents, ae] },
        dirty: ['timeline'],
      }
    }

    case 'mission_complete': {
      const ae = makeActionEvent('mission_complete', '任务已完成')
      return {
        state: {
          ...state,
          taskStatus:   'complete',
          actionEvents: [...state.actionEvents, ae],
        },
        dirty: ['goal', 'plan', 'timeline'],
      }
    }

    case 'mission_failed': {
      const ae = makeActionEvent(
        'mission_failed',
        `任务失败${event.reason ? '：' + event.reason : ''}`,
      )
      return {
        state: {
          ...state,
          taskStatus:   'failed',
          actionEvents: [...state.actionEvents, ae],
        },
        dirty: ['goal', 'plan', 'timeline'],
      }
    }

    default:
      return { state, dirty: [] }
  }
}
