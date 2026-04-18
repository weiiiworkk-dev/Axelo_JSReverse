import type { AgentStateView, CheckpointRecord, PlanStepView, RunView } from '../workbench/types'

interface RunStateView {
  connected: boolean
  current: RunView | null
  error: string
  events: unknown[]
}

interface SystemRailProps {
  runState: RunStateView
}

function EmptyState({ text }: { text: string }) {
  return <p className="text-[12px] leading-5 text-[#9a9087]">{text}</p>
}

function Section({ body, title }: { body: React.ReactNode; title: string }) {
  return (
    <section className="rounded-[16px] border border-[#ece5df] bg-[#fffdfb] px-4 py-3.5 shadow-[0_8px_22px_rgba(25,22,20,0.02)]">
      <div className="text-[11px] uppercase tracking-[0.04em] text-[#b3a89f]">{title}</div>
      <div className="mt-3">{body}</div>
    </section>
  )
}

function PlanList({ steps }: { steps: PlanStepView[] }) {
  if (steps.length === 0) {
    return <EmptyState text="执行步骤会在 run 开始后出现在这里。" />
  }

  return (
    <div className="space-y-3">
      {steps.map((step) => (
        <div className="grid grid-cols-[8px,minmax(0,1fr)] gap-3" key={step.step_id}>
          <span
            className={[
              'mt-1.5 h-2 w-2 rounded-full',
              step.status === 'completed'
                ? 'bg-[#7ba283]'
                : step.status === 'failed'
                  ? 'bg-[#c06d63]'
                  : step.status === 'blocked'
                    ? 'bg-[#c69a54]'
                    : 'bg-[#c6bcb3]',
            ].join(' ')}
          />
          <div>
            <div className="text-[13px] text-[#423b35]">{step.title}</div>
            {step.note ? <div className="mt-1 text-[12px] leading-5 text-[#9a9087]">{step.note}</div> : null}
          </div>
        </div>
      ))}
    </div>
  )
}

function AgentList({ agents }: { agents: AgentStateView[] }) {
  if (agents.length === 0) {
    return <EmptyState text="当前还没有活跃 agent。" />
  }

  return (
    <div className="space-y-3">
      {agents.map((agent) => (
        <div key={agent.agent_id}>
          <div className="flex items-center justify-between gap-3 text-[13px] text-[#423b35]">
            <span>{agent.label}</span>
            <span className="text-[11px] uppercase tracking-[0.04em] text-[#b3a89f]">{agent.status}</span>
          </div>
          <div className="mt-1 text-[12px] leading-5 text-[#9a9087]">{agent.current_task || 'Waiting'}</div>
        </div>
      ))}
    </div>
  )
}

function CheckpointList({ checkpoints }: { checkpoints: CheckpointRecord[] }) {
  if (checkpoints.length === 0) {
    return <EmptyState text="需要用户决策时，检查点会显示在这里。" />
  }

  return (
    <div className="space-y-3">
      {checkpoints.map((checkpoint) => (
        <div key={checkpoint.checkpoint_id}>
          <div className="text-[13px] text-[#423b35]">{checkpoint.question}</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.04em] text-[#b3a89f]">{checkpoint.status}</div>
        </div>
      ))}
    </div>
  )
}

export function SystemRail({ runState }: SystemRailProps) {
  const run = runState.current

  return (
    <aside className="hidden border-l border-[#eee7e1] bg-[#faf7f4] xl:block">
      <div className="scrollbar-thin flex h-full flex-col gap-3 overflow-y-auto px-3 py-4">
        <Section
          body={
            run ? (
              <>
                <div className="text-[14px] leading-6 text-[#443d37]">{run.objective_text || 'No active objective yet'}</div>
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.04em] text-[#a1958b]">
                  <span>{run.phase_label}</span>
                  <span>{run.status}</span>
                  <span>{runState.connected ? 'Connected' : 'Offline'}</span>
                </div>
              </>
            ) : (
              <EmptyState text="开始执行后，当前目标会固定在这里。" />
            )
          }
          title="Current Objective"
        />

        <Section body={<PlanList steps={run?.plan_steps || []} />} title="Run Plan" />
        <Section body={<AgentList agents={run?.agents || []} />} title="Active Agents" />
        <Section body={<CheckpointList checkpoints={run?.checkpoints || []} />} title="Checkpoints" />

        <Section
          body={
            run ? (
              <div className="space-y-2 text-[12px] text-[#5e564d]">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[#a1958b]">Run</span>
                  <strong className="font-medium text-[#433c36]">{run.run_id}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[#a1958b]">Session</span>
                  <strong className="font-medium text-[#433c36]">{run.session_id || '-'}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[#a1958b]">Recent</span>
                  <strong className="font-medium text-[#433c36]">{run.recent_event || 'Waiting'}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[#a1958b]">Artifacts</span>
                  <strong className="font-medium text-[#433c36]">{run.artifacts.length}</strong>
                </div>
              </div>
            ) : (
              <EmptyState text="运行状态、事件和产物会汇总到这里。" />
            )
          }
          title="Run Status"
        />
      </div>
    </aside>
  )
}
