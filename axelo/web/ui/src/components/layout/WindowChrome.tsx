export function WindowChrome() {
  return (
    <div className="h-9 bg-[#e8e8e8] border-b border-[#d8d8d8] flex items-center px-3 gap-2 flex-shrink-0 select-none">
      <div className="flex gap-1.5">
        <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
        <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
        <div className="w-3 h-3 rounded-full bg-[#28c840]" />
      </div>

      <div className="flex gap-0.5 ml-2">
        {(['‹', '›'] as const).map((arrow) => (
          <button
            key={arrow}
            className="w-6 h-5 rounded flex items-center justify-center text-[#999] text-sm hover:bg-[#ddd] hover:text-[#333] transition-colors"
          >
            {arrow}
          </button>
        ))}
      </div>

      <div className="flex gap-0.5 ml-1">
        <button className="px-2.5 py-0.5 rounded text-xs text-[#888] font-medium hover:text-[#555] transition-colors">
          Chat
        </button>
        <button className="px-2.5 py-0.5 rounded text-xs bg-[#d8d8d8] text-[#222] font-semibold">
          Scrape
        </button>
      </div>
    </div>
  )
}
