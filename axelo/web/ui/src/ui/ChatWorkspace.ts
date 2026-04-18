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
    const ready = Boolean(current?.ready_to_run) && !current?.current_run_id

    this.el.innerHTML = `
      <div class="chat-shell">
        <div class="chat-header">
          <div>
            <div class="chat-eyebrow">AI Workspace</div>
            <div class="chat-title">${esc(current?.title || 'New session')}</div>
          </div>
          <div class="chat-phase">${esc(current?.status || 'welcome')}</div>
        </div>
        <div class="thread-viewport" id="thread-viewport">
          ${items.length > 0 ? items.map(renderThreadItem).join('') : renderEmptyThread()}
        </div>
        <div class="composer-shell">
          <div class="composer-toolbar">
            <div class="composer-hint">${state.sending ? 'Router is updating the session...' : 'Describe the site, data target, or reverse-engineering goal.'}</div>
            ${ready ? '<button type="button" id="run-start-btn" class="subtle-action">Start run</button>' : ''}
          </div>
          <div class="composer-input-wrap">
            <textarea id="composer-input" class="composer-input" rows="1" placeholder="Ask Axelo to inspect a target, design a crawl path, or recover a data workflow..."></textarea>
            <button type="button" id="composer-send-btn" class="composer-send">Send</button>
          </div>
          ${state.error ? `<div class="composer-error">${esc(state.error)}</div>` : ''}
        </div>
      </div>
    `

    const viewport = this.el.querySelector('#thread-viewport') as HTMLElement | null
    if (viewport) viewport.scrollTop = viewport.scrollHeight

    this.el.querySelector<HTMLButtonElement>('#composer-send-btn')
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

function renderEmptyThread(): string {
  return `
    <div class="thread-empty">
      <div class="msg system">
        <div class="msg-label">Router</div>
        <div class="msg-body">
          Describe the target and what you want to capture. Axelo will turn that into one continuous workflow, from site inspection through extraction and delivery.
        </div>
      </div>
      <div class="thread-empty-note">
        One input is enough to begin. The system will decide whether to browse, inspect transport, reverse logic, draft extraction, or prepare artifacts.
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
