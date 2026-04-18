import { useEffect, useRef, useSyncExternalStore } from 'react'
import { runStore } from '../store/runStore'
import { sessionStore } from '../store/sessionStore'
import { RunClient } from '../ws/runClient'
import { ConversationWorkspace } from '../components/ConversationWorkspace'
import { HomeWorkspace } from '../components/HomeWorkspace'
import { Sidebar } from '../components/Sidebar'
import { SystemRail } from '../components/SystemRail'

interface StoreLike<T> {
  getState: () => T
  subscribe: (listener: (state: T) => void) => () => void
}

function useStoreSnapshot<T>(store: StoreLike<T>): T {
  return useSyncExternalStore(
    (listener) => store.subscribe(() => listener()),
    () => store.getState(),
    () => store.getState(),
  )
}

export function App() {
  const sessionState = useStoreSnapshot(sessionStore)
  const runState = useStoreSnapshot(runStore)
  const bootstrappedRef = useRef(false)
  const runClientRef = useRef<RunClient | null>(null)

  useEffect(() => {
    const client = new RunClient()
    runClientRef.current = client

    return () => {
      client.disconnect()
      runClientRef.current = null
    }
  }, [])

  useEffect(() => {
    if (bootstrappedRef.current) return
    bootstrappedRef.current = true

    void (async () => {
      await sessionStore.refreshSessions()
      sessionStore.openHome()
    })()
  }, [])

  const currentSession = sessionState.current
  const inConversation = Boolean(currentSession && ((currentSession.thread_items?.length ?? 0) > 0 || currentSession.current_run_id))

  async function openSession(sessionId: string): Promise<void> {
    runClientRef.current?.disconnect()
    runStore.reset()

    await sessionStore.loadSession(sessionId)
    const current = sessionStore.getState().current

    if (current?.current_run_id) {
      await runStore.loadRun(current.current_run_id)
    } else if (current?.session_id && current.status !== 'welcome') {
      try {
        await runStore.loadRun(current.session_id)
      } catch {
        runStore.reset()
      }
    }

    const runId = runStore.getState().current?.run_id || ''
    if (runId) {
      runClientRef.current?.connect(runId, runStore.getState().current?.last_seq || 0)
    }
  }

  async function handleSend(message: string): Promise<void> {
    if (!sessionStore.getState().current) {
      await sessionStore.createSession()
    }

    await sessionStore.sendMessage(message)
  }

  async function handleStartRun(): Promise<void> {
    const runId = await sessionStore.startRun()
    if (!runId) return

    await runStore.loadRun(runId)
    runClientRef.current?.connect(runId, runStore.getState().current?.last_seq || 0)
  }

  function handleNewChat(): void {
    runClientRef.current?.disconnect()
    runStore.reset()
    sessionStore.openHome()
  }

  return (
    <div className="min-h-screen bg-[#f4efeb] p-2 sm:p-3">
      <div
        className={[
          'mx-auto grid min-h-[calc(100vh-16px)] max-w-[1440px] overflow-hidden rounded-[18px] border border-[#ebe4de] bg-[#fffdfa] shadow-[0_18px_48px_rgba(52,40,29,0.04)] sm:min-h-[calc(100vh-24px)]',
          inConversation ? 'lg:grid-cols-[214px,minmax(0,1fr),292px]' : 'lg:grid-cols-[214px,minmax(0,1fr)]',
        ].join(' ')}
      >
        <Sidebar
          currentSessionId={currentSession?.session_id || ''}
          sessions={sessionState.sessions}
          onNewChat={handleNewChat}
          onOpenSession={openSession}
        />

        {inConversation ? (
          <ConversationWorkspace
            current={currentSession}
            error={sessionState.error}
            onSend={handleSend}
            onStartRun={handleStartRun}
            sending={sessionState.sending}
          />
        ) : (
          <HomeWorkspace
            error={sessionState.error}
            onSend={handleSend}
            sending={sessionState.sending}
          />
        )}

        {inConversation ? <SystemRail runState={runState} /> : null}
      </div>
    </div>
  )
}
