/**
 * RightPanelController — state-driven, partial DOM update controller.
 *
 * Responsibilities:
 *  - Mount four card slots into a container element
 *  - Re-render only the slots marked dirty by the reducer
 *  - Apply entering / pulse / latest CSS animation classes surgically
 *  - PlanCard: surgical per-step status patches (no full re-render on status change)
 *  - ActionTimeline: append-only DOM growth (no re-render on new events)
 *  - Wire up checkpoint approve/reject button clicks
 */

import { rightPanelStore } from './store'
import type { RightPanelState, DirtyCard, StepStatus, ActionEvent } from './types'
import { renderGoalCard }        from './render/goalCard'
import { renderPlanCard }        from './render/planCard'
import { renderActionTimeline }  from './render/actionTimeline'
import { renderCheckpointCard }  from './render/checkpointCard'
import { esc, fmtTime }          from './render/utils'

const STEP_ICON: Record<StepStatus, string> = {
  pending:   '○',
  running:   '◉',
  completed: '✓',
  failed:    '✗',
  skipped:   '–',
}

const TL_ICON: Record<string, string> = {
  goal_set: '◎', plan_created: '▦', step_started: '▶', step_completed: '✓',
  tool_called: '⚙', checkpoint_waiting: '⏸', checkpoint_resolved: '▶',
  note: '·', mission_complete: '★', mission_failed: '✗',
}

const TIMELINE_MAX = 40

export class RightPanelController {
  private container:  HTMLElement
  private prevState:  RightPanelState | null = null
  private unsub:      (() => void) | null = null

  constructor(container: HTMLElement) {
    this.container = container
    this._mount()
    this.unsub = rightPanelStore.subscribe((state, dirty) => {
      this._update(state, dirty)
    })
  }

  // ── Mount ────────────────────────────────────────────────────────────────────

  private _mount(): void {
    this.container.innerHTML = `
      <div id="rp-slot-goal"></div>
      <div id="rp-slot-checkpoint"></div>
      <div id="rp-slot-plan"></div>
      <div id="rp-slot-timeline"></div>
    `
    this.container.addEventListener('click', this._onClick.bind(this))

    const state = rightPanelStore.getState()
    this._setSlotRaw('rp-slot-goal',       renderGoalCard(state))
    this._setSlotRaw('rp-slot-plan',       renderPlanCard(state))
    this._setSlotRaw('rp-slot-checkpoint', renderCheckpointCard(state))
    this._setSlotRaw('rp-slot-timeline',   renderActionTimeline(state))
    this.prevState = state
  }

  // ── Dispatch update ──────────────────────────────────────────────────────────

  private _update(state: RightPanelState, dirty: DirtyCard[]): void {
    if (dirty.includes('goal'))       this._updateGoal(state)
    if (dirty.includes('checkpoint')) this._updateCheckpoint(state)
    if (dirty.includes('plan'))       this._updatePlan(state)
    if (dirty.includes('timeline'))   this._appendTimeline(state)
    this.prevState = state
  }

  // ── Goal card ────────────────────────────────────────────────────────────────

  private _updateGoal(state: RightPanelState): void {
    this._animateSlot('rp-slot-goal', renderGoalCard(state))
  }

  // ── Checkpoint card ──────────────────────────────────────────────────────────

  private _updateCheckpoint(state: RightPanelState): void {
    this._animateSlot('rp-slot-checkpoint', renderCheckpointCard(state))
  }

  // ── Plan card — surgical step updates ─────────────────────────────────────

  private _updatePlan(state: RightPanelState): void {
    const prev = this.prevState
    const planCard = document.getElementById('plan-card')

    // Full render: no existing card, or plan was empty before
    if (!prev || prev.planSteps.length === 0 || !planCard) {
      this._animateSlot('rp-slot-plan', renderPlanCard(state))
      return
    }

    const stepsList = document.getElementById('rp-steps-list')
    let hasChanges = false

    for (const step of state.planSteps) {
      const prev = this.prevState?.planSteps.find(s => s.id === step.id)

      if (!prev) {
        // New step: append a new element
        if (stepsList) {
          const el = document.createElement('div')
          el.className = `rp-step rp-step--${step.status} entering`
          el.dataset.stepId = step.id
          el.innerHTML = `
            <span class="rp-step__icon" aria-hidden="true">${STEP_ICON[step.status]}</span>
            <div class="rp-step__body">
              <span class="rp-step__title">${esc(step.title)}</span>
              ${step.tool ? `<span class="rp-step__tool">${esc(step.tool)}</span>` : ''}
            </div>
          `
          stepsList.appendChild(el)
          requestAnimationFrame(() => { setTimeout(() => el.classList.remove('entering'), 400) })
        }
        hasChanges = true

      } else if (prev.status !== step.status) {
        // Status change: patch existing element in-place
        const stepEl = planCard.querySelector(`[data-step-id="${step.id}"]`)
        if (stepEl) {
          stepEl.classList.remove(`rp-step--${prev.status}`)
          stepEl.classList.add(`rp-step--${step.status}`, 'pulse')
          setTimeout(() => stepEl.classList.remove('pulse'), 600)

          const iconEl = stepEl.querySelector('.rp-step__icon')
          if (iconEl) iconEl.textContent = STEP_ICON[step.status]

          if (step.note) {
            const body = stepEl.querySelector('.rp-step__body')
            if (body && !body.querySelector('.rp-step__note')) {
              const noteEl = document.createElement('span')
              noteEl.className = 'rp-step__note'
              noteEl.textContent = step.note
              body.appendChild(noteEl)
            }
          }
        }
        hasChanges = true
      }
    }

    // Update progress bar & counter
    if (hasChanges) {
      const completed = state.planSteps.filter(s => s.status === 'completed').length
      const pct = Math.round((completed / state.planSteps.length) * 100)

      const fill = planCard.querySelector('.rp-progress__fill') as HTMLElement | null
      if (fill) fill.style.width = `${pct}%`

      const meta = planCard.querySelector('.rp-card__meta')
      if (meta) meta.textContent = `${completed} / ${state.planSteps.length}`

      const bar = planCard.querySelector('.rp-progress') as HTMLElement | null
      if (bar) bar.setAttribute('aria-valuenow', String(pct))
    }
  }

  // ── Action timeline — append-only ────────────────────────────────────────────

  private _appendTimeline(state: RightPanelState): void {
    const prevCount = this.prevState?.actionEvents.length ?? 0
    const newEvents = state.actionEvents.slice(prevCount)
    if (newEvents.length === 0) return

    // If no timeline card yet, do a full render
    const list = document.getElementById('rp-timeline-list')
    if (!list) {
      this._animateSlot('rp-slot-timeline', renderActionTimeline(state))
      return
    }

    // Update count badge
    const meta = document.querySelector('#timeline-card .rp-card__meta')
    if (meta) meta.textContent = String(state.actionEvents.length)

    // Remove --latest marker from previous tail
    list.querySelector('.rp-tl-entry--latest')?.classList.remove('rp-tl-entry--latest')

    // Append each new event
    for (const event of newEvents) {
      const el = this._buildTimelineEntry(event, false)
      list.appendChild(el)

      // Trim leading entries
      while (list.children.length > TIMELINE_MAX) {
        list.removeChild(list.firstElementChild!)
      }
    }

    // Mark the new tail entry as latest
    const last = list.lastElementChild
    if (last) {
      last.classList.add('rp-tl-entry--latest')
      // Scroll to bottom after DOM paint
      requestAnimationFrame(() => { list.scrollTop = list.scrollHeight })
    }
  }

  private _buildTimelineEntry(event: ActionEvent, isLatest: boolean): HTMLElement {
    const el = document.createElement('div')
    el.className = [
      'rp-tl-entry',
      `rp-tl-entry--${event.type}`,
      'entering',
      isLatest ? 'rp-tl-entry--latest' : '',
    ].filter(Boolean).join(' ')
    el.dataset.evtId = event.id

    el.innerHTML = `
      <span class="rp-tl-icon" aria-hidden="true">${TL_ICON[event.type] ?? '·'}</span>
      <div class="rp-tl-body">
        <span class="rp-tl-content">${esc(event.content)}</span>
        <span class="rp-tl-time">${fmtTime(event.timestamp)}</span>
      </div>
    `

    requestAnimationFrame(() => { setTimeout(() => el.classList.remove('entering'), 50) })
    return el
  }

  // ── Slot helpers ─────────────────────────────────────────────────────────────

  private _setSlotRaw(id: string, html: string): void {
    const el = document.getElementById(id)
    if (el) el.innerHTML = html
  }

  private _animateSlot(id: string, html: string): void {
    const slot = document.getElementById(id)
    if (!slot) return
    slot.innerHTML = html
    const card = slot.firstElementChild as HTMLElement | null
    if (card) {
      card.classList.add('entering')
      requestAnimationFrame(() => { setTimeout(() => card.classList.remove('entering'), 400) })
    }
  }

  // ── Event delegation ─────────────────────────────────────────────────────────

  private _onClick(e: Event): void {
    const btn = (e.target as HTMLElement).closest<HTMLElement>('[data-cp-id]')
    if (!btn) return

    const cpId    = btn.dataset.cpId
    const approve = btn.dataset.approve === 'true'
    if (!cpId) return

    // Optimistic local state update
    rightPanelStore.dispatch({ type: 'checkpoint_resolved', id: cpId, approved: approve })

    // Relay to backend (best-effort)
    void fetch('/api/checkpoints/resolve', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ id: cpId, approved: approve }),
    }).catch(() => { /* backend may not have this endpoint yet */ })
  }

  // ── Lifecycle ────────────────────────────────────────────────────────────────

  dispose(): void {
    this.unsub?.()
    this.container.innerHTML = ''
    this.prevState = null
  }
}
