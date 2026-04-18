import { useEffect, useRef } from 'react'
import { useApp, ThreadMessage } from '../../context/AppContext'

function UserBubble({ msg }: { msg: ThreadMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-lavender-500 text-white rounded-[14px] rounded-br-[4px] px-4 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap">
        {msg.content}
      </div>
    </div>
  )
}

function AssistantBubble({ msg }: { msg: ThreadMessage }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] bg-[#f3f4f6] text-[#111827] rounded-[14px] rounded-bl-[4px] px-4 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap">
        {msg.content}
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

export function ConversationWorkspace() {
  const { state } = useApp()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.thread, state.sending])

  return (
    <div className="flex-1 overflow-y-auto no-scrollbar px-[52px] pt-8 pb-[150px] flex flex-col gap-3">
      {state.thread.length === 0 && !state.sending && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center">
          <div className="text-[32px]">🔍</div>
          <p className="text-[14px] text-[#9ca3af]">描述你要爬取的目标，或提出一个问题</p>
        </div>
      )}
      {state.thread.map((msg) =>
        msg.role === 'user'
          ? <UserBubble key={msg.id} msg={msg} />
          : <AssistantBubble key={msg.id} msg={msg} />
      )}
      {state.sending && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  )
}
