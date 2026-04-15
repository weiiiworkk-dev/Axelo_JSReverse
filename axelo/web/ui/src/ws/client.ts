/**
 * WebSocket 客户端：连接后端 /ws/sessions/{id}/stream，
 * 将收到的事件 dispatch 到 missionStore。
 */
import { missionStore, SessionSnapshot, WsEvent } from '../store/missionStore'

let ws: WebSocket | null = null
let currentSessionId = ''
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

export function connectSession(sessionId: string): void {
  if (currentSessionId === sessionId && ws && ws.readyState === WebSocket.OPEN) return

  disconnectSession()
  currentSessionId = sessionId
  missionStore.selectSession(sessionId)
  void _bootstrapSession(sessionId).finally(() => _connect())
}

export function disconnectSession(): void {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  if (ws) { ws.close(); ws = null }
  missionStore.setConnected(false)
}

function _connect(): void {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${location.host}/ws/sessions/${currentSessionId}/stream`

  ws = new WebSocket(url)

  ws.onopen = () => {
    missionStore.setConnected(true)
    console.log('[WS] connected', currentSessionId)
  }

  ws.onmessage = (ev: MessageEvent) => {
    try {
      const event: WsEvent = normalizeEvent(JSON.parse(ev.data))
      missionStore.applyEvent(event)
    } catch (e) {
      console.warn('[WS] parse error', e)
    }
  }

  ws.onerror = (ev) => {
    console.warn('[WS] error', ev)
  }

  ws.onclose = () => {
    missionStore.setConnected(false)
    // 5 秒后自动重连
    reconnectTimer = setTimeout(() => {
      if (currentSessionId) _connect()
    }, 5000)
  }
}

async function _bootstrapSession(sessionId: string): Promise<void> {
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`)
    if (!res.ok) return
    const snapshot: SessionSnapshot = await res.json()
    missionStore.hydrateSession(snapshot)
  } catch (error) {
    console.warn('[WS] bootstrap session failed', error)
  }
}

function normalizeEvent(raw: Record<string, any>): WsEvent {
  // Flatten nested data fields into the event for new event kinds (reconciliation, verdict, risk, field_evidence)
  const data: Record<string, any> = raw.data || {}
  return {
    type: String(raw.type || 'engine_event'),
    kind: String(raw.kind || raw.data?.kind || 'info'),
    message: String(raw.message || ''),
    agentRole: raw.agentRole || raw.agent_role || data.agent_role || '',
    objective: raw.objective || data.objective || '',
    publishedAt: raw.publishedAt || raw.published_at || raw.ts || '',
    state: raw.state || data || {},
    // Pass through new fields for ExecutionTimelinePanel
    step: raw.step || data.step,
    tier: raw.tier || data.tier,
    actions: raw.actions || data.actions,
    field_evidence: raw.field_evidence || data.field_evidence,
    coverage_snapshot: raw.coverage_snapshot || data.coverage_snapshot,
  }
}

// Class-based wrapper for use in main.ts
export class WsClient {
  private sessionId: string

  constructor(sessionId: string) {
    this.sessionId = sessionId
  }

  connect(): void {
    connectSession(this.sessionId)
  }

  disconnect(): void {
    disconnectSession()
  }
}
