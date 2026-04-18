import { sessionStore } from './store/sessionStore'
import { runStore } from './store/runStore'
import { ChatWorkspace } from './ui/ChatWorkspace'
import { SystemPanel } from './ui/SystemPanel'
import { RunClient } from './ws/runClient'

const appRoot = document.getElementById('app') as HTMLElement
const chatRoot = document.getElementById('chat-root') as HTMLElement
const systemRoot = document.getElementById('system-root') as HTMLElement
const sessionList = document.getElementById('session-list') as HTMLElement
const newChatButton = document.getElementById('new-chat-btn') as HTMLButtonElement
const sessionTitle = document.getElementById('session-title') as HTMLElement

const runClient = new RunClient()
const chatWorkspace = new ChatWorkspace(chatRoot, {
  onSend: async (message) => {
    if (!sessionStore.getState().current) {
      await sessionStore.createSession()
    }
    await sessionStore.sendMessage(message)
  },
  onStartRun: async () => {
    const runId = await sessionStore.startRun()
    if (runId) {
      await runStore.loadRun(runId)
      runClient.connect(runId)
    }
  },
})

const systemPanel = new SystemPanel(systemRoot)

function renderSidebar(): void {
  const state = sessionStore.getState()
  const currentId = state.current?.session_id || ''
  const inConversation = Boolean((state.current?.thread_items || []).length > 0 || state.current?.current_run_id)
  sessionTitle.textContent = inConversation ? (state.current?.title || 'Axelo') : 'Axelo'
  sessionList.innerHTML = state.sessions.map(session => `
    <button type="button" class="nav-session ${session.session_id === currentId ? 'is-active' : ''}" data-session-id="${session.session_id}">
      <span class="nav-session-title">${esc(session.title)}</span>
      <span class="nav-session-meta">${esc(session.latest_run_status || session.status || 'idle')}</span>
    </button>
  `).join('')

  sessionList.querySelectorAll<HTMLButtonElement>('[data-session-id]').forEach(button => {
    button.addEventListener('click', () => {
      const sessionId = button.dataset.sessionId || ''
      void openSession(sessionId)
    })
  })

  appRoot.dataset.mode = inConversation ? 'conversation' : 'home'
}

async function openSession(sessionId: string): Promise<void> {
  runClient.disconnect()
  runStore.reset()
  await sessionStore.loadSession(sessionId)
  const current = sessionStore.getState().current
  if (current?.current_run_id) {
    await runStore.loadRun(current.current_run_id)
  } else if (current?.session_id && current.status !== 'welcome') {
    const legacyRunId = current.session_id
    try {
      await runStore.loadRun(legacyRunId)
    } catch {
      runStore.reset()
    }
  }
  const runId = runStore.getState().current?.run_id || ''
  if (runId) runClient.connect(runId, runStore.getState().current?.last_seq || 0)
}

sessionStore.subscribe(() => {
  renderSidebar()
})

newChatButton.addEventListener('click', () => {
  runClient.disconnect()
  runStore.reset()
  sessionStore.openHome()
})

void (async () => {
  await sessionStore.refreshSessions()
  sessionStore.openHome()
})()

window.addEventListener('beforeunload', () => {
  runClient.disconnect()
  chatWorkspace.dispose()
  systemPanel.dispose()
})

function esc(value: string): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
