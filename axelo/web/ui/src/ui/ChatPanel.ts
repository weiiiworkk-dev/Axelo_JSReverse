/**
 * ChatPanel — AI requirement discussion chat interface (right panel).
 * Pre-execution: full chat mode for requirement intake.
 * Post-start: annotation mode only.
 */

import {
  intakeStore,
  sendIntakeMessage,
  sendAnnotation,
  createIntakeSession,
  startMissionFromContract,
  type IntakePhase,
} from '../store/intakeStore'
import { missionStore } from '../store/missionStore'

const PLACEHOLDER_DISCUSSING = 'Describe what you want to crawl or reverse engineer...'
const PLACEHOLDER_EXECUTING  = 'Add a note or annotation to the current mission...'

export class ChatPanel {
  private el: HTMLElement
  private messagesEl!: HTMLElement
  private inputEl!: HTMLTextAreaElement
  private sendBtn!: HTMLButtonElement
  private phaseBarEl!: HTMLElement
  private startBtnEl!: HTMLButtonElement
  private unsubIntake: (() => void) | null = null

  constructor(el: HTMLElement) {
    this.el = el
    this.render()
    this.bindStore()
    this.initSession()
  }

  private render(): void {
    this.el.innerHTML = `
      <div class="cp-root">
        <div class="cp-header">
          <div class="cp-title">💬 Requirements</div>
          <div class="cp-phase-badge" id="cp-phase-badge">Welcome</div>
        </div>
        <div class="cp-messages" id="cp-messages">
          <div class="cp-welcome-msg">
            <div class="cp-welcome-icon">🤖</div>
            <div class="cp-welcome-text">
              Hello! I'm your intake specialist.<br>
              Describe what you want to crawl or reverse engineer, and I'll build a structured mission plan.
            </div>
          </div>
        </div>
        <div class="cp-readiness-bar" id="cp-readiness-bar" style="display:none">
          <div class="cp-readiness-fill" id="cp-readiness-fill" style="width:0%"></div>
          <span class="cp-readiness-label" id="cp-readiness-label">0% ready</span>
        </div>
        <div class="cp-missing" id="cp-missing" style="display:none"></div>
        <div class="cp-start-row" id="cp-start-row" style="display:none">
          <button class="cp-start-btn" id="cp-start-btn" disabled>Start Mission</button>
        </div>
        <div class="cp-input-row">
          <textarea class="cp-input" id="cp-input" rows="2" placeholder="${PLACEHOLDER_DISCUSSING}"></textarea>
          <button class="cp-send-btn" id="cp-send-btn">Send</button>
        </div>
        <div class="cp-ai-spinner" id="cp-ai-spinner" style="display:none">
          <span class="cp-spinner-dot"></span>
          <span class="cp-spinner-dot"></span>
          <span class="cp-spinner-dot"></span>
          <span style="font-size:10px;color:#888;margin-left:6px">AI is thinking…</span>
        </div>
        <div class="cp-error" id="cp-error" style="display:none"></div>
      </div>
    `

    this.messagesEl  = this.el.querySelector('#cp-messages')!
    this.inputEl     = this.el.querySelector('#cp-input')!
    this.sendBtn     = this.el.querySelector('#cp-send-btn')!
    this.phaseBarEl  = this.el.querySelector('#cp-phase-badge')!
    this.startBtnEl  = this.el.querySelector('#cp-start-btn')!

    this.sendBtn.addEventListener('click', () => this.handleSend())
    this.inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        this.handleSend()
      }
    })
    this.startBtnEl.addEventListener('click', () => this.handleStart())
  }

  private bindStore(): void {
    this.unsubIntake = intakeStore.subscribe((state) => {
      this.updatePhase(state.phase)
      this.updateReadiness(
        state.readiness?.confidence ?? 0,
        state.readiness?.blocking_gaps ?? [],
        state.readiness?.missing_info ?? [],
      )
      // Gate is driven by is_ready (backend deterministic gates), NOT confidence threshold
      this.startBtnEl.disabled = !state.readiness?.is_ready || state.isWaitingForAI || state.phase === 'executing'

      const spinner = this.el.querySelector('#cp-ai-spinner') as HTMLElement
      spinner.style.display = state.isWaitingForAI ? 'flex' : 'none'
      this.sendBtn.disabled = state.isWaitingForAI || state.phase === 'executing'
      this.inputEl.disabled = state.isWaitingForAI

      const errEl = this.el.querySelector('#cp-error') as HTMLElement
      if (state.error) {
        errEl.style.display = 'block'
        errEl.textContent = state.error
      } else {
        errEl.style.display = 'none'
      }
    })
  }

  private async initSession(): Promise<void> {
    try {
      const intakeId = await createIntakeSession()
      intakeStore.setIntakeId(intakeId)
      intakeStore.setPhase('welcome')
    } catch (e) {
      intakeStore.setError('Failed to connect to server. Please refresh.')
    }
  }

  private async handleSend(): Promise<void> {
    const msg = this.inputEl.value.trim()
    if (!msg) return

    const state = intakeStore.getState()
    if (!state.intakeId) return

    this.inputEl.value = ''
    const tmpId = Date.now().toString()

    if (state.phase === 'executing') {
      // Annotation mode
      this.appendMessage('user', msg, tmpId)
      await sendAnnotation(state.intakeId, msg, 'note')
      this.appendMessage('assistant', `Noted: ${msg}. The mission will continue with the current plan.`, tmpId + '_ack')
      return
    }

    // Normal intake mode — call AI
    intakeStore.appendUserMessage(msg, tmpId)
    this.appendMessage('user', msg, tmpId)
    intakeStore.setWaiting(true)
    intakeStore.setError('')

    try {
      const result = await sendIntakeMessage(state.intakeId, msg)
      intakeStore.appendAssistantMessage(result.ai_reply, result.turn_id + '_reply')
      this.appendMessage('assistant', result.ai_reply, result.turn_id + '_reply')
      intakeStore.setContract(result.contract, result.contract_delta)
      intakeStore.setPhase(result.phase as IntakePhase)
    } catch (err: any) {
      intakeStore.setError(String(err.message || err))
    } finally {
      intakeStore.setWaiting(false)
    }
  }

  private async handleStart(): Promise<void> {
    const state = intakeStore.getState()
    if (!state.intakeId || !state.readiness?.is_ready) return

    intakeStore.setWaiting(true)
    intakeStore.setError('')
    try {
      const result = await startMissionFromContract(state.intakeId)
      intakeStore.setExecuting(result.session_id)
      // Notify missionStore to connect WS
      missionStore.selectSession(result.session_id)
      window.dispatchEvent(new CustomEvent('axelo:mission-started', { detail: { sessionId: result.session_id } }))
    } catch (err: any) {
      intakeStore.setError(String(err.message || err))
    } finally {
      intakeStore.setWaiting(false)
    }
  }

  private appendMessage(role: 'user' | 'assistant', content: string, _turnId: string): void {
    const isUser = role === 'user'
    const div = document.createElement('div')
    div.className = `cp-msg cp-msg-${role}`
    div.innerHTML = `
      <div class="cp-msg-bubble ${isUser ? 'cp-msg-user-bubble' : 'cp-msg-ai-bubble'}">
        ${escHtml(content).replace(/\n/g, '<br>')}
      </div>
    `
    this.messagesEl.appendChild(div)
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight
  }

  private updatePhase(phase: IntakePhase): void {
    const labels: Record<IntakePhase, string> = {
      welcome:         'Welcome',
      discussing:      'Discussing',
      contract_ready:  'Ready',
      executing:       'Executing',
      complete:        'Complete',
      failed:          'Failed',
    }
    const colors: Record<IntakePhase, string> = {
      welcome:         '#8a7e6e',
      discussing:      '#e0a030',
      contract_ready:  '#4cad6e',
      executing:       '#5b8dd9',
      complete:        '#4cad6e',
      failed:          '#d95555',
    }
    this.phaseBarEl.textContent = labels[phase] || phase
    this.phaseBarEl.style.background = colors[phase] || '#8a7e6e'

    // Show/hide start row
    const startRow = this.el.querySelector('#cp-start-row') as HTMLElement
    const readinessBar = this.el.querySelector('#cp-readiness-bar') as HTMLElement
    if (phase === 'welcome') {
      startRow.style.display = 'none'
      readinessBar.style.display = 'none'
    } else if (phase === 'discussing' || phase === 'contract_ready') {
      startRow.style.display = 'flex'
      readinessBar.style.display = 'flex'
    } else if (phase === 'executing') {
      startRow.style.display = 'none'
      readinessBar.style.display = 'none'
      this.inputEl.placeholder = PLACEHOLDER_EXECUTING
    }
  }

  private updateReadiness(confidence: number, blockingGaps: string[], missingInfo: string[]): void {
    const pct = Math.round(confidence * 100)
    const fillEl = this.el.querySelector('#cp-readiness-fill') as HTMLElement
    const labelEl = this.el.querySelector('#cp-readiness-label') as HTMLElement
    const missingEl = this.el.querySelector('#cp-missing') as HTMLElement

    if (fillEl) {
      fillEl.style.width = `${pct}%`
      // Bar color based on is_ready, not confidence threshold
      fillEl.style.background = blockingGaps.length === 0 ? '#4cad6e' : pct >= 50 ? '#e0a030' : '#d95555'
    }
    // Label: show gate status, confidence is secondary/decorative
    if (labelEl) {
      if (blockingGaps.length === 0) {
        labelEl.textContent = `Ready (${pct}%)`
      } else {
        labelEl.textContent = `${pct}% — ${blockingGaps.length} issue${blockingGaps.length > 1 ? 's' : ''} blocking`
      }
    }

    if (missingEl) {
      const items: string[] = []
      // Show blocking gaps first (hard gates), then non-blocking missing info
      if (blockingGaps.length > 0) {
        items.push('<span class="cp-gap-header">Cannot start:</span>')
        items.push(...blockingGaps.map(g => `<span class="cp-blocking-item">✗ ${escHtml(g)}</span>`))
      }
      if (missingInfo.length > 0) {
        items.push(...missingInfo.map(m => `<span class="cp-missing-item">• ${escHtml(m)}</span>`))
      }
      if (items.length > 0) {
        missingEl.style.display = 'block'
        missingEl.innerHTML = items.join('')
      } else {
        missingEl.style.display = 'none'
      }
    }
  }

  dispose(): void {
    if (this.unsubIntake) this.unsubIntake()
  }
}

function escHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
