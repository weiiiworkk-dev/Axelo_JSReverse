function IconChat() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

function IconList() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  )
}

function IconCode() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  )
}

function IconPlus() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function IconRoutines() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="4" width="18" height="4" rx="1" />
      <rect x="3" y="11" width="18" height="4" rx="1" />
      <rect x="3" y="18" width="11" height="4" rx="1" />
    </svg>
  )
}

function IconCustomize() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v3m0 16v3M4.22 4.22l2.12 2.12m11.32 11.32 2.12 2.12M1 12h3m16 0h3M4.22 19.78l2.12-2.12M18.66 5.34l-2.12 2.12" />
    </svg>
  )
}

function IconMore() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="5" cy="12" r="1.2" fill="currentColor" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
      <circle cx="19" cy="12" r="1.2" fill="currentColor" />
    </svg>
  )
}

function IconGear() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v3m0 16v3M4.22 4.22l2.12 2.12m11.32 11.32 2.12 2.12M1 12h3m16 0h3M4.22 19.78l2.12-2.12M18.66 5.34l-2.12 2.12" />
    </svg>
  )
}

const railIcons = [
  { icon: <IconChat />, active: false },
  { icon: <IconList />, active: false },
  { icon: <IconCode />, active: true },
]

const navItems = [
  { label: 'New session', icon: <IconPlus /> },
  { label: 'Routines',    icon: <IconRoutines /> },
  { label: 'Customize',  icon: <IconCustomize /> },
]

export function NavCard() {
  return (
    <div className="flex bg-white border border-[#e2e2e2] rounded-[14px] shadow-[0_2px_10px_rgba(0,0,0,0.07),0_1px_3px_rgba(0,0,0,0.04)] overflow-hidden flex-shrink-0 h-full">

      {/* Icon Rail */}
      <div className="w-[46px] bg-[#fafafa] border-r border-[#efefef] flex flex-col items-center py-2.5 gap-0.5 flex-shrink-0">
        {railIcons.map(({ icon, active }, i) => (
          <button
            key={i}
            className={`w-[30px] h-[30px] rounded-[7px] flex items-center justify-center transition-colors ${
              active
                ? 'bg-lavender-100 text-lavender-600'
                : 'text-[#b0b0b0] hover:bg-[#eee] hover:text-[#444]'
            }`}
          >
            {icon}
          </button>
        ))}
        <div className="flex-1" />
        <div className="w-[26px] h-[26px] rounded-full bg-gradient-to-br from-lavender-400 to-lavender-600 text-white text-[10px] font-bold flex items-center justify-center cursor-pointer select-none">
          江
        </div>
      </div>

      {/* Sidebar */}
      <div className="w-[200px] flex flex-col">
        <div className="flex-1 overflow-y-auto no-scrollbar py-1.5">
          {navItems.map(({ label, icon }) => (
            <button
              key={label}
              className="w-[calc(100%-10px)] mx-[5px] my-[1px] px-[9px] py-[6px] rounded-[7px] text-[12.5px] text-[#374151] font-medium flex items-center gap-[7px] hover:bg-lavender-50 transition-colors text-left"
            >
              <span className="text-[#9ca3af]">{icon}</span>
              {label}
            </button>
          ))}

          <button className="w-[calc(100%-10px)] mx-[5px] my-[1px] px-[9px] py-[6px] rounded-[7px] text-[12.5px] text-[#aaa] flex items-center gap-[7px] hover:bg-lavender-50 transition-colors text-left">
            <span className="text-[#aaa]"><IconMore /></span>
            More
          </button>

          <div className="px-4 pt-3 pb-[3px] text-[10px] font-bold text-[#c8c8c8] tracking-[0.06em] uppercase">
            Pinned
          </div>
          <div className="px-4 pb-1.5 text-[11.5px] text-[#d8d8d8]">
            Drag to pin
          </div>

          <div className="px-4 pt-2 pb-[3px] text-[11.5px] font-medium text-[#9ca3af]">
            Axelo_JSReverse
          </div>
          <div className="w-[calc(100%-10px)] mx-[5px] my-[1px] px-[9px] py-[5px] rounded-[6px] text-[12px] text-[#6b7280] cursor-pointer hover:bg-lavender-50 hover:text-[#374151] transition-colors overflow-hidden text-ellipsis whitespace-nowrap">
            Review stress testing module for e-c...
          </div>
        </div>

        <div className="px-2.5 py-[9px] border-t border-[#f2f2f2] flex items-center justify-between flex-shrink-0">
          <span className="text-[12.5px] font-medium text-[#374151]">江薇</span>
          <button className="w-6 h-6 rounded-[6px] flex items-center justify-center text-[#ccc] hover:bg-lavender-50 hover:text-lavender-600 transition-colors">
            <IconGear />
          </button>
        </div>
      </div>

    </div>
  )
}
