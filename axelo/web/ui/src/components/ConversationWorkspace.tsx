import { useEffect, useRef } from 'react'
import type { ChatThreadItem, SessionView } from '../workbench/types'
import { ComposerCard } from './ComposerCard'
import { ChevronDownIcon, FolderIcon, MicrophoneIcon, SparklesIcon } from './icons'

interface ConversationWorkspaceProps {
  current: SessionView | null
  error: string
  onSend: (message: string) => Promise<void>
  onStartRun: () => Promise<void>
  sending: boolean
}

function actorLabel(item: ChatThreadItem): string {
  if (item.actor_type === 'user') return 'You'
  if (item.actor_type === 'router') return 'Router'
  if (item.actor_type === 'agent') return item.actor_id
  return 'System'
}

function messageTone(item: ChatThreadItem): string {
  if (item.actor_type === 'user') return 'ml-auto border-[#e6dfd8] bg-[#fbf8f5]'
  if (item.kind === 'deliverable_block') return 'border-[#dae7db] bg-[#fbfffb]'
  if (item.kind === 'agent_activity_block') return 'border-[#ece6e1] bg-[#fbf8f6]'
  return 'border-[#ece6e1] bg-white'
}

export function ConversationWorkspace({
  current,
  error,
  onSend,
  onStartRun,
  sending,
}: ConversationWorkspaceProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const items = current?.thread_items || []
  const showRunAction = Boolean(current?.ready_to_run) && !current?.current_run_id

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    viewport.scrollTop = viewport.scrollHeight
  }, [items.length])

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-[#fffdfa]">
      <div className="mx-auto flex w-full max-w-[900px] items-center justify-between gap-4 px-4 pb-2 pt-6 sm:px-8">
        <div>
          <div className="text-[12px] text-[#b0a59b]">会话</div>
          <h1 className="mt-1 text-[20px] font-medium tracking-[-0.03em] text-[#2f2a25]">
            {current?.title || '新聊天'}
          </h1>
        </div>

        <div className="rounded-full border border-[#ece5df] bg-[#fbf8f5] px-3 py-1.5 text-[12px] text-[#8b8178]">
          {(current?.status || 'welcome').replace(/_/g, ' ')}
        </div>
      </div>

      <div
        className="scrollbar-thin mx-auto flex w-full max-w-[900px] flex-1 flex-col gap-3 overflow-y-auto px-4 pb-6 pt-4 sm:px-8"
        ref={viewportRef}
      >
        {items.length > 0 ? (
          items.map((item) => (
            <article
              className={[
                'max-w-[760px] rounded-[18px] border px-4 py-3.5 shadow-[0_8px_22px_rgba(25,22,20,0.025)]',
                messageTone(item),
              ].join(' ')}
              key={item.item_id}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] text-[#b0a59b]">{actorLabel(item)}</span>
                {item.status ? <span className="text-[11px] text-[#948a81]">{item.status}</span> : null}
              </div>
              {item.title ? <div className="mt-2 text-[14px] font-medium text-[#2e2925]">{item.title}</div> : null}
              <div className="mt-2 whitespace-pre-wrap text-[13px] leading-6 text-[#5b544c]">{item.content || ''}</div>
            </article>
          ))
        ) : (
          <div className="rounded-[18px] border border-dashed border-[#e8e1db] bg-[#fbf8f5] px-5 py-6 text-[13px] leading-6 text-[#91877e]">
            还没有对话内容。发送一条消息后，这里会显示完整线程。
          </div>
        )}
      </div>

      <div className="mx-auto w-full max-w-[900px] px-4 pb-6 sm:px-8">
        <ComposerCard
          error={error}
          leftItems={[
            { label: 'Axelo', icon: <FolderIcon className="h-3 w-3" /> },
            ...(showRunAction ? [{ label: '开始运行', icon: <SparklesIcon className="h-3 w-3" /> }] : []),
          ]}
          onSubmit={onSend}
          placeholder="继续描述你的目标，或补充执行约束..."
          rightItems={[
            { label: '中文', withChevron: true },
            { label: '', icon: <MicrophoneIcon className="h-3.5 w-3.5" /> },
          ]}
          rows={3}
          sending={sending}
          variant="conversation"
        />

        {showRunAction ? (
          <button
            className="mt-3 inline-flex items-center gap-1 rounded-full border border-[#e8e1db] bg-white px-3 py-1.5 text-[12px] text-[#766e67] transition-colors hover:bg-[#faf7f4]"
            onClick={() => {
              void onStartRun()
            }}
            type="button"
          >
            <SparklesIcon className="h-3.5 w-3.5" />
            <span>开始运行</span>
            <ChevronDownIcon className="h-3 w-3" />
          </button>
        ) : null}
      </div>
    </main>
  )
}
