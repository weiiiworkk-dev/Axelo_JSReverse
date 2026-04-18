/**
 * App 入口 — 双面板路由 + 底部全宽输入栏。
 *
 * 预执行阶段（welcome / discussing / contract_ready）：
 *   Left   → MissionContractPanel（实时合约视图）
 *   Right  → ChatPanel（需求讨论）
 *   Bottom → 就绪度进度条 + 输入栏
 *
 * 执行阶段（executing / complete / failed）：
 *   Left   → MissionContractPanel（锁定）
 *   Right  → ExecutionTimelinePanel（替换 ChatPanel）
 *   Bottom → 就绪度行隐藏，输入栏改为批注模式
 */

import { ChatPanel }              from './ui/ChatPanel'
import { MissionContractPanel }   from './ui/MissionContractPanel'
import { ExecutionTimelinePanel } from './ui/ExecutionTimelinePanel'
import { intakeStore, type IntakePhase } from './store/intakeStore'
import { missionStore }           from './store/missionStore'
import { WsClient }               from './ws/client'
import { RightPanelController }   from './rightPanel/controller'
import { rightPanelStore }        from './rightPanel/store'
import { normalizeWsEvent }       from './rightPanel/wsAdapter'

// ── DOM refs ──────────────────────────────────────────────────────────────────
const leftEl  = document.getElementById('left-panel')  as HTMLElement
const rightEl = document.getElementById('right-panel') as HTMLElement

// ── Bottom bar refs ───────────────────────────────────────────────────────────
const readinessLabel  = document.getElementById('readiness-label')  as HTMLElement
const readinessFill   = document.getElementById('readiness-bar-fill') as HTMLElement
const readinessStatus = document.getElementById('readiness-status') as HTMLElement
const mainStartBtn    = document.getElementById('main-start-btn')   as HTMLButtonElement
const mainInput       = document.getElementById('main-input')       as HTMLTextAreaElement
const mainSendBtn     = document.getElementById('main-send-btn')    as HTMLButtonElement
const readinessRow    = document.getElementById('readiness-row')    as HTMLElement

// ── Chat container ────────────────────────────────────────────────────────────
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

// ── Right panel (AI process view) ────────────────────────────────────────────
const rpContainerEl = document.getElementById('rp-container') as HTMLElement
const rpController  = new RightPanelController(rpContainerEl)

// ── Welcome view / panels toggle ─────────────────────────────────────────────
const welcomeView  = document.getElementById('welcome-view')  as HTMLElement | null
const mainArea     = document.getElementById('main')          as HTMLElement | null
const bottomBar    = document.getElementById('bottom')        as HTMLElement | null

function setWelcomeVisible(show: boolean): void {
  if (welcomeView) welcomeView.style.display  = show ? 'flex'  : 'none'
  if (mainArea)    mainArea.style.display     = show ? 'none'  : 'flex'
  if (bottomBar)   bottomBar.style.display    = show ? 'none'  : 'block'
}

// ── Phase routing ─────────────────────────────────────────────────────────────
let currentPhase: IntakePhase = 'welcome'

function setRightCardMode(mode: 'contract' | 'process'): void {
  const leftPanel      = document.getElementById('left-panel')
  const rpContainer    = document.getElementById('rp-container')
  const sectionLabel   = document.getElementById('rc-section-label')
  if (mode === 'process') {
    if (leftPanel)    leftPanel.style.display    = 'none'
    if (rpContainer)  rpContainer.style.display  = 'flex'
    if (sectionLabel) sectionLabel.textContent   = 'AI 进程'
  } else {
    if (leftPanel)    leftPanel.style.display    = ''
    if (rpContainer)  rpContainer.style.display  = 'none'
    if (sectionLabel) sectionLabel.textContent   = '合约规划'
  }
}

function onPhaseChange(phase: IntakePhase): void {
  if (phase === currentPhase) return
  currentPhase = phase

  // Toggle welcome vs panels
  setWelcomeVisible(phase === 'welcome')

  if (phase === 'executing' || phase === 'complete' || phase === 'failed') {
    showExecutionTimeline()
    setRightCardMode('process')
  } else {
    hideExecutionTimeline()
    setRightCardMode('contract')
  }

  // Bottom bar: hide readiness row during execution
  if (readinessRow) {
    readinessRow.style.display = (phase === 'executing' || phase === 'complete' || phase === 'failed')
      ? 'none'
      : 'flex'
  }

  // Show/hide start button based on phase
  const isDiscussing = phase === 'discussing' || phase === 'contract_ready'
  if (mainStartBtn) {
    mainStartBtn.style.display = isDiscussing ? 'inline-block' : 'none'
  }

  // Input placeholder
  if (mainInput) {
    mainInput.placeholder = phase === 'executing'
      ? '添加批注或备注到当前任务...'
      : '继续告诉 Axelo 更多细节...'
  }
}

function showExecutionTimeline(): void {
  if (timelineEl) return

  chatEl.style.display = 'none'

  timelineEl = document.createElement('div')
  timelineEl.id = 'timeline-container'
  timelineEl.style.cssText = 'flex:1; display:flex; flex-direction:column; overflow:hidden;'
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
  chatEl.style.display = 'flex'
}

// ── Bottom bar — readiness wiring ─────────────────────────────────────────────
intakeStore.subscribe((state) => {
  onPhaseChange(state.phase)

  const conf = state.readiness?.confidence ?? 0
  const pct = Math.round(conf * 100)
  const blockingGaps = state.readiness?.blocking_gaps ?? []
  const isReady = state.readiness?.is_ready ?? false

  // Readiness label
  if (readinessLabel) {
    readinessLabel.textContent = `就绪度：${pct}%`
  }

  // Welcome view model button shows readiness
  const welcomeModelBtn = document.getElementById('welcome-model-btn')
  if (welcomeModelBtn) {
    welcomeModelBtn.childNodes[0]!.textContent = `就绪度 ${pct}%`
  }

  // Progress bar fill + color
  if (readinessFill) {
    readinessFill.style.width = `${pct}%`
    readinessFill.style.background = blockingGaps.length === 0 && pct > 0
      ? 'var(--success)'
      : pct >= 50
        ? 'var(--warn)'
        : 'var(--danger)'
  }

  // Status text
  if (readinessStatus) {
    if (isReady) {
      readinessStatus.textContent = '可以开始'
      readinessStatus.style.color = 'var(--success)'
    } else if (blockingGaps.length > 0) {
      readinessStatus.textContent = `${blockingGaps.length} 项未满足`
      readinessStatus.style.color = 'var(--danger)'
    } else {
      readinessStatus.textContent = '需要更多信息'
      readinessStatus.style.color = 'var(--warn)'
    }
  }

  // Start button
  if (mainStartBtn) {
    mainStartBtn.disabled = !isReady || state.isWaitingForAI || state.phase === 'executing'
  }

  // Send button
  if (mainSendBtn) {
    mainSendBtn.disabled = state.isWaitingForAI
  }
  if (mainInput) {
    mainInput.disabled = state.isWaitingForAI
  }
})

// ── Bottom bar — input wiring ──────────────────────────────────────────────────
async function doSend(): Promise<void> {
  const msg = mainInput.value.trim()
  if (!msg) return
  mainInput.value = ''
  await chatPanel.handleSend(msg)
}

mainSendBtn?.addEventListener('click', () => { void doSend() })

mainInput?.addEventListener('keydown', (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void doSend()
  }
})

// ── Welcome textarea wiring ────────────────────────────────────────────────────
const welcomeTextarea = document.getElementById('welcome-textarea') as HTMLTextAreaElement | null

async function doWelcomeSend(): Promise<void> {
  if (!welcomeTextarea) return
  const msg = welcomeTextarea.value.trim()
  if (!msg) return
  welcomeTextarea.value = ''
  mainInput.value = msg
  await chatPanel.handleSend(msg)
}

welcomeTextarea?.addEventListener('keydown', (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void doWelcomeSend()
  }
})

mainStartBtn?.addEventListener('click', () => { void chatPanel.handleStart() })

// ── Mission start event ───────────────────────────────────────────────────────
window.addEventListener('axelo:mission-started', (e: Event) => {
  const detail = (e as CustomEvent).detail as { sessionId: string }
  const sessionId = detail.sessionId
  if (!sessionId) return

  if (wsClient) wsClient.disconnect()
  wsClient = new WsClient(sessionId)
  wsClient.connect()

  const select = document.getElementById('session-select') as HTMLSelectElement
  if (select) {
    if (!select.querySelector(`option[value="${sessionId}"]`)) {
      const opt = document.createElement('option')
      opt.value = sessionId
      opt.textContent = sessionId
      select.appendChild(opt)
    }
    select.value = sessionId
  }
  addSidebarSession(sessionId)
  activateSidebarSession(sessionId)
})

// ── WsEvent → rightPanelStore bridge ─────────────────────────────────────────
// Detects newly appended WsEvents and normalizes them into AgentEvents.
let _rpEventCursor = 0
missionStore.subscribe((mState) => {
  const incoming = mState.events.slice(_rpEventCursor)
  _rpEventCursor = mState.events.length
  for (const wsEv of incoming) {
    const agentEv = normalizeWsEvent(wsEv)
    if (agentEv) rightPanelStore.dispatch(agentEv)
  }
})

// ── Session selector ──────────────────────────────────────────────────────────
const sessionSelect = document.getElementById('session-select') as HTMLSelectElement
sessionSelect?.addEventListener('change', async () => {
  const sessionId = sessionSelect.value
  if (!sessionId) return
  if (wsClient) wsClient.disconnect()
  missionStore.selectSession(sessionId)
  rightPanelStore.reset()
  _rpEventCursor = 0
  wsClient = new WsClient(sessionId)
  wsClient.connect()
})

// ── Sidebar session list helpers ──────────────────────────────────────────────
const sidebarSessionList = document.getElementById('session-list') as HTMLElement

function addSidebarSession(sid: string): void {
  if (!sidebarSessionList) return
  if (sidebarSessionList.querySelector(`[data-sid="${sid}"]`)) return
  const item = document.createElement('div')
  item.className = 'sb-session-item'
  item.dataset.sid = sid
  const label = document.createElement('span')
  label.className = 'sb-session-id'
  label.textContent = sid
  item.appendChild(label)
  item.addEventListener('click', () => activateSidebarSession(sid))
  sidebarSessionList.appendChild(item)
}

function activateSidebarSession(sid: string): void {
  const select = document.getElementById('session-select') as HTMLSelectElement
  if (!select) return
  select.value = sid
  select.dispatchEvent(new Event('change'))
  sidebarSessionList.querySelectorAll('.sb-session-item').forEach(el =>
    el.classList.toggle('active', (el as HTMLElement).dataset.sid === sid)
  )
}

// ── Load session list on startup ──────────────────────────────────────────────
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
      if (!select.querySelector(`option[value="${sid}"]`)) {
        const opt = document.createElement('option')
        opt.value = sid
        opt.textContent = sid
        select.appendChild(opt)
      }
      addSidebarSession(sid)
    }
  } catch { /* ignore */ }
}

loadSessionList()

// ── Connection badge ──────────────────────────────────────────────────────────
missionStore.subscribe((state) => {
  const dot   = document.getElementById('conn-dot')
  const label = document.getElementById('conn-label')
  if (dot)   dot.classList.toggle('live', state.connected)
  if (label) label.textContent = state.connected ? '实时' : '离线'
})

// ── New session button ────────────────────────────────────────────────────────
document.getElementById('new-session-btn')?.addEventListener('click', () => {
  if (wsClient) wsClient.disconnect()
  window.location.reload()
})

// ── Cleanup ───────────────────────────────────────────────────────────────────
window.addEventListener('beforeunload', () => {
  chatPanel.dispose()
  contractPanel.dispose()
  timelinePanel?.dispose()
  rpController.dispose()
  wsClient?.disconnect()
})
