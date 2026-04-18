/**
 * Maps raw WsEvent (from missionStore / WebSocket) to AgentEvent.
 * Returns null if the event carries no meaningful right-panel update.
 *
 * WsEvent.kind discriminator values seen in production:
 *   dispatch | complete | info | verdict | reconciliation | risk
 */
import type { WsEvent } from '../store/missionStore'
import type { AgentEvent, PlanStepInit } from './types'

export function normalizeWsEvent(event: WsEvent): AgentEvent | null {
  const state = event.state ?? {}

  switch (event.kind) {

    case 'dispatch':
      if (event.agentRole) {
        return {
          type:   'step_started',
          stepId: event.agentRole,
          tool:   event.agentRole,
        }
      }
      return null

    case 'complete':
      if (event.agentRole) {
        return {
          type:    'step_completed',
          stepId:  event.agentRole,
          success: !(state as Record<string, unknown>).error,
        }
      }
      return null

    case 'verdict': {
      const outcome = String((state as Record<string, unknown>).missionOutcome
        ?? (state as Record<string, unknown>).mission_outcome
        ?? '')
      if (outcome === 'success') return { type: 'mission_complete' }
      if (outcome === 'failed' || outcome === 'failure') {
        return {
          type:   'mission_failed',
          reason: event.message || undefined,
        }
      }
      return { type: 'note', content: event.message || '裁定完成' }
    }

    case 'info':
      if (event.message) return { type: 'note', content: event.message }
      return null

    case 'risk':
      if (event.message) return { type: 'note', content: `⚠ ${event.message}` }
      return null

    case 'reconciliation':
      return null   // coverage snapshots — not surfaced in right panel

    default:
      return null
  }
}

// ── Helpers for backend-driven plan events ────────────────────────────────────
// If the backend ever sends a structured `plan` event, use these normalizers.

export function normalizePlanSteps(raw: unknown[]): PlanStepInit[] {
  return raw.map((s, i) => {
    const obj = s as Record<string, unknown>
    return {
      id:    String(obj.id   ?? `step-${i}`),
      title: String(obj.title ?? obj.name ?? `步骤 ${i + 1}`),
      tool:  obj.tool ? String(obj.tool) : undefined,
    }
  })
}
