/**
 * App entry — phase-based 2-panel routing.
 *
 * Pre-execution (welcome / discussing / contract_ready):
 *   Left   → MissionContractPanel (live contract view)
 *   Right  → ChatPanel (requirement discussion)
 *
 * During execution (executing / complete / failed):
 *   Left   → MissionContractPanel (locked)
 *   Right  → ExecutionTimelinePanel (replaces ChatPanel)
 */

import { ChatPanel }              from './ui/ChatPanel'
import { MissionContractPanel }   from './ui/MissionContractPanel'
import { ExecutionTimelinePanel } from './ui/ExecutionTimelinePanel'
import { intakeStore, type IntakePhase } from './store/intakeStore'
import { missionStore }           from './store/missionStore'
import { WsClient }               from './ws/client'

// ── DOM refs ─────────────────────────────────────────────────────────────────
const leftEl  = document.getElementById('left-panel')  as HTMLElement
const rightEl = document.getElementById('right-panel') as HTMLElement

// ── Chat container (lives inside right panel) ─────────────────────────────
const chatEl = document.createElement('div')
chatEl.id = 'chat-container'
chatEl.style.cssText = 'flex:1; display:flex; flex-direction:column; overflow:hidden;'
rightEl.appendChild(chatEl)

// ── Core panels ───────────────────────────────────────────────────────────────
const contractPanel = new MissionContractPanel(leftEl)
const chatPanel     = new ChatPanel(chatEl)

// Timeline — created on demand during execution
let timelinePanel: ExecutionTimelinePanel | null = null
let timelineEl: HTMLElement | null = null
let wsClient: WsClient | null = null

// ── Phase routing ─────────────────────────────────────────────────────────────
let currentPhase: IntakePhase = 'welcome'

function onPhaseChange(phase: IntakePhase): void {
  if (phase === currentPhase) return
  currentPhase = phase

  if (phase === 'executing' || phase === 'complete' || phase === 'failed') {
    showExecutionTimeline()
  } else {
    hideExecutionTimeline()
  }
}

function showExecutionTimeline(): void {
  if (timelineEl) return  // already visible

  // Hide chat panel
  chatEl.style.display = 'none'

  // Create timeline container filling the right panel
  timelineEl = document.createElement('div')
  timelineEl.id = 'timeline-container'
  timelineEl.style.cssText = 'flex:1; display:flex; flex-direction:column; overflow:hidden; background:#0a0a14;'
  rightEl.appendChild(timelineEl)

  timelinePanel = new ExecutionTimelinePanel(timelineEl)
}

function hideExecutionTimeline(): void {
  if (timelineEl) {
    timelinePanel?.dispose()
    timelinePanel = null
    timelineEl.remove()
    timelineEl = null
  }
  // Restore chat panel
  chatEl.style.display = 'flex'
}

// ── Mission start event ───────────────────────────────────────────────────────
window.addEventListener('axelo:mission-started', (e: Event) => {
  const detail = (e as CustomEvent).detail as { sessionId: string }
  const sessionId = detail.sessionId
  if (!sessionId) return

  // Connect WebSocket for live events
  if (wsClient) wsClient.disconnect()
  wsClient = new WsClient(sessionId)
  wsClient.connect()

  // Update header session select
  const select = document.getElementById('session-select') as HTMLSelectElement
  if (select) {
    const opt = document.createElement('option')
    opt.value = sessionId
    opt.textContent = sessionId
    select.appendChild(opt)
    select.value = sessionId
  }
})

// ── Subscribe to intake phase changes ────────────────────────────────────────
intakeStore.subscribe((state) => {
  onPhaseChange(state.phase)
})

// ── Session selector (for loading existing sessions) ─────────────────────────
const sessionSelect = document.getElementById('session-select') as HTMLSelectElement
sessionSelect?.addEventListener('change', async () => {
  const sessionId = sessionSelect.value
  if (!sessionId) return
  if (wsClient) wsClient.disconnect()
  missionStore.selectSession(sessionId)
  wsClient = new WsClient(sessionId)
  wsClient.connect()
})

// ── Load session list on startup ─────────────────────────────────────────────
async function loadSessionList(): Promise<void> {
  try {
    const resp = await fetch('/api/sessions')
    if (!resp.ok) return
    const data = await resp.json()
    const sessions: any[] = Array.isArray(data) ? data : (data.sessions || [])
    const select = document.getElementById('session-select') as HTMLSelectElement
    if (!select) return
    for (const s of sessions.slice(0, 20)) {
      const sid = s.session_id || s.id || String(s)
      if (!sid) continue
      if (select.querySelector(`option[value="${sid}"]`)) continue
      const opt = document.createElement('option')
      opt.value = sid
      opt.textContent = sid
      select.appendChild(opt)
    }
  } catch { /* ignore */ }
}

loadSessionList()

// ── Connection badge ──────────────────────────────────────────────────────────
missionStore.subscribe((state) => {
  const dot   = document.getElementById('conn-dot')
  const label = document.getElementById('conn-label')
  if (dot)   dot.classList.toggle('live', state.connected)
  if (label) label.textContent = state.connected ? 'Live' : 'Offline'
})

// ── Cleanup ────────────────────────────────────────────────────────────────────
window.addEventListener('beforeunload', () => {
  chatPanel.dispose()
  contractPanel.dispose()
  timelinePanel?.dispose()
  wsClient?.disconnect()
})
