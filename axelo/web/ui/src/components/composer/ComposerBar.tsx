import { useState } from 'react'

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

export function ComposerBar() {
  const [planMode, setPlanMode] = useState(false)

  return (
    <div className="absolute bottom-0 left-0 right-0 px-[52px] pb-[18px] pt-6 bg-gradient-to-t from-white via-white/90 to-transparent pointer-events-none">
      <div className="pointer-events-auto w-full bg-white border border-[#e0e0e0] rounded-[14px] shadow-[0_2px_14px_rgba(0,0,0,0.09),0_1px_4px_rgba(0,0,0,0.05)] overflow-hidden">

        <div className="flex items-center gap-2 px-3.5 pt-[11px] pb-[10px]">
          <span className="flex-1 text-[13.5px] text-[#9ca3af]">
            Describe a task or ask a question
          </span>
          <div className="flex items-center gap-1.5">
            <button className="w-[27px] h-[27px] rounded-md flex items-center justify-center text-[#c8c8c8] hover:bg-lavender-50 hover:text-lavender-500 transition-colors">
              <IconAttach />
            </button>
            <button className="w-[28px] h-[28px] rounded-[7px] bg-[#e5e7eb] flex items-center justify-center cursor-not-allowed">
              <span className="text-[#aaa]"><IconSend /></span>
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
              <Spinner />
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
