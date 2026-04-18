import type { SessionSummary } from '../workbench/types'
import {
  ClockIcon,
  FilePlusIcon,
  FolderIcon,
  GridIcon,
  PlugIcon,
  SearchIcon,
  SettingsIcon,
  SlidersIcon,
  SparklesIcon,
} from './icons'

interface SidebarProps {
  currentSessionId: string
  onNewChat: () => void
  onOpenSession: (sessionId: string) => Promise<void>
  sessions: SessionSummary[]
}

const primaryNav = [
  { label: '新建聊天', icon: FilePlusIcon, action: 'new' as const },
  { label: '搜索', icon: SearchIcon },
  { label: '插件', icon: PlugIcon },
  { label: '自动化', icon: ClockIcon },
]

const previewSessions = [
  { session_id: 'preview-1', title: '重构成熟的 Axelo AI 工作台', updated_at: '', status: '35 分' },
  { session_id: 'preview-2', title: 'C:\\Users\\PC\\Downloads\\logs.17763...', updated_at: '', status: '2 天' },
  { session_id: 'preview-3', title: '我想你先浏览全部的文件了解整套...', updated_at: '', status: '5 天' },
]

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  const diffMs = Date.now() - date.getTime()
  const diffMinutes = Math.max(0, Math.round(diffMs / (1000 * 60)))

  if (diffMinutes < 60) return `${diffMinutes || 1} 分`

  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours} 小时`

  const diffDays = Math.round(diffHours / 24)
  return `${diffDays} 天`
}

export function Sidebar({ currentSessionId, onNewChat, onOpenSession, sessions }: SidebarProps) {
  const recentSessions = sessions.length > 0 ? sessions.slice(0, 4) : previewSessions

  return (
    <aside className="hidden min-h-0 flex-col border-r border-[#eee7e1] bg-[#fbf6f2] lg:flex">
      <div className="flex h-full flex-col px-3 pb-3 pt-4">
        <div className="space-y-0.5">
          {primaryNav.map((item) => {
            const Icon = item.icon
            const isButton = item.action === 'new'

            return (
              <button
                className="flex w-full items-center gap-2.5 rounded-[10px] px-2 py-2 text-left text-[13px] text-[#5e564d] transition-colors hover:bg-[#f1ebe6]"
                key={item.label}
                onClick={isButton ? onNewChat : undefined}
                type="button"
              >
                <Icon className="h-[15px] w-[15px] text-[#847b72]" />
                <span>{item.label}</span>
              </button>
            )
          })}
        </div>

        <section className="mt-8 min-h-0 flex-1">
          <div className="mb-2 flex items-center justify-between px-1 text-[11px] tracking-[0.02em] text-[#a1958b]">
            <span>项目</span>
            <div className="flex items-center gap-2">
              <SlidersIcon className="h-3.5 w-3.5" />
              <GridIcon className="h-3.5 w-3.5" />
            </div>
          </div>

          <div className="mb-2 flex items-center gap-2 px-1 text-[13px] font-medium text-[#5b534b]">
            <FolderIcon className="h-4 w-4 text-[#887f76]" />
            <span>Axelo</span>
          </div>

          <div className="scrollbar-thin space-y-1 overflow-y-auto pr-1">
            {recentSessions.map((session) => {
              const active = session.session_id === currentSessionId
              const isPreview = session.session_id.startsWith('preview-')

              return (
                <button
                  className={[
                    'w-full rounded-[10px] px-2 py-2 text-left transition-colors',
                    active ? 'bg-[#f1ebe6]' : 'hover:bg-[#f4efea]',
                  ].join(' ')}
                  key={session.session_id}
                  onClick={() => {
                    if (!isPreview) {
                      void onOpenSession(session.session_id)
                    }
                  }}
                  type="button"
                >
                  <div className="truncate text-[12.5px] leading-5 text-[#584f48]">{session.title}</div>
                  <div className="mt-1 text-[11px] text-[#a0958c]">{formatTime(session.updated_at) || session.status}</div>
                </button>
              )
            })}
          </div>

          <div className="mt-6">
            <div className="mb-2 flex items-center justify-between px-1 text-[11px] tracking-[0.02em] text-[#a1958b]">
              <span>聊天</span>
              <GridIcon className="h-3.5 w-3.5" />
            </div>
            <div className="px-1 text-[12px] text-[#c0b6ad]">暂无聊天</div>
          </div>
        </section>

        <div className="mt-4 flex items-center justify-between border-t border-[#f0e8e2] px-1 pt-3">
          <button className="inline-flex items-center gap-2 rounded-full px-2 py-1 text-[12px] text-[#6c645d] transition-colors hover:bg-[#f1ebe6]" type="button">
            <SettingsIcon className="h-3.5 w-3.5" />
            <span>设置</span>
          </button>

          <button className="inline-flex items-center gap-1 rounded-full border border-[#eadfd7] bg-white px-3 py-1 text-[11px] text-[#7b6dff]" type="button">
            <SparklesIcon className="h-3 w-3" />
            <span>升级</span>
          </button>
        </div>
      </div>
    </aside>
  )
}
