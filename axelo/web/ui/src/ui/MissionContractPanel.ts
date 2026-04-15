/**
 * MissionContractPanel — 左侧任务合约面板，终端风格展示。
 * 预执行阶段：实时更新并显示 delta 动画。
 * 执行后：锁定视图。
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
          <div>
            <div class="mcp-logo">AXELO</div>
            <div class="mcp-subtitle">Mission Contract</div>
          </div>
          <div class="mcp-version-badge">v0</div>
        </div>
        <div class="mcp-placeholder">
          <div class="mcp-ph-icon">📋</div>
          <div class="mcp-ph-text">
            在右侧对话栏描述你的目标<br>
            任务计划将在此实时生成
          </div>
        </div>
      </div>
    `
  }

  private renderContract(contract: MissionContract, delta?: Partial<MissionContract>): void {
    const isLocked = Boolean(contract.locked_at)
    const conf = contract.readiness_assessment?.confidence ?? 0
    const pct = Math.round(conf * 100)
    const confColor = pct >= 75 ? 'var(--success)' : pct >= 50 ? 'var(--warn)' : 'var(--danger)'
    const newVersion = contract.contract_version !== this.lastVersion
    this.lastVersion = contract.contract_version ?? 0

    const deltaKeys = delta ? Object.keys(delta) : []

    // 终端风格进度条
    const barLen = 20
    const filled = Math.round(pct / 100 * barLen)
    const empty = barLen - filled
    const barStr = '█'.repeat(filled) + '░'.repeat(empty)

    // 就绪状态行
    const isReady = contract.readiness_assessment?.is_ready ?? false
    const blockingGaps = contract.readiness_assessment?.blocking_gaps ?? []

    this.el.innerHTML = `
      <div class="mcp-root${isLocked ? ' mcp-locked' : ''}">
        <div class="mcp-header">
          <div>
            <div class="mcp-logo">AXELO</div>
            <div class="mcp-subtitle">Mission Contract${isLocked ? ' [锁定]' : ''}</div>
          </div>
          <div class="mcp-version-badge">v${contract.contract_version ?? 0}</div>
        </div>

        ${!isLocked ? `
        <div class="mcp-conf-row">
          <div class="mcp-conf-bar-bg">
            <div class="mcp-conf-bar-fill" style="width:${pct}%;background:${confColor}"></div>
          </div>
          <span class="mcp-conf-label" style="color:${confColor}">${pct}%</span>
        </div>
        ` : ''}

        ${contract.target_url ? `
        <div class="mcp-section${deltaKeys.includes('target_url') && newVersion ? ' mcp-delta' : ''}">
          <div class="mcp-section-title">TARGET</div>
          <div class="mcp-val mcp-url">${escHtml(contract.target_url)}</div>
          ${contract.target_scope?.mode ? `<div class="mcp-meta">Scope: ${contract.target_scope.mode}</div>` : ''}
          ${contract.auth_spec?.mechanism && contract.auth_spec.mechanism !== 'auto'
            ? `<div class="mcp-meta">Auth: ${contract.auth_spec.mechanism}${contract.auth_spec.login_required ? ' (需要登录)' : ''}</div>`
            : ''}
        </div>
        ` : `
        <div class="mcp-section mcp-empty-section">
          <div class="mcp-section-title">TARGET</div>
          <div class="mcp-empty-hint">(not set)</div>
        </div>
        `}

        ${contract.objective ? `
        <div class="mcp-section${deltaKeys.includes('objective') && newVersion ? ' mcp-delta' : ''}">
          <div class="mcp-section-title">OBJECTIVE</div>
          <div class="mcp-objective">${escHtml(contract.objective)}</div>
          ${contract.objective_type
            ? `<div class="mcp-badge mcp-badge-${contract.objective_type}">${contract.objective_type.replace('_', ' ')}</div>`
            : ''}
          ${(contract.item_limit ?? 0) > 0
            ? `<div class="mcp-meta">Limit: ${contract.item_limit} items</div>`
            : ''}
        </div>
        ` : `
        <div class="mcp-section mcp-empty-section">
          <div class="mcp-section-title">OBJECTIVE</div>
          <div class="mcp-empty-hint">(not set)</div>
          ${(contract.item_limit ?? 0) > 0
            ? `<div class="mcp-meta">Limit: ${contract.item_limit} items</div>`
            : ''}
        </div>
        `}

        ${(contract.requested_fields ?? []).length > 0 ? `
        <div class="mcp-section${deltaKeys.includes('requested_fields') && newVersion ? ' mcp-delta' : ''}">
          <div class="mcp-section-title">FIELDS (${(contract.requested_fields ?? []).length})</div>
          <div class="mcp-fields-list">
            ${(contract.requested_fields ?? []).map(f => renderFieldSpec(f)).join('')}
          </div>
        </div>
        ` : ''}

        ${(contract.execution_spec?.stealth_level || contract.execution_spec?.js_rendering) ? `
        <div class="mcp-section${deltaKeys.includes('execution_spec') && newVersion ? ' mcp-delta' : ''}">
          <div class="mcp-section-title">CONFIG</div>
          <div class="mcp-chips">
            ${contract.execution_spec?.stealth_level ? `<span class="mcp-chip">stealth: ${contract.execution_spec.stealth_level}</span>` : ''}
            ${contract.execution_spec?.js_rendering ? `<span class="mcp-chip">js: ${contract.execution_spec.js_rendering}</span>` : ''}
          </div>
        </div>
        ` : ''}

        ${(contract.assumptions ?? []).length > 0 ? `
        <div class="mcp-section">
          <div class="mcp-section-title">ASSUMPTIONS</div>
          ${(contract.assumptions ?? []).map(a => `<div class="mcp-assumption">• ${escHtml(a)}</div>`).join('')}
        </div>
        ` : ''}

        ${blockingGaps.length > 0 ? `
        <div class="mcp-section mcp-section-warn">
          <div class="mcp-section-title">STILL NEEDED</div>
          ${blockingGaps.map(g => `<div class="mcp-gap">• ${escHtml(g)}</div>`).join('')}
        </div>
        ` : ''}

        ${isLocked ? `
        <div class="mcp-locked-banner">🔒 Contract locked — 任务执行中</div>
        ` : isReady ? `
        <div class="mcp-ready-line">READY TO START</div>
        ` : ''}
      </div>
    `
  }

  dispose(): void {
    if (this.unsub) this.unsub()
  }
}

function renderFieldSpec(f: FieldSpec): string {
  const typeColor: Record<string, string> = {
    string: '#5b8dd9', number: '#00aa55', boolean: '#cc7700', array: '#cc5533', object: '#9b59b6',
  }
  const color = typeColor[f.data_type ?? ''] || '#888888'
  return `
    <div class="mcp-field-row">
      <span class="mcp-field-name">${escHtml(f.field_name ?? '')}</span>
      <span class="mcp-field-type" style="color:${color}">${f.data_type}</span>
      ${f.priority === 1
        ? '<span class="mcp-field-req">must</span>'
        : '<span class="mcp-field-opt">opt</span>'}
    </div>
  `
}

function escHtml(str: string): string {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
