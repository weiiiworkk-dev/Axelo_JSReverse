function mulberry32(seed: number) {
  return function () {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const COLS = 38
const ROWS = 7
const LEVEL_CLASS = ['hm-empty', 'hm-l1', 'hm-l2', 'hm-l3', 'hm-l4']

function buildCells(): number[] {
  const rand = mulberry32(42)
  const cells: number[] = []
  for (let c = 0; c < COLS; c++) {
    const pos = c / (COLS - 1)
    const density = pos < 0.65 ? 0.10 : 0.10 + ((pos - 0.65) / 0.35) * 0.55
    for (let r = 0; r < ROWS; r++) {
      let level = 0
      if (rand() > 1 - density) {
        const intensity = rand()
        if (pos > 0.88 && intensity < 0.30) level = 4
        else if (pos > 0.75 && intensity < 0.45) level = 3
        else if (intensity < 0.55) level = 2
        else level = 1
      }
      cells.push(level)
    }
  }
  return cells
}

const CELLS = buildCells()

export function Heatmap() {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateRows: `repeat(${ROWS}, 12px)`,
        gridAutoColumns: '12px',
        gridAutoFlow: 'column',
        gap: '3px',
      }}
    >
      {CELLS.map((level, i) => (
        <div
          key={i}
          className={LEVEL_CLASS[level]}
          style={{ width: 12, height: 12, borderRadius: 2 }}
        />
      ))}
    </div>
  )
}
