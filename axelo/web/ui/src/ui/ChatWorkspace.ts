import { sessionStore } from '../store/sessionStore'
import type { ChatThreadItem } from '../workbench/types'

interface ChatWorkspaceOptions {
  onSend: (message: string) => Promise<void>
  onStartRun: () => Promise<void>
}

export class ChatWorkspace {
  private readonly el: HTMLElement
  private readonly options: ChatWorkspaceOptions
  private readonly unsub: () => void

  constructor(el: HTMLElement, options: ChatWorkspaceOptions) {
    this.el = el
    this.options = options
    this.unsub = sessionStore.subscribe(() => this.render())
    this.render()
  }

  private render(): void {
    const state = sessionStore.getState()
    const current = state.current
    const items = current?.thread_items || []
    const inHomeMode = items.length === 0 && !current?.current_run_id
    const showRunAction = Boolean(current?.ready_to_run) && !current?.current_run_id

    this.el.innerHTML = inHomeMode
      ? renderHomeShell(state.sending, state.error)
      : renderConversationShell(current?.title || 'New session', current?.status || 'welcome', items, state.error, showRunAction, state.sending)

    const viewport = this.el.querySelector('#thread-viewport') as HTMLElement | null
    if (viewport) viewport.scrollTop = viewport.scrollHeight

    this.el.querySelector<HTMLButtonElement>('[data-action="send"]')
      ?.addEventListener('click', () => { void this.handleSend() })
    this.el.querySelector<HTMLTextAreaElement>('#composer-input')
      ?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault()
          void this.handleSend()
        }
      })
    this.el.querySelector<HTMLButtonElement>('#run-start-btn')
      ?.addEventListener('click', () => { void this.options.onStartRun() })
  }

  private async handleSend(): Promise<void> {
    const input = this.el.querySelector<HTMLTextAreaElement>('#composer-input')
    const message = input?.value.trim() || ''
    if (!message) return
    if (input) input.value = ''
    await this.options.onSend(message)
  }

  dispose(): void {
    this.unsub()
    this.el.innerHTML = ''
  }
}

function renderHomeShell(sending: boolean, error: string): string {
  return `
    <div class="chat-shell home-shell">
      <div class="home-stack">
        <h1 class="home-title">What should we build in Axelo?</h1>
        ${renderComposer({
          placeholder: '向 Codex 提问、@ 添加文件、/ 输入命令、$ 使用技能',
          sending,
          error,
          home: true,
        })}
        <div class="composer-context-chips">
          <button type="button" class="composer-context-chip">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h2.086a1.5 1.5 0 0 1 1.06.44l.829.81H9.5A1.5 1.5 0 0 1 11 3.75v5.25A1.5 1.5 0 0 1 9.5 10.5h-7A1.5 1.5 0 0 1 1 9V2.5Z" stroke="currentColor" stroke-width="1" fill="none"/></svg>
            Axelo
            <svg width="9" height="9" viewBox="0 0 9 9" fill="none" style="opacity:0.4"><path d="M2 3.5l2.5 2.5L7 3.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button type="button" class="composer-context-chip">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="3" width="10" height="7" rx="1.5" stroke="currentColor" stroke-width="1"/><path d="M4 3V2.5A.5.5 0 0 1 4.5 2h3a.5.5 0 0 1 .5.5V3" stroke="currentColor" stroke-width="1"/><circle cx="6" cy="6.5" r="1" fill="currentColor" opacity=".5"/></svg>
            本地工作
            <svg width="9" height="9" viewBox="0 0 9 9" fill="none" style="opacity:0.4"><path d="M2 3.5l2.5 2.5L7 3.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button type="button" class="composer-context-chip">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="2" r="1.2" stroke="currentColor" stroke-width="1"/><circle cx="2" cy="9" r="1.2" stroke="currentColor" stroke-width="1"/><circle cx="10" cy="9" r="1.2" stroke="currentColor" stroke-width="1"/><path d="M6 3.2V6.5M6 6.5L2.8 8M6 6.5L9.2 8" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>
            main
            <svg width="9" height="9" viewBox="0 0 9 9" fill="none" style="opacity:0.4"><path d="M2 3.5l2.5 2.5L7 3.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
        <div class="home-suggestions">
          <button type="button" class="suggestion-item">
            <div class="suggestion-icon">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 10.5V12h1.5l4.42-4.42-1.5-1.5L2 10.5ZM12.71 3.79a1 1 0 0 0 0-1.42L11.63 1.29a1 1 0 0 0-1.42 0L9.13 2.37l2.12 2.12 1.46-1.46-.01-.24Z" fill="currentColor" opacity=".7"/><path d="M1 4h4M1 7h2M1 10h1" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" opacity=".35"/></svg>
            </div>
            审查我最近的提交是否存在正确性风险和可维护性问题
          </button>
          <button type="button" class="suggestion-item">
            <div class="suggestion-icon">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="3" y="1.5" width="8" height="11" rx="1.5" stroke="currentColor" stroke-width="1.1"/><path d="M5.5 5.5h3M5.5 8h2" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" opacity=".5"/></svg>
            </div>
            解除我最近一个未合并 PR 的阻碍
          </button>
          <button type="button" class="suggestion-item">
            <div class="suggestion-icon">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M5 7a2 2 0 1 0 4 0 2 2 0 0 0-4 0Z" stroke="currentColor" stroke-width="1.1"/><path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.929 2.929l1.06 1.06M10.01 10.01l1.061 1.06M2.929 11.07l1.06-1.06M10.01 3.99l1.061-1.061" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" opacity=".6"/></svg>
            </div>
            将你常用的应用连接到 Codex
          </button>
        </div>
      </div>
    </div>
  `
}

function renderConversationShell(
  title: string,
  phase: string,
  items: ChatThreadItem[],
  error: string,
  showRunAction: boolean,
  sending: boolean,
): string {
  return `
    <div class="chat-shell conversation-shell">
      <div class="chat-header">
        <div>
          <div class="chat-title">${esc(title)}</div>
        </div>
        <div class="chat-phase">${esc(phase)}</div>
      </div>
      <div class="thread-viewport" id="thread-viewport">
        ${items.map(renderThreadItem).join('')}
      </div>
      <div class="composer-shell">
        ${renderComposer({
          placeholder: 'Continue the conversation...',
          sending,
          error,
          home: false,
          showRunAction,
        })}
      </div>
    </div>
  `
}

function renderComposer(options: {
  placeholder: string
  sending: boolean
  error: string
  home: boolean
  showRunAction?: boolean
}): string {
  const sendIcon = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 12V2M2.5 6.5L7 2l4.5 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`
  const status = options.sending
    ? `<button type="button" class="composer-submit" data-action="send" disabled style="opacity:.45;">${sendIcon}</button>`
    : `<button type="button" class="composer-submit is-active" data-action="send" aria-label="Send">${sendIcon}</button>`

  if (options.home) {
    return `
      <div class="composer-shell">
        <div class="composer-card">
          <textarea id="composer-input" class="composer-input" rows="4" placeholder="${esc(options.placeholder)}"></textarea>
          <div class="composer-foot">
            <div class="composer-tools">
              <button type="button" class="composer-icon" aria-hidden="true">+</button>
              <button type="button" class="composer-chip-orange">完全词问视频 ▾</button>
            </div>
            <div class="composer-meta">
              <button type="button" class="composer-chip">GPT-5.4 ▾</button>
              <button type="button" class="composer-chip">中 ▾</button>
              <button type="button" class="composer-icon" aria-label="语音输入">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="4.5" y="1" width="4" height="7" rx="2" stroke="currentColor" stroke-width="1.1"/><path d="M2 6.5A4.5 4.5 0 0 0 11 6.5" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><path d="M6.5 11v1.5" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg>
              </button>
              ${status}
            </div>
          </div>
          ${options.error ? `<div class="composer-error">${esc(options.error)}</div>` : ''}
        </div>
      </div>
    `
  }

  const trailingAction = options.showRunAction
    ? '<button type="button" id="run-start-btn" class="composer-chip">Start run</button>'
    : ''

  return `
    <div class="composer-shell">
      <div class="composer-card">
        <textarea id="composer-input" class="composer-input" rows="3" placeholder="${esc(options.placeholder)}"></textarea>
        <div class="composer-foot">
          <div class="composer-tools">
            <button type="button" class="composer-icon" aria-hidden="true">+</button>
            <button type="button" class="composer-chip">Axelo</button>
          </div>
          <div class="composer-meta">
            ${trailingAction}
            ${status}
          </div>
        </div>
        ${options.error ? `<div class="composer-error">${esc(options.error)}</div>` : ''}
      </div>
    </div>
  `
}

function renderThreadItem(item: ChatThreadItem): string {
  const classes = ['msg', item.kind.replace(/_/g, '-')]
  if (item.status) classes.push(`status-${item.status}`)
  const title = item.title ? `<div class="msg-title">${esc(item.title)}</div>` : ''
  const status = item.status ? `<span class="msg-status">${esc(item.status)}</span>` : ''
  const label = item.actor_type === 'user'
    ? 'You'
    : item.actor_type === 'router'
      ? 'Router'
      : item.actor_type === 'agent'
        ? item.actor_id
        : 'System'
  return `
    <div class="${classes.join(' ')}">
      <div class="msg-head">
        <div class="msg-label">${esc(label)}</div>
        ${status}
      </div>
      ${title}
      <div class="msg-body">${esc(item.content || '').replace(/\n/g, '<br>')}</div>
    </div>
  `
}

function esc(value: string): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
