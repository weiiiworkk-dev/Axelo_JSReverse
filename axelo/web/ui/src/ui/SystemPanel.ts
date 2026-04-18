import { runStore } from '../store/runStore'

export class SystemPanel {
  private readonly el: HTMLElement
  private readonly unsub: () => void

  constructor(el: HTMLElement) {
    this.el = el
    this.unsub = runStore.subscribe(() => this.render())
    this.render()
  }

  private render(): void {
    const state = runStore.getState()
    const run = state.current
    const plan = run?.plan_steps || []
    const agents = run?.agents || []
    const checkpoints = run?.checkpoints || []

    this.el.innerHTML = `
      <div class="system-shell">
        ${renderSection('Current Objective', run ? `
          <div class="sys-objective">${esc(run.objective_text || 'No active objective yet')}</div>
          <div class="sys-inline-meta">
            <span>${esc(run.phase_label || 'Idle')}</span>
            <span>${esc(run.status || 'idle')}</span>
          </div>
        ` : emptyState('The current run objective will stay pinned here once execution starts.'))}

        ${renderSection('Run Plan', plan.length > 0 ? `
          <div class="sys-list">
            ${plan.map(step => `
              <div class="sys-step sys-step-${step.status}">
                <span class="sys-step-dot"></span>
                <div>
                  <div class="sys-step-title">${esc(step.title)}</div>
                  ${step.note ? `<div class="sys-step-note">${esc(step.note)}</div>` : ''}
                </div>
              </div>
            `).join('')}
          </div>
        ` : emptyState('Planned steps will appear here as the router turns the request into a run graph.'))}

        ${renderSection('Active Agents', agents.length > 0 ? `
          <div class="sys-list">
            ${agents.map(agent => `
              <div class="sys-agent">
                <div class="sys-agent-head">
                  <span>${esc(agent.label)}</span>
                  <span class="sys-agent-status">${esc(agent.status)}</span>
                </div>
                <div class="sys-agent-task">${esc(agent.current_task || 'Waiting')}</div>
              </div>
            `).join('')}
          </div>
        ` : emptyState('Agent activity is quiet until the run is active.'))}

        ${renderSection('Checkpoints', checkpoints.length > 0 ? `
          <div class="sys-list">
            ${checkpoints.map(checkpoint => `
              <div class="sys-checkpoint">
                <div class="sys-agent-head">
                  <span>${esc(checkpoint.question)}</span>
                  <span class="sys-agent-status">${esc(checkpoint.status)}</span>
                </div>
              </div>
            `).join('')}
          </div>
        ` : emptyState('User decisions and approval gates will surface here when the run pauses.'))}

        ${renderSection('Run Status', run ? `
          <div class="sys-metrics">
            <div><span>Session</span><strong>${esc(run.session_id || '-')}</strong></div>
            <div><span>Run</span><strong>${esc(run.run_id)}</strong></div>
            <div><span>Phase</span><strong>${esc(run.phase)}</strong></div>
            <div><span>Recent</span><strong>${esc(run.recent_event || 'Waiting')}</strong></div>
            <div><span>Artifacts</span><strong>${run.artifacts.length}</strong></div>
            <div><span>Connection</span><strong>${state.connected ? 'Connected' : 'Offline'}</strong></div>
          </div>
          <details class="sys-dev">
            <summary>Dev details</summary>
            <div class="sys-dev-grid">
              <div><span>Last seq</span><strong>${run.last_seq}</strong></div>
              <div><span>Events</span><strong>${state.events.length}</strong></div>
            </div>
          </details>
        ` : emptyState('Once a run is live, system status and artifacts will stay visible here.'))}
      </div>
    `
  }

  dispose(): void {
    this.unsub()
    this.el.innerHTML = ''
  }
}

function renderSection(title: string, body: string): string {
  return `
    <section class="sys-section">
      <div class="sys-section-title">${title}</div>
      <div class="sys-section-body">${body}</div>
    </section>
  `
}

function emptyState(text: string): string {
  return `<div class="sys-empty">${esc(text)}</div>`
}

function esc(value: string): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
