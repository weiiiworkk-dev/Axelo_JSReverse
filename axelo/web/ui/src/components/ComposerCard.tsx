import { useId, useState } from 'react'
import { ArrowUpIcon, ChevronDownIcon, PlusIcon } from './icons'

interface ComposerBadge {
  label: string
  icon?: React.ReactNode
  accent?: boolean
  withChevron?: boolean
}

interface ComposerCardProps {
  contextItems?: ComposerBadge[]
  error?: string
  leftItems: ComposerBadge[]
  onSubmit: (message: string) => Promise<void>
  placeholder: string
  rightItems: ComposerBadge[]
  rows?: number
  sending: boolean
  variant?: 'home' | 'conversation'
}

function ToolbarBadge({ badge }: { badge: ComposerBadge }) {
  return (
    <button
      className={[
        'inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] transition-colors',
        badge.accent ? 'text-[#f1782d]' : 'text-[#8f867d]',
        'hover:bg-[#f6f2ef]',
      ].join(' ')}
      type="button"
    >
      {badge.icon}
      <span>{badge.label}</span>
      {badge.withChevron ? <ChevronDownIcon className="h-3 w-3" /> : null}
    </button>
  )
}

export function ComposerCard({
  contextItems = [],
  error,
  leftItems,
  onSubmit,
  placeholder,
  rightItems,
  rows = 3,
  sending,
  variant = 'home',
}: ComposerCardProps) {
  const inputId = useId()
  const [message, setMessage] = useState('')

  async function handleSubmit(): Promise<void> {
    const nextMessage = message.trim()
    if (!nextMessage || sending) return

    await onSubmit(nextMessage)
    setMessage('')
  }

  return (
    <div className="w-full">
      <div className="overflow-hidden rounded-[18px] border border-[#e8e2dc] bg-white shadow-[0_10px_26px_rgba(25,22,20,0.045)]">
        <div className={variant === 'home' ? 'px-4 pb-3 pt-3.5 sm:px-[15px]' : 'px-4 pb-3 pt-3'}>
          <label className="sr-only" htmlFor={inputId}>
            Compose message
          </label>
          <textarea
            className={[
              'w-full resize-none border-0 bg-transparent text-[13px] leading-6 text-[#2e2925] outline-none placeholder:text-[12px] placeholder:text-[#c7c0b7]',
              variant === 'home' ? 'min-h-[62px]' : 'min-h-[60px]',
            ].join(' ')}
            id={inputId}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void handleSubmit()
              }
            }}
            placeholder={placeholder}
            rows={rows}
            value={message}
          />

          <div className="mt-1 flex items-center justify-between gap-3 border-t border-[#f1ece8] pt-2.5">
            <div className="flex min-w-0 items-center gap-1.5">
              <button
                className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[#9a9188] transition-colors hover:bg-[#f6f2ef]"
                type="button"
              >
                <PlusIcon className="h-4 w-4" />
              </button>
              {leftItems.map((badge) => (
                <ToolbarBadge badge={badge} key={badge.label} />
              ))}
            </div>

            <div className="flex min-w-0 items-center gap-1.5">
              {rightItems.map((badge) => (
                <ToolbarBadge badge={badge} key={badge.label} />
              ))}
              <button
                className={[
                  'inline-flex h-7 w-7 items-center justify-center rounded-full border text-[#ffffff] transition-colors',
                  sending ? 'border-[#bfb8b1] bg-[#bfb8b1]' : 'border-[#8d877f] bg-[#8d877f] hover:bg-[#7f786f]',
                ].join(' ')}
                onClick={() => {
                  void handleSubmit()
                }}
                type="button"
              >
                <ArrowUpIcon className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {contextItems.length > 0 ? (
          <div className="flex items-center gap-1.5 border-t border-[#efe8e2] bg-[#f7f4f1] px-3.5 py-2 text-[11px] text-[#8c837a]">
            {contextItems.map((item) => (
              <ToolbarBadge badge={item} key={item.label} />
            ))}
          </div>
        ) : null}
      </div>

      {error ? <p className="mt-2 px-1 text-[12px] text-[#b2554c]">{error}</p> : null}
    </div>
  )
}
