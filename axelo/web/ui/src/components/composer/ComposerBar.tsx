import { useState, useRef, KeyboardEvent } from 'react'
import { useApp } from '../../context/AppContext'

function IconAttach() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  )
}

function IconSend() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="5 12 12 5 19 12" />
    </svg>
  )
}

function IconPlay() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  )
}

function IconChevron() {
  return (
    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

function IconCircle() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="10" />
    </svg>
  )
}

function IconPlus() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function Spinner() {
  return (
    <>
      <div
        className="w-3 h-3 rounded-full border-[1.5px] border-[#d1d5db] border-t-lavender-500"
        style={{ animation: 'spin 0.9s linear infinite' }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  )
}

// "开始执行" 按钮 — 当 AI 确认任务就绪且尚未开始运行时显示
function StartButton({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-1.5 px-3 py-[5px] rounded-[8px] text-[12px] font-semibold transition-all ${
        disabled
          ? 'bg-[#e5e7eb] text-[#aaa] cursor-not-allowed'
          : 'bg-lavender-500 text-white hover:bg-lavender-600 cursor-pointer shadow-sm'
      }`}
    >
      <IconPlay />
      开始执行
    </button>
  )
}

export function ComposerBar() {
  const { state, sendMessage, createSession, startRun } = useApp()
  const [text, setText] = useState('')
  const [planMode, setPlanMode] = useState(false)
  const [starting, setStarting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const canSend = text.trim().length > 0 && !state.sending && state.runStatus === 'idle'
  const showStart = state.isReady && state.runStatus === 'idle' && !!state.activeSessionId

  const handleSend = async () => {
    if (!canSend) return
    const msg = text.trim()
    setText('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    if (!state.activeSessionId) await createSession()
    await sendMessage(msg)
  }

  const handleStart = async () => {
    if (starting) return
    setStarting(true)
    try { await startRun() } finally { setStarting(false) }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  const isExecuting = state.runStatus === 'running'

  return (
    <div className="absolute bottom-0 left-0 right-0 px-[52px] pb-[18px] pt-6 bg-gradient-to-t from-white via-white/90 to-transparent pointer-events-none">
      <div className="pointer-events-auto w-full bg-white border border-[#e0e0e0] rounded-[14px] shadow-[0_2px_14px_rgba(0,0,0,0.09),0_1px_4px_rgba(0,0,0,0.05)] overflow-hidden">

        <div className="flex items-end gap-2 px-3.5 pt-[11px] pb-[10px]">
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onInput={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={isExecuting ? '执行中，请稍候…' : 'Describe a task or ask a question'}
            disabled={isExecuting}
            className="flex-1 resize-none bg-transparent outline-none text-[13.5px] text-[#111827] placeholder:text-[#9ca3af] leading-relaxed max-h-[120px] overflow-y-auto disabled:opacity-50"
            style={{ minHeight: '22px' }}
          />
          <div className="flex items-center gap-1.5 flex-shrink-0 mb-[1px]">
            <button
              disabled={isExecuting}
              className="w-[27px] h-[27px] rounded-md flex items-center justify-center text-[#c8c8c8] hover:bg-lavender-50 hover:text-lavender-500 transition-colors disabled:opacity-40"
            >
              <IconAttach />
            </button>
            <button
              onClick={handleSend}
              disabled={!canSend}
              className={`w-[28px] h-[28px] rounded-[7px] flex items-center justify-center transition-colors ${
                canSend
                  ? 'bg-lavender-500 text-white hover:bg-lavender-600 cursor-pointer'
                  : 'bg-[#e5e7eb] cursor-not-allowed'
              }`}
            >
              <span className={canSend ? 'text-white' : 'text-[#aaa]'}><IconSend /></span>
            </button>
          </div>
        </div>

        <div className="flex items-center gap-1.5 px-2.5 pb-2 pt-1.5 border-t border-[#f3f4f6]">
          <button className="flex items-center gap-1 px-[9px] py-[3px] rounded-md border border-[#e5e7eb] text-[12px] text-[#374151] font-medium hover:bg-lavender-50 transition-colors">
            <span className="text-[#9ca3af]"><IconCircle /></span>
            Default
            <span className="text-[#9ca3af]"><IconChevron /></span>
          </button>

          <button className="flex items-center gap-1 px-[9px] py-[3px] rounded-md border border-[#eee] text-[12px] text-[#9ca3af] hover:bg-lavender-50 transition-colors">
            <IconPlus />
            Select repo...
          </button>

          <div className="ml-auto flex items-center gap-2.5">
            {/* "开始执行" 按钮 — 就绪且未开始时显示 */}
            {showStart && (
              <StartButton onClick={handleStart} disabled={starting} />
            )}

            <label className="flex items-center gap-1.5 text-[12px] text-[#6b7280] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={planMode}
                onChange={(e) => setPlanMode(e.target.checked)}
                className="w-[13px] h-[13px] accent-lavender-600"
              />
              Plan mode
            </label>
            <div className="flex items-center gap-1.5 text-[12px] text-[#6b7280] font-medium">
              Sonnet 4.6
              {state.sending || starting ? <Spinner /> : (
                <div className="w-3 h-3 rounded-full border-[1.5px] border-[#d1d5db]" />
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
