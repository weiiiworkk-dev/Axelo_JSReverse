import type { RightPanelState, PlanStep, StepStatus } from '../types'
import { esc } from './utils'

const STEP_ICON: Record<StepStatus, string> = {
  pending:   '○',
  running:   '◉',
  completed: '✓',
  failed:    '✗',
  skipped:   '–',
}

export function renderPlanCard(state: RightPanelState): string {
  const { planSteps } = state

  if (planSteps.length === 0) {
    return `<div class="rp-card rp-card--empty" id="plan-card">
      <span class="rp-card__empty-icon">▦</span>
      <p class="rp-card__empty-label">执行计划<br>将在任务开始时生成</p>
    </div>`
  }

  const completed = planSteps.filter(s => s.status === 'completed').length
  const pct = Math.round((completed / planSteps.length) * 100)

  return `<div class="rp-card rp-card--plan" id="plan-card">
    <div class="rp-card__header">
      <span class="rp-card__title">执行计划</span>
      <span class="rp-card__meta">${completed} / ${planSteps.length}</span>
    </div>
    <div class="rp-progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
      <div class="rp-progress__fill" style="width:${pct}%"></div>
    </div>
    <div class="rp-steps" id="rp-steps-list">
      ${planSteps.map(renderStep).join('')}
    </div>
  </div>`
}

export function renderStep(step: PlanStep): string {
  const icon = STEP_ICON[step.status]
  const toolHtml = step.tool
    ? `<span class="rp-step__tool">${esc(step.tool)}</span>`
    : ''
  const noteHtml = step.note
    ? `<span class="rp-step__note">${esc(step.note)}</span>`
    : ''

  return `<div class="rp-step rp-step--${step.status}" data-step-id="${esc(step.id)}">
    <span class="rp-step__icon" aria-hidden="true">${icon}</span>
    <div class="rp-step__body">
      <span class="rp-step__title">${esc(step.title)}</span>
      ${toolHtml}${noteHtml}
    </div>
  </div>`
}
