export function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

export function fmtTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('zh', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
