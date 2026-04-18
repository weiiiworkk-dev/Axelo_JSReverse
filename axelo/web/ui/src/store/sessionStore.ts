import { applyRunEventToThread } from '../projectors/runEvents'
import type { RunEvent, SessionSummary, SessionView } from '../workbench/types'

interface SessionState {
  sessions: SessionSummary[]
  current: SessionView | null
  loading: boolean
  sending: boolean
  error: string
}

type Listener = (state: SessionState) => void

class SessionStore {
  private state: SessionState = {
    sessions: [],
    current: null,
    loading: false,
    sending: false,
    error: '',
  }

  private listeners = new Set<Listener>()

  getState(): SessionState { return this.state }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private patch(patch: Partial<SessionState>): void {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach(listener => listener(this.state))
  }

  async refreshSessions(): Promise<void> {
    const resp = await fetch('/api/sessions')
    const data = await resp.json()
    this.patch({ sessions: Array.isArray(data) ? data : [] })
  }

  async createSession(): Promise<void> {
    this.patch({ loading: true, error: '' })
    try {
      const resp = await fetch('/api/sessions', { method: 'POST' })
      const summary = await resp.json() as SessionSummary
      await this.refreshSessions()
      await this.loadSession(summary.session_id)
    } catch (error: any) {
      this.patch({ error: String(error?.message || error) })
    } finally {
      this.patch({ loading: false })
    }
  }

  async loadSession(sessionId: string): Promise<void> {
    this.patch({ loading: true, error: '' })
    try {
      const resp = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`)
      if (!resp.ok) throw new Error(`Failed to load session ${sessionId}`)
      const data = await resp.json() as SessionView
      data.thread_items = Array.isArray(data.thread_items) ? data.thread_items : []
      this.patch({ current: data })
      await this.refreshSessions()
    } catch (error: any) {
      this.patch({ error: String(error?.message || error) })
    } finally {
      this.patch({ loading: false })
    }
  }

  async sendMessage(message: string): Promise<void> {
    const current = this.state.current
    if (!current) return
    this.patch({ sending: true, error: '' })
    try {
      const resp = await fetch(`/api/sessions/${encodeURIComponent(current.session_id)}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (!resp.ok) throw new Error(`Failed to send message (${resp.status})`)
      const data = await resp.json()
      this.patch({ current: data.session })
      await this.refreshSessions()
    } catch (error: any) {
      this.patch({ error: String(error?.message || error) })
    } finally {
      this.patch({ sending: false })
    }
  }

  async startRun(): Promise<string> {
    const current = this.state.current
    if (!current) throw new Error('No active session')
    this.patch({ sending: true, error: '' })
    try {
      const resp = await fetch(`/api/sessions/${encodeURIComponent(current.session_id)}/runs`, { method: 'POST' })
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(String(payload.detail || resp.statusText))
      }
      const data = await resp.json()
      await this.loadSession(current.session_id)
      return String(data.run?.run_id || '')
    } finally {
      this.patch({ sending: false })
    }
  }

  applyRunEvent(event: RunEvent): void {
    const current = this.state.current
    if (!current || current.session_id !== event.session_id) return
    const threadItems = applyRunEventToThread(current.thread_items || [], event)
    const nextRunIds = current.run_ids || []
    if (event.run_id && !nextRunIds.includes(event.run_id)) nextRunIds.push(event.run_id)
    this.patch({
      current: {
        ...current,
        current_run_id: event.run_id || current.current_run_id,
        run_ids: nextRunIds,
        thread_items: threadItems,
      },
    })
  }
}

export const sessionStore = new SessionStore()
