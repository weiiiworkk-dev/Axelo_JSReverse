import { useApp, PlanStep } from '../../context/AppContext'

// ── 图标 ─────────────────────────────────────────────────────────────────────

function IconClose() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function IconBolt() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

// ── 步骤状态图标 ──────────────────────────────────────────────────────────────

function StepIcon({ status }: { status: PlanStep['status'] }) {
  if (status === 'completed') {
    return (
      <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center flex-shrink-0">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
    )
  }
  if (status === 'running') {
    return (
      <div className="w-5 h-5 rounded-full border-2 border-lavender-500 flex items-center justify-center flex-shrink-0">
        <div
          className="w-2 h-2 rounded-full bg-lavender-500"
          style={{ animation: 'pulse-dot 1.2s ease-in-out infinite' }}
        />
        <style>{`@keyframes pulse-dot { 0%,100%{opacity:.4;transform:scale(.7)} 50%{opacity:1;transform:scale(1)} }`}</style>
      </div>
    )
  }
  if (status === 'failed') {
    return (
      <div className="w-5 h-5 rounded-full bg-red-100 border border-red-300 flex items-center justify-center flex-shrink-0">
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="3">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </div>
    )
  }
  if (status === 'blocked') {
    return (
      <div className="w-5 h-5 rounded-full bg-amber-100 border border-amber-300 flex items-center justify-center flex-shrink-0">
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="3">
          <line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
    )
  }
  // pending
  return (
    <div className="w-5 h-5 rounded-full border-2 border-[#e0e0e0] flex-shrink-0" />
  )
}

// ── 连接线 ────────────────────────────────────────────────────────────────────

function Connector({ done }: { done: boolean }) {
  return (
    <div className="flex justify-center w-5 flex-shrink-0">
      <div className={`w-[2px] h-5 rounded-full transition-colors duration-500 ${done ? 'bg-emerald-400' : 'bg-[#e8e8e8]'}`} />
    </div>
  )
}

// ── 单个步骤行 ────────────────────────────────────────────────────────────────

function Step({ step, isLast }: { step: PlanStep; isLast: boolean }) {
  const isActive = step.status === 'running'
  const isDone = step.status === 'completed'

  return (
    <div>
      <div className="flex items-start gap-2.5 py-[5px]">
        <StepIcon status={step.status} />
        <div className="flex-1 min-w-0 pt-[2px]">
          <div className={`text-[12.5px] font-medium leading-tight transition-colors ${
            isActive ? 'text-lavender-700'
            : isDone ? 'text-[#374151]'
            : 'text-[#9ca3af]'
          }`}>
            {step.label}
          </div>
          {step.agentId && isActive && (
            <div className="text-[11px] text-lavender-400 mt-0.5 truncate">{step.agentId}</div>
          )}
          {step.note && (isActive || isDone) && (
            <div className="text-[11px] text-[#9ca3af] mt-0.5 line-clamp-2 leading-snug">{step.note}</div>
          )}
        </div>
      </div>
      {!isLast && <Connector done={isDone} />}
    </div>
  )
}

// ── 运行状态徽标 ──────────────────────────────────────────────────────────────

function RunBadge({ status }: { status: string }) {
  if (status === 'running') return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-lavender-100 text-lavender-600 flex items-center gap-1">
      <span className="w-1.5 h-1.5 rounded-full bg-lavender-500" style={{ animation: 'pulse-dot 1.2s ease-in-out infinite' }} />
      执行中
    </span>
  )
  if (status === 'completed') return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-600">完成</span>
  )
  if (status === 'failed') return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-red-100 text-red-600">失败</span>
  )
  return null
}

// ── 主面板 ────────────────────────────────────────────────────────────────────

export function ExecutionPanel() {
  const { state, closePanel } = useApp()
  const { planSteps, runStatus, rightPanelOpen } = state

  return (
    <div
      className="flex-shrink-0 overflow-hidden"
      style={{
        width: rightPanelOpen ? '280px' : '0px',
        transition: 'width 0.32s cubic-bezier(0.4,0,0.2,1)',
      }}
    >
      {/* 内容容器 — 固定 280px 宽，不随动画收缩 */}
      <div className="w-[280px] h-full bg-white border border-[#e2e2e2] rounded-[14px] shadow-[0_2px_10px_rgba(0,0,0,0.07)] flex flex-col overflow-hidden">

        {/* 标题栏 */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[#f2f2f2] flex-shrink-0">
          <span className="text-lavender-500"><IconBolt /></span>
          <span className="text-[13px] font-semibold text-[#111827] flex-1">执行流程</span>
          <RunBadge status={runStatus} />
          <button
            onClick={closePanel}
            className="w-5 h-5 rounded-md flex items-center justify-center text-[#c0c0c0] hover:bg-[#f3f4f6] hover:text-[#6b7280] transition-colors ml-1"
          >
            <IconClose />
          </button>
        </div>

        {/* 步骤列表 */}
        <div className="flex-1 overflow-y-auto no-scrollbar px-4 py-3">
          {planSteps.map((step, i) => (
            <Step key={step.id} step={step} isLast={i === planSteps.length - 1} />
          ))}
        </div>

        {/* 底部状态 */}
        {runStatus === 'completed' && (
          <div className="px-4 py-2.5 border-t border-[#f2f2f2] flex-shrink-0">
            <div className="text-[11.5px] text-emerald-600 font-medium text-center">✅ 所有步骤执行完毕</div>
          </div>
        )}
        {runStatus === 'failed' && (
          <div className="px-4 py-2.5 border-t border-[#f2f2f2] flex-shrink-0">
            <div className="text-[11.5px] text-red-500 font-medium text-center">❌ 执行遇到错误</div>
          </div>
        )}
      </div>
    </div>
  )
}
