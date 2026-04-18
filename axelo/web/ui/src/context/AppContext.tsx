import { createContext, useContext, useReducer, useEffect, useRef, ReactNode } from 'react'

export interface SessionSummary {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  status: string
  latest_run_id?: string
  latest_run_status?: string
}

export interface ThreadMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  ts: string
  actor?: string  // 'router' | 'agent-xxx' — 用于聊天气泡标签
}

export interface PlanStep {
  id: string
  label: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  agentId?: string
  note?: string
}

// 标准 9 步流水线（与后端 OBJECTIVE_TITLES 对应）
const DEFAULT_STEPS: PlanStep[] = [
  { id: 'consult_memory',            label: '查询记忆库',      status: 'pending' },
  { id: 'discover_surface',          label: '检测目标结构',    status: 'pending' },
  { id: 'recover_transport',         label: '恢复传输路径',    status: 'pending' },
  { id: 'recover_static_mechanism',  label: '分析静态机制',    status: 'pending' },
  { id: 'recover_runtime_mechanism', label: '检测运行时机制',  status: 'pending' },
  { id: 'recover_response_schema',   label: '映射响应结构',    status: 'pending' },
  { id: 'build_artifacts',           label: '构建爬虫产物',    status: 'pending' },
  { id: 'verify_execution',          label: '验证执行结果',    status: 'pending' },
  { id: 'challenge_findings',        label: '复核发现项',      status: 'pending' },
]

interface AppState {
  sessions: SessionSummary[]
  activeSessionId: string | null
  thread: ThreadMessage[]
  phase: string
  sending: boolean
  wsConnected: boolean
  streamingText: string | null
  // 执行面板
  isReady: boolean
  runId: string | null
  runStatus: 'idle' | 'running' | 'completed' | 'failed'
  planSteps: PlanStep[]
  rightPanelOpen: boolean
}

type Action =
  | { type: 'SET_SESSIONS'; sessions: SessionSummary[] }
  | { type: 'SET_ACTIVE'; sessionId: string; thread: ThreadMessage[]; phase: string }
  | { type: 'APPEND_MESSAGES'; messages: ThreadMessage[] }
  | { type: 'SET_SENDING'; value: boolean }
  | { type: 'SET_WS_CONNECTED'; value: boolean }
  | { type: 'PREPEND_SESSION'; session: SessionSummary }
  | { type: 'CLEAR_ACTIVE' }
  | { type: 'SET_PHASE'; phase: string }
  | { type: 'SET_STREAMING'; text: string }
  | { type: 'COMMIT_STREAMING'; id: string; ts: string }
  | { type: 'SET_READY'; isReady: boolean }
  | { type: 'OPEN_PANEL' }
  | { type: 'CLOSE_PANEL' }
  | { type: 'SET_RUN'; runId: string }
  | { type: 'SET_RUN_STATUS'; status: AppState['runStatus'] }
  | { type: 'UPDATE_STEP'; objective: string; status: PlanStep['status']; agentId?: string; note?: string }

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_SESSIONS':
      return { ...state, sessions: action.sessions }
    case 'SET_ACTIVE':
      return { ...state, activeSessionId: action.sessionId, thread: action.thread, phase: action.phase, streamingText: null }
    case 'APPEND_MESSAGES':
      return { ...state, thread: [...state.thread, ...action.messages] }
    case 'SET_SENDING':
      return { ...state, sending: action.value }
    case 'SET_WS_CONNECTED':
      return { ...state, wsConnected: action.value }
    case 'PREPEND_SESSION':
      return { ...state, sessions: [action.session, ...state.sessions] }
    case 'CLEAR_ACTIVE':
      return {
        ...state, activeSessionId: null, thread: [], phase: '',
        wsConnected: false, streamingText: null,
        isReady: false, runId: null, runStatus: 'idle',
        planSteps: DEFAULT_STEPS.map(s => ({ ...s })),
        rightPanelOpen: false,
      }
    case 'SET_PHASE':
      return { ...state, phase: action.phase }
    case 'SET_STREAMING':
      return { ...state, streamingText: action.text }
    case 'COMMIT_STREAMING': {
      if (state.streamingText === null) return state
      const msg: ThreadMessage = { id: action.id, role: 'assistant', content: state.streamingText, ts: action.ts }
      return { ...state, streamingText: null, thread: [...state.thread, msg] }
    }
    case 'SET_READY':
      return { ...state, isReady: action.isReady }
    case 'OPEN_PANEL':
      return { ...state, rightPanelOpen: true }
    case 'CLOSE_PANEL':
      return { ...state, rightPanelOpen: false }
    case 'SET_RUN':
      return { ...state, runId: action.runId, runStatus: 'running' }
    case 'SET_RUN_STATUS':
      return { ...state, runStatus: action.status }
    case 'UPDATE_STEP':
      return {
        ...state,
        planSteps: state.planSteps.map(s =>
          s.id === action.objective
            ? { ...s, status: action.status, agentId: action.agentId ?? s.agentId, note: action.note ?? s.note }
            : s
        ),
      }
    default:
      return state
  }
}

const initialState: AppState = {
  sessions: [],
  activeSessionId: null,
  thread: [],
  phase: '',
  sending: false,
  wsConnected: false,
  streamingText: null,
  isReady: false,
  runId: null,
  runStatus: 'idle',
  planSteps: DEFAULT_STEPS.map(s => ({ ...s })),
  rightPanelOpen: false,
}

interface AppContextValue {
  state: AppState
  loadSessions: () => Promise<void>
  openSession: (sessionId: string) => Promise<void>
  createSession: () => Promise<void>
  sendMessage: (text: string) => Promise<void>
  startRun: () => Promise<void>
  clearActive: () => void
  closePanel: () => void
}

const AppContext = createContext<AppContextValue | null>(null)

const API = ''

function historyToThread(
  history: Array<{
    role?: string; actor_type?: string; content?: string
    turn_id?: string; item_id?: string; ts?: string; created_at?: string
  }>
): ThreadMessage[] {
  return history.map((h, i) => {
    const role =
      h.role === 'user' || h.actor_type === 'user' ? 'user'
      : h.role === 'assistant' || h.actor_type === 'router' || h.actor_type === 'agent' ? 'assistant'
      : 'system'
    return {
      id: h.turn_id ?? h.item_id ?? String(i),
      role,
      content: h.content ?? '',
      ts: h.ts ?? h.created_at ?? '',
    }
  })
}

async function streamAiReply(
  text: string,
  dispatch: React.Dispatch<Action>,
  abortRef: { current: boolean }
): Promise<void> {
  const id = crypto.randomUUID()
  const ts = new Date().toISOString()
  const CHUNK = 4
  const DELAY = 18

  dispatch({ type: 'SET_STREAMING', text: '' })
  for (let i = CHUNK; i < text.length; i += CHUNK) {
    if (abortRef.current) return
    dispatch({ type: 'SET_STREAMING', text: text.slice(0, i) })
    await new Promise(r => setTimeout(r, DELAY))
  }
  if (abortRef.current) return
  dispatch({ type: 'SET_STREAMING', text })
  await new Promise(r => setTimeout(r, DELAY))
  if (!abortRef.current) dispatch({ type: 'COMMIT_STREAMING', id, ts })
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const wsRef = useRef<WebSocket | null>(null)      // intake WS (不接收 run 事件)
  const runWsRef = useRef<WebSocket | null>(null)   // run WS
  const streamAbortRef = useRef(false)
  // 用 ref 访问最新 state（避免闭包陈旧值）
  const stateRef = useRef(state)
  useEffect(() => { stateRef.current = state }, [state])

  const loadSessions = async () => {
    try {
      const res = await fetch(`${API}/api/sessions`)
      if (!res.ok) return
      const data: SessionSummary[] = await res.json()
      dispatch({ type: 'SET_SESSIONS', sessions: data })
    } catch { /* ignore */ }
  }

  const openSession = async (sessionId: string) => {
    try {
      const res = await fetch(`${API}/api/sessions/${sessionId}`)
      if (!res.ok) return
      const data = await res.json()
      const rawHistory = data.thread_items ?? data.history ?? []
      const thread = historyToThread(rawHistory)
      dispatch({ type: 'SET_ACTIVE', sessionId, thread, phase: data.status ?? data.phase ?? '' })
      const isReady = Boolean(data.ready_to_run)
      dispatch({ type: 'SET_READY', isReady })
      if (isReady) dispatch({ type: 'OPEN_PANEL' })
      connectIntakeWs(sessionId)
      // P2-E: 刷新重连 — 若会话已有进行中的 run，重新连接 run WS
      const existingRunId: string = data.current_run_id ?? ''
      const isExecuting = data.status === 'executing' || data.phase === 'executing'
      if (existingRunId && isExecuting) {
        dispatch({ type: 'SET_RUN', runId: existingRunId })
        dispatch({ type: 'OPEN_PANEL' })
        connectRunWs(existingRunId)
      }
    } catch { /* ignore */ }
  }

  const createSession = async () => {
    try {
      const res = await fetch(`${API}/api/sessions`, { method: 'POST' })
      if (!res.ok) return
      const data = await res.json()
      const sessionId = data.session_id
      dispatch({ type: 'PREPEND_SESSION', session: data as SessionSummary })
      dispatch({ type: 'SET_ACTIVE', sessionId, thread: [], phase: 'welcome' })
      connectIntakeWs(sessionId)
    } catch { /* ignore */ }
  }

  const sendMessage = async (text: string) => {
    const sessionId = stateRef.current.activeSessionId
    if (!sessionId || stateRef.current.sending) return
    streamAbortRef.current = false
    dispatch({ type: 'SET_SENDING', value: true })
    const userMsg: ThreadMessage = { id: crypto.randomUUID(), role: 'user', content: text, ts: new Date().toISOString() }
    dispatch({ type: 'APPEND_MESSAGES', messages: [userMsg] })
    try {
      const res = await fetch(`${API}/api/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      if (res.ok) {
        const data = await res.json()
        const aiReply: string = data.ai_reply ?? ''
        dispatch({ type: 'SET_SENDING', value: false })
        if (aiReply) await streamAiReply(aiReply, dispatch, streamAbortRef)

        // 解析 readiness：多路容错——ready_to_run / is_ready / phase===contract_ready
        const isReady = Boolean(
          data.session?.ready_to_run
          ?? data.readiness?.is_ready
          ?? (data.session?.phase === 'contract_ready' || data.phase === 'contract_ready')
        )
        if (isReady && !stateRef.current.isReady) {
          dispatch({ type: 'SET_READY', isReady: true })
          dispatch({ type: 'OPEN_PANEL' })
        }
        const newPhase = data.session?.phase ?? data.phase ?? ''
        if (newPhase) dispatch({ type: 'SET_PHASE', phase: newPhase })
      }
    } catch { /* ignore */ } finally {
      dispatch({ type: 'SET_SENDING', value: false })
    }
  }

  const startRun = async () => {
    const sessionId = stateRef.current.activeSessionId
    if (!sessionId) return
    try {
      const res = await fetch(`${API}/api/sessions/${sessionId}/runs`, { method: 'POST' })
      if (!res.ok) return
      const data = await res.json()
      const runId: string = data.run?.run_id ?? ''
      if (!runId) return
      dispatch({ type: 'SET_RUN', runId })
      dispatch({ type: 'SET_PHASE', phase: 'executing' })
      // 重置步骤为 pending 再开始
      DEFAULT_STEPS.forEach(s => dispatch({ type: 'UPDATE_STEP', objective: s.id, status: 'pending' }))
      connectRunWs(runId)
      // 系统提示消息
      const sysMsg: ThreadMessage = {
        id: crypto.randomUUID(), role: 'system',
        content: '▶ 任务已启动，Router AI 开始规划执行路径…', ts: new Date().toISOString(),
      }
      dispatch({ type: 'APPEND_MESSAGES', messages: [sysMsg] })
    } catch { /* ignore */ }
  }

  const connectIntakeWs = (sessionId: string) => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/sessions/${sessionId}/stream`)
    wsRef.current = ws
    ws.onopen = () => dispatch({ type: 'SET_WS_CONNECTED', value: true })
    ws.onclose = () => dispatch({ type: 'SET_WS_CONNECTED', value: false })
    ws.onerror = () => dispatch({ type: 'SET_WS_CONNECTED', value: false })
    ws.onmessage = (ev: MessageEvent) => handleRunEvent(ev.data)
  }

  const connectRunWs = (runId: string) => {
    if (runWsRef.current) { runWsRef.current.close(); runWsRef.current = null }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/sessions/${runId}/stream`)
    runWsRef.current = ws
    ws.onclose = () => {
      // 如果还在运行则尝试重连
      if (stateRef.current.runStatus === 'running') {
        setTimeout(() => {
          const currentRunId = stateRef.current.runId
          if (currentRunId) connectRunWs(currentRunId)
        }, 3000)
      }
    }
    ws.onmessage = (ev: MessageEvent) => handleRunEvent(ev.data)
  }

  const handleRunEvent = (raw: string) => {
    try {
      const event = JSON.parse(raw) as Record<string, unknown>
      const kind = String(event.kind ?? '')
      const payload = (event.payload ?? {}) as Record<string, unknown>
      const message = String(payload.message ?? event.message ?? '')
      const objective = String(payload.objective ?? '')
      const objectiveLabel = String(payload.objective_label ?? objective)
      const actorId = String(event.actor_id ?? '')
      const status = String(payload.status ?? '')
      const ts = String(event.ts ?? new Date().toISOString())
      const eventId = String(event.event_id ?? crypto.randomUUID())

      // 更新流水线步骤
      if (objective) {
        const stepStatus: PlanStep['status'] =
          status === 'completed' ? 'completed'
          : status === 'failed' ? 'failed'
          : status === 'blocked' ? 'blocked'
          : kind === 'agent.activity' ? 'running'
          : 'pending'
        dispatch({ type: 'UPDATE_STEP', objective, status: stepStatus, agentId: actorId, note: message || undefined })
      }

      // 聊天区消息
      if (kind === 'router.message' && message) {
        dispatch({ type: 'APPEND_MESSAGES', messages: [{ id: eventId, role: 'assistant', content: message, ts, actor: 'router' }] })
      } else if (kind === 'agent.activity' && message && !payload.transient) {
        const label = objectiveLabel ? `[${objectiveLabel}] ` : ''
        dispatch({ type: 'APPEND_MESSAGES', messages: [{ id: eventId, role: 'assistant', content: `${label}${message}`, ts, actor: actorId }] })
      } else if (kind === 'run.completed') {
        dispatch({ type: 'SET_RUN_STATUS', status: 'completed' })
        dispatch({ type: 'SET_PHASE', phase: 'completed' })
        // 把剩余 pending 步骤标为 completed
        stateRef.current.planSteps.forEach(s => {
          if (s.status === 'pending' || s.status === 'running') {
            dispatch({ type: 'UPDATE_STEP', objective: s.id, status: 'completed' })
          }
        })
        dispatch({ type: 'APPEND_MESSAGES', messages: [{ id: crypto.randomUUID(), role: 'system', content: '✅ 执行完成', ts, actor: 'system' }] })
      } else if (kind === 'run.failed') {
        dispatch({ type: 'SET_RUN_STATUS', status: 'failed' })
        dispatch({ type: 'SET_PHASE', phase: 'failed' })
        dispatch({ type: 'APPEND_MESSAGES', messages: [{ id: crypto.randomUUID(), role: 'system', content: '❌ 执行失败', ts, actor: 'system' }] })
      }
    } catch { /* ignore */ }
  }

  const clearActive = () => {
    streamAbortRef.current = true
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    if (runWsRef.current) { runWsRef.current.close(); runWsRef.current = null }
    dispatch({ type: 'CLEAR_ACTIVE' })
  }

  const closePanel = () => dispatch({ type: 'CLOSE_PANEL' })

  useEffect(() => {
    loadSessions()
    return () => {
      streamAbortRef.current = true
      if (wsRef.current) wsRef.current.close()
      if (runWsRef.current) runWsRef.current.close()
    }
  }, [])

  return (
    <AppContext.Provider value={{ state, loadSessions, openSession, createSession, sendMessage, startRun, clearActive, closePanel }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}
