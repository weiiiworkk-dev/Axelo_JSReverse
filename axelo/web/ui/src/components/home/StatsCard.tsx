import { useState, useEffect } from 'react'
import { Heatmap } from './Heatmap'

type Tab = 'Overview' | 'Models'
type Filter = 'All' | '30d' | '7d'

interface Stats {
  sessions: string | number
  messages: string | number
  total_tokens: string | number
  active_days: string | number
  current_streak: string
  longest_streak: string
  peak_hour: string
  favorite_model: string
}

const EMPTY: Stats = {
  sessions: '—', messages: '—', total_tokens: '—', active_days: '—',
  current_streak: '—', longest_streak: '—', peak_hour: '—', favorite_model: '—',
}

export function StatsCard() {
  const [tab, setTab] = useState<Tab>('Overview')
  const [filter, setFilter] = useState<Filter>('All')
  const [stats, setStats] = useState<Stats>(EMPTY)

  useEffect(() => {
    fetch('/api/stats')
      .then((r) => r.ok ? r.json() : null)
      .then((data) => { if (data) setStats(data) })
      .catch(() => { /* ignore */ })
  }, [])

  const rows = [
    { label: 'Sessions',       value: String(stats.sessions) },
    { label: 'Messages',       value: String(stats.messages) },
    { label: 'Total tokens',   value: String(stats.total_tokens) },
    { label: 'Active days',    value: String(stats.active_days) },
    { label: 'Current streak', value: stats.current_streak },
    { label: 'Longest streak', value: stats.longest_streak },
    { label: 'Peak hour',      value: stats.peak_hour },
    { label: 'Favorite model', value: stats.favorite_model, small: true },
  ]

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
        {rows.map((s) => (
          <div key={s.label}>
            <div className="text-[11px] text-[#9ca3af] mb-0.5">{s.label}</div>
            <div className={`font-bold text-[#111827] tracking-tight ${s.small ? 'text-[12.5px]' : 'text-[15px]'}`}>
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
