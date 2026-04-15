/**
 * ChatPanel — 右侧对话面板（仅显示消息）。
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

export class ChatPanel {
  private el: HTMLElement
  private messagesEl!: HTMLElement
  private phaseBarEl!: HTMLElement
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
          <div class="cp-title">对话</div>
          <div class="cp-phase-badge" id="cp-phase-badge">欢迎</div>
        </div>
        <div class="cp-messages" id="cp-messages">
          <div class="cp-welcome-msg">
            <span class="cp-welcome-icon">🤖</span>
            <div class="cp-welcome-text">
              你好！我是 Axelo 需求助手。<br>
              请描述你想爬取什么，或者想逆向分析哪个网站，我会为你构建结构化的任务计划。<br><br>
              示例：<br>
              &nbsp;&nbsp;'从 amazon.com 获取 iPhone 15 商品列表'<br>
              &nbsp;&nbsp;'抓取 linkedin.com 上的招聘信息'<br>
              &nbsp;&nbsp;'逆向分析 example.com 的搜索 API'
            </div>
          </div>
        </div>
        <div class="cp-ai-spinner" id="cp-ai-spinner" style="display:none">
          <span class="cp-spinner-dot"></span>
          <span class="cp-spinner-dot"></span>
          <span class="cp-spinner-dot"></span>
          <span style="font-size:10px;color:#888;margin-left:6px">AI 思考中…</span>
        </div>
        <div class="cp-error" id="cp-error" style="display:none"></div>
      </div>
    `

    this.messagesEl = this.el.querySelector('#cp-messages')!
    this.phaseBarEl = this.el.querySelector('#cp-phase-badge')!
  }

  private bindStore(): void {
    this.unsubIntake = intakeStore.subscribe((state) => {
      this.updatePhase(state.phase)

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
      this.appendMessage('assistant', result.ai_reply, result.turn_id + '_reply')
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
      welcome:        '欢迎',
      discussing:     '讨论中',
      contract_ready: '已就绪',
      executing:      '执行中',
      complete:       '已完成',
      failed:         '失败',
    }
    const colors: Record<IntakePhase, string> = {
      welcome:        '#555555',
      discussing:     '#cc7700',
      contract_ready: '#00aa55',
      executing:      '#5b8dd9',
      complete:       '#00aa55',
      failed:         '#cc3333',
    }
    this.phaseBarEl.textContent = labels[phase] || phase
    this.phaseBarEl.style.background = colors[phase] || '#555555'
  }

  dispose(): void {
    if (this.unsubIntake) this.unsubIntake()
  }
}

function escHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
