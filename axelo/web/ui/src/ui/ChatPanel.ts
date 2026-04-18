/**
 * ChatPanel — 中央对话面板。
 * 输入栏和就绪度栏已移至 index.html 底部全宽区域，由 main.ts 统一管理。
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
import type { MissionContract } from '../generated/contracts'

// ── Field label map (contract delta display) ─────────────────────────────────
const FIELD_LABELS: Record<string, string> = {
  target_url:       '目标地址',
  objective:        '爬取目标',
  requested_fields: '字段列表',
  execution_spec:   '执行配置',
  auth_spec:        '认证方式',
  output_spec:      '输出格式',
  target_scope:     '爬取范围',
  item_limit:       '数量限制',
  assumptions:      '假设条件',
  constraints:      '约束条件',
}

const IGNORED_DELTA_KEYS = new Set(['readiness_assessment', 'contract_version', 'contract_id', 'created_at'])

export class ChatPanel {
  private el: HTMLElement
  private messagesEl!: HTMLElement
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
        <div class="cp-messages" id="cp-messages">
          <div class="cp-welcome-msg">
            <div class="cp-welcome-text">
              告诉我你想从哪里获取什么数据，或者想分析哪个网站的接口。<br><br>
              我会先和你确认需求细节，然后构建一份可执行的爬取方案。
            </div>
          </div>
        </div>
        <div class="cp-ai-spinner" id="cp-ai-spinner" style="display:none">
          <span class="cp-spinner-dot"></span>
          <span class="cp-spinner-dot"></span>
          <span class="cp-spinner-dot"></span>
          <span style="font-size:10px;color:var(--text3);margin-left:6px">AI 思考中…</span>
        </div>
        <div class="cp-error" id="cp-error" style="display:none"></div>
      </div>
    `

    this.messagesEl = this.el.querySelector('#cp-messages')!
  }

  private bindStore(): void {
    this.unsubIntake = intakeStore.subscribe((state) => {
      const spinner = this.el.querySelector('#cp-ai-spinner') as HTMLElement
      spinner.style.display = state.isWaitingForAI ? 'flex' : 'none'

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
    } catch {
      intakeStore.setError('无法连接服务器，请刷新页面重试。')
    }
  }

  /** 由底部输入栏（main.ts）调用 */
  async handleSend(msg: string): Promise<void> {
    if (!msg.trim()) return

    const state = intakeStore.getState()
    if (!state.intakeId) return

    const tmpId = Date.now().toString()

    if (state.phase === 'executing') {
      this.appendMessage('user', msg, tmpId)
      await sendAnnotation(state.intakeId, msg, 'note')
      this.appendMessage('assistant', `已记录：${msg}。当前任务将继续按原计划执行。`, tmpId + '_ack')
      return
    }

    intakeStore.appendUserMessage(msg, tmpId)
    this.appendMessage('user', msg, tmpId)
    intakeStore.setWaiting(true)
    intakeStore.setError('')

    try {
      const result = await sendIntakeMessage(state.intakeId, msg)
      intakeStore.appendAssistantMessage(result.ai_reply, result.turn_id + '_reply')
      this.appendMessage('assistant', result.ai_reply, result.turn_id + '_reply', result.contract_delta)
      intakeStore.setContract(result.contract, result.contract_delta)
      intakeStore.setPhase(result.phase as IntakePhase)
    } catch (err: any) {
      intakeStore.setError(String(err.message || err))
    } finally {
      intakeStore.setWaiting(false)
    }
  }

  /** 由底部「开始任务」按钮（main.ts）调用 */
  async handleStart(): Promise<void> {
    const state = intakeStore.getState()
    if (!state.intakeId || !state.readiness?.is_ready) return

    intakeStore.setWaiting(true)
    intakeStore.setError('')
    try {
      const result = await startMissionFromContract(state.intakeId)
      intakeStore.setExecuting(result.session_id)
      missionStore.selectSession(result.session_id)
      window.dispatchEvent(new CustomEvent('axelo:mission-started', { detail: { sessionId: result.session_id } }))
    } catch (err: any) {
      intakeStore.setError(String(err.message || err))
    } finally {
      intakeStore.setWaiting(false)
    }
  }

  private appendMessage(
    role: 'user' | 'assistant',
    content: string,
    _turnId: string,
    contractDelta?: Partial<MissionContract> | null,
  ): void {
    const isUser = role === 'user'
    const div = document.createElement('div')
    div.className = `cp-msg cp-msg-${role}`

    const bubbleContent = isUser
      ? escHtml(content).replace(/\n/g, '<br>')
      : this.renderMarkdown(content)

    // Build optional delta tag
    let deltaHtml = ''
    if (!isUser && contractDelta) {
      const keys = Object.keys(contractDelta).filter(k => !IGNORED_DELTA_KEYS.has(k))
      if (keys.length > 0) {
        const label = keys.length === 1
          ? `更新了${FIELD_LABELS[keys[0]] ?? keys[0]}`
          : `更新了 ${keys.length} 个字段`
        deltaHtml = `<div class="cp-delta-tag">${escHtml(label)}</div>`
      }
    }

    div.innerHTML = `
      <div class="cp-msg-bubble ${isUser ? 'cp-msg-user-bubble' : 'cp-msg-ai-bubble'}">
        ${bubbleContent}
      </div>
      ${deltaHtml}
    `
    this.messagesEl.appendChild(div)
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight
  }

  /**
   * Markdown-lite renderer.
   * XSS-safe: escHtml is applied FIRST, then markdown patterns are processed.
   * Supports: **bold**, `inline code`, unordered lists (- / *)
   */
  private renderMarkdown(text: string): string {
    const lines = escHtml(text).split('\n')
    const output: string[] = []
    let listBuffer: string[] = []

    const flushList = (): void => {
      if (listBuffer.length > 0) {
        output.push(
          `<ul class="cp-list">${listBuffer.map(l => `<li>${l}</li>`).join('')}</ul>`
        )
        listBuffer = []
      }
    }

    for (const line of lines) {
      const listMatch = line.match(/^[-*]\s+(.+)$/)
      if (listMatch) {
        listBuffer.push(applyInline(listMatch[1]))
      } else {
        flushList()
        output.push(applyInline(line))
      }
    }
    flushList()

    return output.join('<br>')
  }

  dispose(): void {
    if (this.unsubIntake) this.unsubIntake()
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function escHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function applyInline(s: string): string {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="cp-inline-code">$1</code>')
}
