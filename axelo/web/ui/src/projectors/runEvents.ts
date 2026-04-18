import type { ChatThreadItem, RunEvent } from '../workbench/types'

function makeNotice(event: RunEvent, kind: ChatThreadItem['kind'], title: string, status = ''): ChatThreadItem {
  return {
    item_id: `${kind}:${event.event_id}`,
    session_id: event.session_id || '',
    run_id: event.run_id,
    kind,
    created_at: event.ts,
    actor_type: kind === 'router_message' ? 'router' : 'system',
    actor_id: kind === 'router_message' ? 'router' : 'system',
    title,
    content: String(event.payload.message || ''),
    status,
    meta: { phase: event.phase },
  }
}

export function applyRunEventToThread(items: ChatThreadItem[], event: RunEvent): ChatThreadItem[] {
  if (event.kind === 'run.created') {
    return [...items, makeNotice(event, 'system_notice', 'Run started')]
  }

  if (event.kind === 'router.message') {
    return [...items, makeNotice(event, 'router_message', '')]
  }

  if (event.kind === 'deliverable.created') {
    return [...items, makeNotice(event, 'deliverable_block', 'Deliverable')]
  }

  if (event.kind === 'run.completed') {
    return [...items, makeNotice(event, 'system_notice', 'Run completed', 'completed')]
  }

  if (event.kind === 'run.failed') {
    return [...items, makeNotice(event, 'system_notice', 'Run failed', 'failed')]
  }

  if (event.kind !== 'agent.activity' || event.payload.transient) {
    return items
  }

  const status = String(event.payload.status || 'running')
  const title = String(event.payload.objective_label || event.actor_id)
  const message = String(event.payload.message || '')

  const next = [...items]
  const existingIndex = [...next].reverse().findIndex((item) =>
    item.kind === 'agent_activity_block'
    && item.run_id === event.run_id
    && item.actor_id === event.actor_id
  )

  if (existingIndex === -1) {
    next.push({
      item_id: `activity:${event.event_id}`,
      session_id: event.session_id || '',
      run_id: event.run_id,
      kind: 'agent_activity_block',
      created_at: event.ts,
      actor_type: 'agent',
      actor_id: event.actor_id,
      title,
      content: message,
      status,
      meta: {
        objective: event.payload.objective || '',
        recent_actions: message ? [message] : [],
      },
    })
    return next
  }

  const targetIndex = next.length - 1 - existingIndex
  const target = next[targetIndex]
  if (!target || target.kind !== 'agent_activity_block') return next

  const previousStatus = String(target.status || '')
  if (
    (previousStatus === 'completed' || previousStatus === 'failed')
    && status === 'running'
  ) {
    next.push({
      item_id: `activity:${event.event_id}`,
      session_id: event.session_id || '',
      run_id: event.run_id,
      kind: 'agent_activity_block',
      created_at: event.ts,
      actor_type: 'agent',
      actor_id: event.actor_id,
      title,
      content: message,
      status,
      meta: {
        objective: event.payload.objective || '',
        recent_actions: message ? [message] : [],
      },
    })
    return next
  }

  const recentActions = [...(target.meta?.recent_actions || []), message].filter(Boolean).slice(-3)
  next[targetIndex] = {
    ...target,
    created_at: event.ts,
    title,
    content: recentActions.join('\n'),
    status,
    meta: {
      ...(target.meta || {}),
      objective: event.payload.objective || '',
      recent_actions: recentActions,
    },
  }
  return next
}
