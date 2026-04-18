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
          placeholder: 'Describe the target, route, or extraction goal...',
          sending,
          error,
          home: true,
        })}
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
          <div class="chat-eyebrow">Workspace</div>
          <div class="chat-title">${esc(title)}</div>
        </div>
        <div class="chat-phase">${esc(phase)}</div>
      </div>
      <div class="thread-viewport" id="thread-viewport">
        ${items.map(renderThreadItem).join('')}
      </div>
      <div class="composer-shell">
        ${renderComposer({
          placeholder: 'Continue the run, adjust direction, or request a deliverable...',
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
  const status = options.sending ? '<button type="button" class="composer-submit" data-action="send" disabled>…</button>' : '<button type="button" class="composer-submit" data-action="send" aria-label="Send">↑</button>'
  const trailingAction = options.home
    ? '<button type="button" class="composer-chip">Workspace</button>'
    : options.showRunAction
      ? '<button type="button" id="run-start-btn" class="composer-chip">Start run</button>'
      : ''

  return `
    <div class="composer-shell">
      <div class="composer-card">
        <textarea id="composer-input" class="composer-input" rows="${options.home ? '4' : '3'}" placeholder="${esc(options.placeholder)}"></textarea>
        <div class="composer-foot">
          <div class="composer-tools">
            <button type="button" class="composer-icon" aria-hidden="true">+</button>
            <button type="button" class="composer-chip">Axelo</button>
            <button type="button" class="composer-chip">GPT-5.4</button>
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
