/**
 * ExecutionTimelinePanel — Center panel overlay during mission execution.
 * Shows stage timeline, coverage bars, trust gauges, and active agent.
 * Mounts as an overlay on top of the canvas.
 */

import { missionStore, type WsEvent } from '../store/missionStore'
import { intakeStore } from '../store/intakeStore'

interface TimelineEntry {
  step: number
  objective: string
  agentRole: string
  status: 'pending' | 'active' | 'done' | 'failed'
  startedAt: string
  completedAt: string
  summary: string
  coverageDelta: Record<string, number>
  risks: string[]
}

const AGENT_ICONS: Record<string, string> = {
  'recon-agent':     '🔍',
  'transport-agent': '🔌',
  'reverse-agent':   '🔓',
  'runtime-agent':   '⚡',
  'schema-agent':    '📐',
  'builder-agent':   '🔨',
  'verifier-agent':  '✅',
  'critic-agent':    '🔬',
  'memory-agent':    '💾',
}

const COVERAGE_DIMS = ['acquisition','protocol','reverse','runtime','schema','extraction','build','verify']
const COVERAGE_LABELS: Record<string, string> = {
  acquisition: 'Acquire', protocol: 'Protocol', reverse: 'Reverse', runtime: 'Runtime',
  schema: 'Schema', extraction: 'Extract', build: 'Build', verify: 'Verify',
}

export class ExecutionTimelinePanel {
  private el: HTMLElement
  private timelineEntries: TimelineEntry[] = []
  private unsubMission: (() => void) | null = null

  constructor(el: HTMLElement) {
    this.el = el
    this.render()
    this.unsubMission = missionStore.subscribe((state) => {
      this.onMissionStateUpdate(state)
    })
  }

  private render(): void {
    this.el.innerHTML = `
      <div class="etp-root">
        <div class="etp-header">
          <span class="etp-title">⚡ EXECUTION TIMELINE</span>
          <span class="etp-step-badge" id="etp-step-badge">—</span>
        </div>
        <div class="etp-coverage-strip" id="etp-coverage-strip">
          ${COVERAGE_DIMS.map(d => `
            <div class="etp-cov-item">
              <div class="etp-cov-name">${COVERAGE_LABELS[d]}</div>
              <div class="etp-cov-bar-bg"><div class="etp-cov-bar-fill" id="etp-cov-${d}" style="width:0%"></div></div>
              <div class="etp-cov-pct" id="etp-covpct-${d}">0%</div>
            </div>
          `).join('')}
        </div>
        <div class="etp-trust-row" id="etp-trust-row">
          ${['Overall','Exec','Mech'].map((l,i) => `
            <div class="etp-trust-item">
              <span class="etp-trust-lbl">${l}</span>
              <div class="etp-trust-bar-bg"><div class="etp-trust-fill" id="etp-trust-${i}" style="width:0%"></div></div>
              <span class="etp-trust-pct" id="etp-trustpct-${i}">0%</span>
            </div>
          `).join('')}
        </div>
        <div class="etp-timeline" id="etp-timeline">
          <div class="etp-empty-hint">Waiting for execution to begin…</div>
        </div>
      </div>
    `
  }

  private onMissionStateUpdate(state: any): void {
    // Update step badge
    const badge = this.el.querySelector('#etp-step-badge') as HTMLElement
    if (badge && state.step) badge.textContent = `Step ${state.step}/${state.maxSteps}`

    // Update coverage bars
    const coverage = state.coverage || {}
    for (const dim of COVERAGE_DIMS) {
      const pct = Math.round((coverage[dim] || 0) * 100)
      const barEl = this.el.querySelector(`#etp-cov-${dim}`) as HTMLElement
      const pctEl = this.el.querySelector(`#etp-covpct-${dim}`) as HTMLElement
      if (barEl) {
        barEl.style.width = `${pct}%`
        barEl.style.background = pct >= 70 ? '#4cad6e' : pct >= 40 ? '#5b8dd9' : '#e0a030'
      }
      if (pctEl) pctEl.textContent = `${pct}%`
    }

    // Update trust gauges
    const trusts = [state.trustScore, state.executionTrustScore, state.mechanismTrustScore]
    trusts.forEach((t, i) => {
      const pct = Math.round((t || 0) * 100)
      const barEl = this.el.querySelector(`#etp-trust-${i}`) as HTMLElement
      const pctEl = this.el.querySelector(`#etp-trustpct-${i}`) as HTMLElement
      if (barEl) {
        barEl.style.width = `${pct}%`
        barEl.style.background = pct >= 80 ? '#4cad6e' : pct >= 50 ? '#5b8dd9' : '#e07b54'
      }
      if (pctEl) pctEl.textContent = `${pct}%`
    })

    // Update timeline entries from events
    this.syncTimelineFromEvents(state.events || [])
  }

  private syncTimelineFromEvents(events: WsEvent[]): void {
    const timelineEl = this.el.querySelector('#etp-timeline') as HTMLElement
    if (!timelineEl) return

    // Build timeline entries from dispatch/complete events
    const entriesByStep: Map<string, TimelineEntry> = new Map()

    for (const ev of events) {
      const objective = (ev as any).objective || ''
      const step = String((ev as any).step || objective || '')
      if (!step) continue

      if (ev.kind === 'dispatch') {
        if (!entriesByStep.has(step)) {
          entriesByStep.set(step, {
            step: parseInt(step) || 0,
            objective,
            agentRole: ev.agentRole || '',
            status: 'active',
            startedAt: ev.publishedAt || '',
            completedAt: '',
            summary: ev.message || '',
            coverageDelta: {},
            risks: [],
          })
        }
      } else if (ev.kind === 'complete' || ev.kind === 'error') {
        const entry = entriesByStep.get(step)
        if (entry) {
          entry.status = ev.kind === 'error' ? 'failed' : 'done'
          entry.completedAt = ev.publishedAt || ''
          entry.summary = ev.message || entry.summary
        }
      } else if (ev.kind === 'risk') {
        const lastEntry = [...entriesByStep.values()].pop()
        if (lastEntry) lastEntry.risks.push(ev.message || '')
      }
    }

    // Check if a final verdict event exists
    const verdictEvent = events.find(e => e.kind === 'verdict')

    if (entriesByStep.size === 0 && !verdictEvent) {
      timelineEl.innerHTML = '<div class="etp-empty-hint">Waiting for execution to begin…</div>'
      return
    }

    const entries = [...entriesByStep.values()].sort((a, b) => a.step - b.step)
    const html = entries.map(entry => this.renderEntry(entry)).join('')

    let verdictHtml = ''
    if (verdictEvent) {
      const tier = String((verdictEvent as any).tier || '').replace(/_/g, ' ').toUpperCase()
      const tierColors: Record<string, string> = {
        'MECHANISM SUCCESS': '#4cad6e', 'OPERATIONAL SUCCESS': '#5b8dd9',
        'STRUCTURAL SUCCESS': '#4cad6e', 'DATA SUCCESS': '#5b8dd9',
        'PARTIAL SUCCESS': '#e0a030', 'FAILED': '#d95555', 'EXECUTION SUCCESS': '#8a7e6e',
      }
      const color = tierColors[tier] || '#5b8dd9'
      verdictHtml = `
        <div class="etp-verdict-row" style="border-color:${color}">
          <span class="etp-verdict-icon">🏁</span>
          <div>
            <div class="etp-verdict-tier" style="color:${color}">${tier}</div>
            <div class="etp-verdict-msg">${escHtml(verdictEvent.message || '')}</div>
          </div>
        </div>
      `
    }

    timelineEl.innerHTML = html + verdictHtml
    // Auto-scroll to bottom
    timelineEl.scrollTop = timelineEl.scrollHeight
  }

  private renderEntry(entry: TimelineEntry): string {
    const icon = AGENT_ICONS[entry.agentRole] || '⚙'
    const statusIcon = entry.status === 'done' ? '✓' : entry.status === 'failed' ? '✗' : entry.status === 'active' ? '⟳' : '○'
    const statusClass = `etp-entry-${entry.status}`
    const riskHtml = entry.risks.length > 0
      ? `<div class="etp-entry-risk">⚠ ${escHtml(entry.risks[0])}</div>`
      : ''
    return `
      <div class="etp-entry ${statusClass}">
        <div class="etp-entry-status">${statusIcon}</div>
        <div class="etp-entry-body">
          <div class="etp-entry-header">
            <span class="etp-entry-icon">${icon}</span>
            <span class="etp-entry-obj">${escHtml(entry.objective.replace(/_/g, ' '))}</span>
            <span class="etp-entry-role">${escHtml(entry.agentRole)}</span>
          </div>
          <div class="etp-entry-summary">${escHtml(entry.summary)}</div>
          ${riskHtml}
        </div>
      </div>
    `
  }

  dispose(): void {
    if (this.unsubMission) this.unsubMission()
  }
}

function escHtml(str: string): string {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
