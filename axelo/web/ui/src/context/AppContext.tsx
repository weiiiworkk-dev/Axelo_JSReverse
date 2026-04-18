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
}

interface AppState {
  sessions: SessionSummary[]
  activeSessionId: string | null
  thread: ThreadMessage[]
  phase: string
  sending: boolean
  wsConnected: boolean
  streamingText: string | null  // null = 不在流式中；'' 或文字 = 正在流式
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
      return { ...state, activeSessionId: null, thread: [], phase: '', wsConnected: false, streamingText: null }
    case 'SET_PHASE':
      return { ...state, phase: action.phase }
    case 'SET_STREAMING':
      return { ...state, streamingText: action.text }
    case 'COMMIT_STREAMING': {
      if (state.streamingText === null) return state
      const msg: ThreadMessage = { id: action.id, role: 'assistant', content: state.streamingText, ts: action.ts }
      return { ...state, streamingText: null, thread: [...state.thread, msg] }
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
}

interface AppContextValue {
  state: AppState
  loadSessions: () => Promise<void>
  openSession: (sessionId: string) => Promise<void>
  createSession: () => Promise<void>
  sendMessage: (text: string) => Promise<void>
  clearActive: () => void
}

const AppContext = createContext<AppContextValue | null>(null)

const API = ''

// 将后端返回的历史数组（ChatThreadItem 或旧 history 格式）统一映射为 ThreadMessage
function historyToThread(
  history: Array<{
    role?: string
    actor_type?: string
    content?: string
    turn_id?: string
    item_id?: string
    ts?: string
    created_at?: string
  }>
): ThreadMessage[] {
  return history.map((h, i) => {
    const role =
      h.role === 'user' || h.actor_type === 'user'
        ? 'user'
        : h.role === 'assistant' || h.actor_type === 'router' || h.actor_type === 'agent'
        ? 'assistant'
        : 'system'
    return {
      id: h.turn_id ?? h.item_id ?? String(i),
      role,
      content: h.content ?? '',
      ts: h.ts ?? h.created_at ?? '',
    }
  })
}

// 逐字符流式显示 AI 回复，模拟打字效果
async function streamAiReply(
  text: string,
  dispatch: React.Dispatch<Action>,
  abortRef: { current: boolean }
): Promise<void> {
  const id = crypto.randomUUID()
  const ts = new Date().toISOString()
  const CHUNK = 4   // 每次显示字符数
  const DELAY = 18  // ms 间隔，约 220 字符/秒

  dispatch({ type: 'SET_STREAMING', text: '' })

  for (let i = CHUNK; i < text.length; i += CHUNK) {
    if (abortRef.current) return
    dispatch({ type: 'SET_STREAMING', text: text.slice(0, i) })
    await new Promise(r => setTimeout(r, DELAY))
  }

  if (abortRef.current) return
  dispatch({ type: 'SET_STREAMING', text })
  await new Promise(r => setTimeout(r, DELAY))
  if (!abortRef.current) {
    dispatch({ type: 'COMMIT_STREAMING', id, ts })
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const wsRef = useRef<WebSocket | null>(null)
  const streamAbortRef = useRef(false)

  const loadSessions = async () => {
    try {
      const res = await fetch(`${API}/api/sessions`)
      if (!res.ok) return
      const data: SessionSummary[] = await res.json()
      dispatch({ type: 'SET_SESSIONS', sessions: data })
    } catch { /* network error */ }
  }

  const openSession = async (sessionId: string) => {
    try {
      const res = await fetch(`${API}/api/sessions/${sessionId}`)
      if (!res.ok) return
      const data = await res.json()
      // 兼容 thread_items（ChatThreadItem）和旧 history 两种格式
      const rawHistory = data.thread_items ?? data.history ?? []
      const thread = historyToThread(rawHistory)
      dispatch({ type: 'SET_ACTIVE', sessionId, thread, phase: data.status ?? data.phase ?? '' })
      connectWs(sessionId)
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
      connectWs(sessionId)
    } catch { /* ignore */ }
  }

  const sendMessage = async (text: string) => {
    if (!state.activeSessionId || state.sending) return
    streamAbortRef.current = false
    dispatch({ type: 'SET_SENDING', value: true })
    const userMsg: ThreadMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      ts: new Date().toISOString(),
    }
    dispatch({ type: 'APPEND_MESSAGES', messages: [userMsg] })
    try {
      const res = await fetch(`${API}/api/sessions/${state.activeSessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      if (res.ok) {
        const data = await res.json()
        const aiReply: string = data.ai_reply ?? ''
        // 先关闭 loading，再流式显示
        dispatch({ type: 'SET_SENDING', value: false })
        if (aiReply) {
          await streamAiReply(aiReply, dispatch, streamAbortRef)
        }
        // 只更新 phase，不重置 thread
        const newPhase = data.session?.phase ?? data.phase ?? ''
        if (newPhase) dispatch({ type: 'SET_PHASE', phase: newPhase })
      }
    } catch { /* ignore */ } finally {
      dispatch({ type: 'SET_SENDING', value: false })
    }
  }

  const connectWs = (sessionId: string) => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const ws = new WebSocket(`${proto}//${host}/ws/sessions/${sessionId}/stream`)
    wsRef.current = ws

    ws.onopen = () => dispatch({ type: 'SET_WS_CONNECTED', value: true })
    ws.onclose = () => dispatch({ type: 'SET_WS_CONNECTED', value: false })
    ws.onerror = () => dispatch({ type: 'SET_WS_CONNECTED', value: false })

    ws.onmessage = (ev: MessageEvent) => {
      try {
        const event = JSON.parse(ev.data as string) as Record<string, unknown>
        const kind = String(event.kind ?? '')
        const payload = (event.payload ?? {}) as Record<string, unknown>
        const message = String(payload.message ?? event.message ?? '')

        // 运行阶段：router/agent 活动消息追加到对话
        if ((kind === 'router.message' || kind === 'agent.activity') && message) {
          const msg: ThreadMessage = {
            id: String(event.event_id ?? crypto.randomUUID()),
            role: 'assistant',
            content: message,
            ts: String(event.ts ?? new Date().toISOString()),
          }
          dispatch({ type: 'APPEND_MESSAGES', messages: [msg] })
        }

        // 运行结束
        if (kind === 'run.completed' || kind === 'run.failed') {
          const phase = kind === 'run.completed' ? 'completed' : 'failed'
          dispatch({ type: 'SET_PHASE', phase })
        }
      } catch { /* ignore malformed events */ }
    }
  }

  const clearActive = () => {
    streamAbortRef.current = true
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    dispatch({ type: 'CLEAR_ACTIVE' })
  }

  useEffect(() => {
    loadSessions()
    return () => {
      streamAbortRef.current = true
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  return (
    <AppContext.Provider value={{ state, loadSessions, openSession, createSession, sendMessage, clearActive }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}
