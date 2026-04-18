import type { RightPanelState } from '../types'
import { esc, truncate } from './utils'

const STATUS_LABEL: Record<string, string> = {
  idle:      '',
  planning:  '规划中',
  executing: '执行中',
  paused:    '等待确认',
  complete:  '已完成',
  failed:    '失败',
}

export function renderGoalCard(state: RightPanelState): string {
  const { currentGoal, taskStatus } = state

  if (!currentGoal) {
    return `<div class="rp-card rp-card--empty" id="goal-card">
      <span class="rp-card__empty-icon">◎</span>
      <p class="rp-card__empty-label">等待任务目标</p>
    </div>`
  }

  const label = STATUS_LABEL[taskStatus] ?? ''
  const badge = label
    ? `<span class="rp-badge rp-badge--${taskStatus}">${label}</span>`
    : ''

  const urlRow = currentGoal.url
    ? `<div class="rp-goal__url" title="${esc(currentGoal.url)}">
         <span class="rp-goal__url-icon">🔗</span>
         <span class="rp-goal__url-text">${esc(truncate(currentGoal.url, 45))}</span>
       </div>`
    : ''

  return `<div class="rp-card rp-card--goal rp-card--${taskStatus}" id="goal-card">
    <div class="rp-card__header">
      <span class="rp-card__title">任务目标</span>
      ${badge}
    </div>
    <p class="rp-goal__desc">${esc(currentGoal.description)}</p>
    ${urlRow}
  </div>`
}
