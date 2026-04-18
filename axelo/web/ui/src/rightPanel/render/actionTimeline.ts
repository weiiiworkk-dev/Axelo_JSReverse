import type { RightPanelState, ActionEvent } from '../types'
import { esc, fmtTime } from './utils'

const EVENT_ICON: Record<string, string> = {
  goal_set:             '◎',
  plan_created:         '▦',
  step_started:         '▶',
  step_completed:       '✓',
  tool_called:          '⚙',
  checkpoint_waiting:   '⏸',
  checkpoint_resolved:  '▶',
  note:                 '·',
  mission_complete:     '★',
  mission_failed:       '✗',
}

const VISIBLE_MAX = 40

export function renderActionTimeline(state: RightPanelState): string {
  const { actionEvents } = state

  if (actionEvents.length === 0) {
    return `<div class="rp-card rp-card--empty rp-card--timeline" id="timeline-card">
      <span class="rp-card__empty-icon">≡</span>
      <p class="rp-card__empty-label">暂无事件</p>
    </div>`
  }

  const visible = actionEvents.slice(-VISIBLE_MAX)

  return `<div class="rp-card rp-card--timeline" id="timeline-card">
    <div class="rp-card__header">
      <span class="rp-card__title">事件流</span>
      <span class="rp-card__meta">${actionEvents.length}</span>
    </div>
    <div class="rp-timeline" id="rp-timeline-list">
      ${visible.map((e, i) => renderEntry(e, i === visible.length - 1)).join('')}
    </div>
  </div>`
}

export function renderEntry(event: ActionEvent, isLatest: boolean): string {
  const icon   = EVENT_ICON[event.type] ?? '·'
  const latest = isLatest ? ' rp-tl-entry--latest' : ''

  return `<div class="rp-tl-entry rp-tl-entry--${event.type}${latest}" data-evt-id="${esc(event.id)}">
    <span class="rp-tl-icon" aria-hidden="true">${icon}</span>
    <div class="rp-tl-body">
      <span class="rp-tl-content">${esc(event.content)}</span>
      <span class="rp-tl-time">${fmtTime(event.timestamp)}</span>
    </div>
  </div>`
}
