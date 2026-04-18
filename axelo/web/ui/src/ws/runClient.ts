import { runStore } from '../store/runStore'
import { sessionStore } from '../store/sessionStore'
import type { RunEvent } from '../workbench/types'

export class RunClient {
  private ws: WebSocket | null = null
  private runId = ''
  private reconnectTimer: number | null = null
  private lastSeq = 0

  connect(runId: string, lastSeq = 0): void {
    this.disconnect()
    this.runId = runId
    this.lastSeq = lastSeq
    this.open()
  }

  disconnect(): void {
    if (this.reconnectTimer != null) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    runStore.setConnected(false)
  }

  private open(): void {
    if (!this.runId) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/ws/runs/${encodeURIComponent(this.runId)}?cursor=${this.lastSeq}`
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      runStore.setConnected(true)
    }

    this.ws.onmessage = (message: MessageEvent) => {
      try {
        const event = JSON.parse(message.data) as RunEvent
        if (!event.session_id) {
          event.session_id = sessionStore.getState().current?.session_id || ''
        }
        this.lastSeq = Math.max(this.lastSeq, Number(event.seq || 0))
        runStore.applyEvent(event)
        sessionStore.applyRunEvent(event)
      } catch (error) {
        console.warn('[RunClient] unable to parse event', error)
      }
    }

    this.ws.onclose = () => {
      runStore.setConnected(false)
      this.reconnectTimer = window.setTimeout(() => this.open(), 1500)
    }

    this.ws.onerror = () => {
      runStore.setConnected(false)
    }
  }
}
