import { useEffect, useRef } from 'react'
import { useApp, ThreadMessage } from '../../context/AppContext'

// ── 气泡组件 ──────────────────────────────────────────────────────────────────

function ActorTag({ actor }: { actor: string }) {
  const isRouter = actor === 'router'
  return (
    <div className={`text-[10.5px] font-semibold mb-0.5 ml-1 ${
      isRouter ? 'text-lavender-400' : 'text-[#a0aec0]'
    }`}>
      {isRouter ? '✦ router' : `↳ ${actor}`}
    </div>
  )
}

function UserBubble({ msg }: { msg: ThreadMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-lavender-500 text-white rounded-[14px] rounded-br-[4px] px-4 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap">
        {msg.content}
      </div>
    </div>
  )
}

function AssistantBubble({ msg, streaming }: { msg: ThreadMessage; streaming?: boolean }) {
  return (
    <div className="flex flex-col items-start">
      {msg.actor && <ActorTag actor={msg.actor} />}
      <div className="max-w-[80%] bg-[#f3f4f6] text-[#111827] rounded-[14px] rounded-bl-[4px] px-4 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap">
        {msg.content}
        {streaming && (
          <span
            className="inline-block w-[2px] h-[14px] bg-lavender-500 ml-0.5 align-middle"
            style={{ animation: 'blink 0.8s step-end infinite' }}
          />
        )}
      </div>
      <style>{`@keyframes blink { 0%,100% { opacity:1 } 50% { opacity:0 } }`}</style>
    </div>
  )
}

// 系统通知条（任务启动、执行完成等）
function SystemNotice({ msg }: { msg: ThreadMessage }) {
  return (
    <div className="flex justify-center py-1">
      <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#f3f4f6] border border-[#e8e8e8]">
        <span className="text-[11.5px] text-[#6b7280] font-medium">{msg.content}</span>
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-[#f3f4f6] rounded-[14px] rounded-bl-[4px] px-4 py-3 flex gap-1 items-center">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-[#9ca3af]"
            style={{ animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite` }}
          />
        ))}
      </div>
      <style>{`@keyframes bounce { 0%,80%,100% { transform: scale(0.7); opacity:.5 } 40% { transform: scale(1); opacity:1 } }`}</style>
    </div>
  )
}

// ── 主工作区 ──────────────────────────────────────────────────────────────────

export function ConversationWorkspace() {
  const { state } = useApp()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.thread, state.sending, state.streamingText])

  const streamingMsg: ThreadMessage | null =
    state.streamingText !== null
      ? { id: '__streaming__', role: 'assistant', content: state.streamingText, ts: '' }
      : null

  return (
    <div className="flex-1 overflow-y-auto no-scrollbar px-[52px] pt-8 pb-[150px] flex flex-col gap-3">
      {state.thread.length === 0 && !state.sending && streamingMsg === null && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center">
          <div className="text-[32px]">🔍</div>
          <p className="text-[14px] text-[#9ca3af]">描述你要爬取的目标，或提出一个问题</p>
        </div>
      )}

      {state.thread.map((msg) => {
        if (msg.role === 'user') return <UserBubble key={msg.id} msg={msg} />
        if (msg.role === 'system') return <SystemNotice key={msg.id} msg={msg} />
        return <AssistantBubble key={msg.id} msg={msg} />
      })}

      {state.sending && <TypingIndicator />}
      {streamingMsg && <AssistantBubble msg={streamingMsg} streaming />}
      <div ref={bottomRef} />
    </div>
  )
}
