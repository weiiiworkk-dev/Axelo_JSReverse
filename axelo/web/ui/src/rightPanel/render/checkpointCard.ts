import type { RightPanelState, Checkpoint } from '../types'
import { esc } from './utils'

export function renderCheckpointCard(state: RightPanelState): string {
  const waiting = state.checkpoints.filter(cp => cp.status === 'waiting')
  if (waiting.length === 0) return ''

  return `<div class="rp-card rp-card--checkpoint" id="checkpoint-card">
    <div class="rp-card__header">
      <span class="rp-card__title">⏸ 需要确认</span>
      <span class="rp-badge rp-badge--paused">${waiting.length}</span>
    </div>
    <div class="rp-checkpoints">
      ${waiting.map(renderCheckpoint).join('')}
    </div>
  </div>`
}

function renderCheckpoint(cp: Checkpoint): string {
  return `<div class="rp-checkpoint" data-cp-id="${esc(cp.id)}">
    <p class="rp-checkpoint__q">${esc(cp.question)}</p>
    <div class="rp-checkpoint__actions">
      <button class="rp-btn rp-btn--approve"
              data-cp-id="${esc(cp.id)}"
              data-approve="true"
              type="button">批准</button>
      <button class="rp-btn rp-btn--reject"
              data-cp-id="${esc(cp.id)}"
              data-approve="false"
              type="button">拒绝</button>
    </div>
  </div>`
}
