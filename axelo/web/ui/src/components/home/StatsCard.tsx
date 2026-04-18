import { useState } from 'react'
import { Heatmap } from './Heatmap'

type Tab = 'Overview' | 'Models'
type Filter = 'All' | '30d' | '7d'

const STATS = [
  { label: 'Sessions',       value: '—' },
  { label: 'Messages',       value: '—' },
  { label: 'Total tokens',   value: '—' },
  { label: 'Active days',    value: '—' },
  { label: 'Current streak', value: '—' },
  { label: 'Longest streak', value: '—' },
  { label: 'Peak hour',      value: '—' },
  { label: 'Favorite model', value: '—', small: true },
] as const

export function StatsCard() {
  const [tab, setTab] = useState<Tab>('Overview')
  const [filter, setFilter] = useState<Filter>('All')

  return (
    <div className="w-[620px] border border-[#e5e7eb] rounded-xl bg-white shadow-[0_1px_3px_rgba(0,0,0,0.05)] overflow-hidden flex-shrink-0">

      <div className="flex items-center justify-between px-3.5 py-2 border-b border-[#f2f2f2]">
        <div className="flex gap-0.5">
          {(['Overview', 'Models'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-2.5 py-1 rounded-md text-[13px] transition-colors ${
                tab === t
                  ? 'bg-[#f3f4f6] text-[#111827] font-semibold'
                  : 'font-medium text-[#9ca3af] hover:text-[#555]'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="flex gap-0.5">
          {(['All', '30d', '7d'] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-0.5 rounded text-[12px] transition-colors ${
                filter === f
                  ? 'bg-[#f3f4f6] text-[#374151] font-semibold'
                  : 'font-medium text-[#c0c0c0] hover:text-[#888]'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-4 px-4 pt-3.5 pb-2.5 gap-y-3.5 border-b border-[#f5f5f5]">
        {STATS.map((s) => (
          <div key={s.label}>
            <div className="text-[11px] text-[#9ca3af] mb-0.5">{s.label}</div>
            <div className={`font-bold text-[#111827] tracking-tight ${'small' in s && s.small ? 'text-[12.5px]' : 'text-[15px]'}`}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      <div className="px-4 pt-3 pb-2.5 border-b border-[#f5f5f5]">
        <Heatmap />
      </div>

      <div className="px-4 py-2 text-[11.5px] text-[#b8b8b8] text-center">
        You've used ~0× more tokens than Moby-Dick.
      </div>
    </div>
  )
}
