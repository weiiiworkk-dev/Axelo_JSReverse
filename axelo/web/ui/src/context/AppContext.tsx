import { createContext, useContext, useReducer, useEffect, useRef, ReactNode } from 'react'

export interface SessionSummary {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  status: string
  latest_run_id: string
  latest_run_status: string
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
}

type Action =
  | { type: 'SET_SESSIONS'; sessions: SessionSummary[] }
  | { type: 'SET_ACTIVE'; sessionId: string; thread: ThreadMessage[]; phase: string }
  | { type: 'APPEND_MESSAGES'; messages: ThreadMessage[] }
  | { type: 'SET_SENDING'; value: boolean }
  | { type: 'SET_WS_CONNECTED'; value: boolean }
  | { type: 'PREPEND_SESSION'; session: SessionSummary }
  | { type: 'CLEAR_ACTIVE' }

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_SESSIONS':
      return { ...state, sessions: action.sessions }
    case 'SET_ACTIVE':
      return { ...state, activeSessionId: action.sessionId, thread: action.thread, phase: action.phase }
    case 'APPEND_MESSAGES':
      return { ...state, thread: [...state.thread, ...action.messages] }
    case 'SET_SENDING':
      return { ...state, sending: action.value }
    case 'SET_WS_CONNECTED':
      return { ...state, wsConnected: action.value }
    case 'PREPEND_SESSION':
      return { ...state, sessions: [action.session, ...state.sessions] }
    case 'CLEAR_ACTIVE':
      return { ...state, activeSessionId: null, thread: [], phase: '', wsConnected: false }
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

function historyToThread(history: Array<{ role: string; content: string; turn_id?: string; ts?: string }>): ThreadMessage[] {
  return history.map((h, i) => ({
    id: h.turn_id ?? String(i),
    role: h.role === 'user' ? 'user' : h.role === 'assistant' ? 'assistant' : 'system',
    content: h.content ?? '',
    ts: h.ts ?? '',
  }))
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const wsRef = useRef<WebSocket | null>(null)

  const loadSessions = async () => {
    try {
      const res = await fetch(`${API}/api/sessions`)
      if (!res.ok) return
      const data: SessionSummary[] = await res.json()
      dispatch({ type: 'SET_SESSIONS', sessions: data })
    } catch { /* network error, ignore */ }
  }

  const openSession = async (sessionId: string) => {
    try {
      const res = await fetch(`${API}/api/sessions/${sessionId}`)
      if (!res.ok) return
      const data = await res.json()
      const history = data.history ?? data.thread_items ?? []
      const thread = historyToThread(history)
      dispatch({ type: 'SET_ACTIVE', sessionId, thread, phase: data.phase ?? data.status ?? '' })
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
    dispatch({ type: 'SET_SENDING', value: true })
    const userMsg: ThreadMessage = { id: crypto.randomUUID(), role: 'user', content: text, ts: new Date().toISOString() }
    dispatch({ type: 'APPEND_MESSAGES', messages: [userMsg] })
    try {
      const res = await fetch(`${API}/api/sessions/${state.activeSessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      if (res.ok) {
        const data = await res.json()
        const aiReply = data.ai_reply ?? ''
        if (aiReply) {
          const aiMsg: ThreadMessage = { id: crypto.randomUUID(), role: 'assistant', content: aiReply, ts: new Date().toISOString() }
          dispatch({ type: 'APPEND_MESSAGES', messages: [aiMsg] })
        }
        if (data.session?.phase) {
          dispatch({ type: 'SET_ACTIVE', sessionId: state.activeSessionId, thread: state.thread, phase: data.session.phase })
        }
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
  }

  const clearActive = () => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    dispatch({ type: 'CLEAR_ACTIVE' })
  }

  useEffect(() => {
    loadSessions()
    return () => {
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
