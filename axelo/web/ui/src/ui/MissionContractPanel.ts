/**
 * MissionContractPanel — Left panel showing AI-generated mission contract.
 * Pre-execution: live-updating with delta animation.
 * Post-start: locked view.
 */

import { intakeStore, type MissionContract, type FieldSpec } from '../store/intakeStore'

export class MissionContractPanel {
  private el: HTMLElement
  private unsub: (() => void) | null = null
  private lastVersion = -1

  constructor(el: HTMLElement) {
    this.el = el
    this.renderEmpty()
    this.unsub = intakeStore.subscribe((state) => {
      if (state.contract) {
        this.renderContract(state.contract, state.lastContractDelta ?? undefined)
      } else {
        this.renderEmpty()
      }
    })
  }

  private renderEmpty(): void {
    this.el.innerHTML = `
      <div class="mcp-root">
        <div class="mcp-header">
          <div class="mcp-logo">⬛ AXELO</div>
          <div class="mcp-subtitle">Mission Contract</div>
        </div>
        <div class="mcp-placeholder">
          <div class="mcp-ph-icon">📋</div>
          <div class="mcp-ph-text">Start a conversation in the chat panel →<br>Your mission plan will appear here as AI understands your requirements.</div>
        </div>
      </div>
    `
  }

  private renderContract(contract: MissionContract, delta?: Partial<MissionContract>): void {
    const isLocked = Boolean(contract.locked_at)
    const conf = contract.readiness_assessment?.confidence ?? 0
    const pct = Math.round(conf * 100)
    const confColor = pct >= 75 ? '#4cad6e' : pct >= 50 ? '#e0a030' : '#d95555'
    const newVersion = contract.contract_version !== this.lastVersion
    this.lastVersion = contract.contract_version ?? 0

    const deltaKeys = delta ? Object.keys(delta) : []

    this.el.innerHTML = `
      <div class="mcp-root${isLocked ? ' mcp-locked' : ''}">
        <div class="mcp-header">
          <div>
            <div class="mcp-logo">⬛ AXELO</div>
            <div class="mcp-subtitle">Mission Contract${isLocked ? ' 🔒' : ''}</div>
          </div>
          <div class="mcp-version-badge">v${contract.contract_version}</div>
        </div>

        ${!isLocked ? `
        <div class="mcp-conf-row">
          <div class="mcp-conf-bar-bg">
            <div class="mcp-conf-bar-fill" style="width:${pct}%;background:${confColor}"></div>
          </div>
          <span class="mcp-conf-label" style="color:${confColor}">${pct}% ready</span>
        </div>
        ` : ''}

        ${contract.target_url ? `
        <div class="mcp-section${deltaKeys.includes('target_url') && newVersion ? ' mcp-delta' : ''}">
          <div class="mcp-section-title">🌐 TARGET</div>
          <div class="mcp-val mcp-url">${escHtml(contract.target_url)}</div>
          ${contract.target_scope?.mode ? `<div class="mcp-meta">Scope: ${contract.target_scope.mode}</div>` : ''}
          ${contract.auth_spec?.mechanism && contract.auth_spec.mechanism !== 'auto' ? `<div class="mcp-meta">Auth: ${contract.auth_spec.mechanism}${contract.auth_spec.login_required ? ' (login required)' : ''}</div>` : ''}
        </div>
        ` : `
        <div class="mcp-section mcp-empty-section">
          <div class="mcp-section-title">🌐 TARGET</div>
          <div class="mcp-empty-hint">No URL yet — mention a website in the chat</div>
        </div>
        `}

        ${contract.objective ? `
        <div class="mcp-section${deltaKeys.includes('objective') && newVersion ? ' mcp-delta' : ''}">
          <div class="mcp-section-title">🎯 OBJECTIVE</div>
          <div class="mcp-objective">${escHtml(contract.objective)}</div>
          ${contract.objective_type ? `<div class="mcp-badge mcp-badge-${contract.objective_type}">${contract.objective_type.replace('_', ' ')}</div>` : ''}
        </div>
        ` : ''}

        ${(contract.requested_fields ?? []).length > 0 ? `
        <div class="mcp-section${deltaKeys.includes('requested_fields') && newVersion ? ' mcp-delta' : ''}">
          <div class="mcp-section-title">📋 FIELDS (${(contract.requested_fields ?? []).length})</div>
          <div class="mcp-fields-list">
            ${(contract.requested_fields ?? []).map(f => renderFieldSpec(f)).join('')}
          </div>
        </div>
        ` : ''}

        ${(contract.item_limit ?? 0) > 0 ? `
        <div class="mcp-section${deltaKeys.includes('item_limit') && newVersion ? ' mcp-delta' : ''}">
          <div class="mcp-section-title">⚙ CONFIG</div>
          <div class="mcp-chips">
            <span class="mcp-chip">${contract.item_limit} items</span>
            ${contract.execution_spec?.stealth_level ? `<span class="mcp-chip">${contract.execution_spec.stealth_level} stealth</span>` : ''}
            ${contract.execution_spec?.js_rendering ? `<span class="mcp-chip">JS: ${contract.execution_spec.js_rendering}</span>` : ''}
          </div>
        </div>
        ` : ''}

        ${(contract.assumptions ?? []).length > 0 ? `
        <div class="mcp-section">
          <div class="mcp-section-title">💡 ASSUMPTIONS</div>
          ${(contract.assumptions ?? []).map(a => `<div class="mcp-assumption">• ${escHtml(a)}</div>`).join('')}
        </div>
        ` : ''}

        ${(contract.readiness_assessment?.blocking_gaps ?? []).length > 0 ? `
        <div class="mcp-section mcp-section-warn">
          <div class="mcp-section-title">⚠ STILL NEEDED</div>
          ${(contract.readiness_assessment?.blocking_gaps ?? []).map(g => `<div class="mcp-gap">• ${escHtml(g)}</div>`).join('')}
        </div>
        ` : ''}

        ${isLocked ? `
        <div class="mcp-locked-banner">🔒 Contract locked — mission executing</div>
        ` : ''}
      </div>
    `
  }

  dispose(): void {
    if (this.unsub) this.unsub()
  }
}

function renderFieldSpec(f: FieldSpec): string {
  const typeColor = { string: '#5b8dd9', number: '#4cad6e', boolean: '#e0a030', array: '#e07b54', object: '#9b59b6' }
  const color = (typeColor as any)[f.data_type ?? ''] || '#8a7e6e'
  return `
    <div class="mcp-field-row">
      <span class="mcp-field-name">${escHtml(f.field_name ?? '')}</span>
      <span class="mcp-field-type" style="color:${color}">${f.data_type}</span>
      ${f.priority === 1 ? '<span class="mcp-field-req">must</span>' : '<span class="mcp-field-opt">opt</span>'}
    </div>
  `
}

function escHtml(str: string): string {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
