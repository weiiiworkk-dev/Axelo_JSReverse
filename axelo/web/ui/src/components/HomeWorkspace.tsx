import { ComposerCard } from './ComposerCard'
import {
  BranchIcon,
  ChevronDownIcon,
  FolderIcon,
  GridIcon,
  GithubIcon,
  MicrophoneIcon,
  MoreIcon,
  PlugIcon,
  ShieldIcon,
  SparklesIcon,
  TerminalIcon,
  WindowIcon,
} from './icons'

interface HomeWorkspaceProps {
  error: string
  onSend: (message: string) => Promise<void>
  sending: boolean
}

const suggestionRows = [
  { label: '审查最近的提交是否存在正确性风险和可维护性问题', icon: ShieldIcon },
  { label: '解决我最近一个未合并 PR 的阻塞', icon: GithubIcon },
  { label: '将你常用的应用连接到 Codex', icon: PlugIcon },
]

export function HomeWorkspace({ error, onSend, sending }: HomeWorkspaceProps) {
  return (
    <main className="flex min-w-0 flex-1 flex-col bg-[#fffdfa]">
      <div className="mx-auto flex w-full max-w-[1120px] items-center justify-between px-4 pb-2 pt-4 sm:px-6">
        <div className="flex items-center gap-2">
          <button className="rounded-full px-3 py-1.5 text-[13px] font-medium text-[#3a342f] transition-colors hover:bg-[#f4efea]" type="button">
            新聊天
          </button>
          <button className="inline-flex items-center gap-1 rounded-full bg-[#f1e9ff] px-3 py-1.5 text-[12px] font-medium text-[#8567ff]" type="button">
            <SparklesIcon className="h-3.5 w-3.5" />
            <span>获取 Plus</span>
          </button>
        </div>

        <div className="flex items-center gap-2 text-[#9c938b]">
          <button className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] border border-[#ebe4dd] bg-[#1f1e1c] text-white" type="button">
            <WindowIcon className="h-3.5 w-3.5" />
          </button>
          <button className="inline-flex items-center gap-1 rounded-full border border-[#ebe4dd] bg-white px-3 py-1.5 text-[12px] text-[#8a8178]" type="button">
            <span>提交</span>
            <ChevronDownIcon className="h-3 w-3" />
          </button>
          <span className="mx-0.5 h-4 w-px bg-[#ece4dd]" />
          <button className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[#b4aba2] transition-colors hover:bg-[#f4efea]" type="button">
            <GridIcon className="h-4 w-4" />
          </button>
          <button className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[#b4aba2] transition-colors hover:bg-[#f4efea]" type="button">
            <WindowIcon className="h-4 w-4" />
          </button>
          <button className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[#b4aba2] transition-colors hover:bg-[#f4efea]" type="button">
            <MoreIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-1 justify-center px-4 pb-10 pt-[16vh] sm:px-6 lg:pt-[22vh]">
        <div className="w-full max-w-[540px]">
          <h1 className="text-center text-[20px] font-medium tracking-[-0.03em] text-[#312c27] sm:text-[21px]">
            What should we build in Axelo?
          </h1>

          <div className="mt-7">
            <ComposerCard
              contextItems={[
                { label: 'Axelo', icon: <FolderIcon className="h-3 w-3" />, withChevron: true },
                { label: '本地工作', icon: <TerminalIcon className="h-3 w-3" />, withChevron: true },
                { label: 'main', icon: <BranchIcon className="h-3 w-3" />, withChevron: true },
              ]}
              error={error}
              leftItems={[
                { label: '完全访问权限', accent: true, withChevron: true },
              ]}
              onSubmit={onSend}
              placeholder="向 Codex 提问，@ 添加文件，/ 输入命令，$ 使用技能"
              rightItems={[
                { label: 'GPT-5.4', withChevron: true },
                { label: '中', withChevron: true },
                { label: '', icon: <MicrophoneIcon className="h-3.5 w-3.5" /> },
              ]}
              rows={3}
              sending={sending}
            />
          </div>

          <div className="mt-4 border-t border-[#efeae5]">
            {suggestionRows.map((item) => {
              const Icon = item.icon

              return (
                <button
                  className="flex w-full items-center gap-2 border-b border-[#f2ede8] px-1 py-3 text-left text-[12px] text-[#8e857c] transition-colors hover:text-[#5f564d]"
                  key={item.label}
                  type="button"
                >
                  <Icon className="h-3.5 w-3.5 text-[#9c938a]" />
                  <span>{item.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </main>
  )
}
