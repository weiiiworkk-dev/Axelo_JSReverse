import { initialRightPanelState, applyAgentEvent } from './reducer'
import type { RightPanelState, AgentEvent, DirtyCard } from './types'

type Listener = (state: RightPanelState, dirty: DirtyCard[]) => void

class RightPanelStore {
  private state: RightPanelState = initialRightPanelState()
  private listeners: Set<Listener> = new Set()

  getState(): RightPanelState {
    return this.state
  }

  dispatch(event: AgentEvent): void {
    const { state, dirty } = applyAgentEvent(this.state, event)
    this.state = state
    if (dirty.length > 0) {
      this.listeners.forEach(fn => fn(this.state, dirty))
    }
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  reset(): void {
    this.state = initialRightPanelState()
    this.listeners.forEach(fn => fn(this.state, ['goal', 'plan', 'timeline', 'checkpoint']))
  }
}

export const rightPanelStore = new RightPanelStore()
