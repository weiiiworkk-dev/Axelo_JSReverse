import { StatsCard } from './StatsCard'

function StarIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
      <path
        d="M20 3C20 3 22.5 14 27 18C31.5 22 38 20 38 20C38 20 31.5 22 27 26C22.5 30 20 37 20 37C20 37 17.5 30 13 26C8.5 22 2 20 2 20C2 20 8.5 18 13 14C17.5 10 20 3 20 3Z"
        fill="#8b5cf6"
      />
    </svg>
  )
}

export function HomeWorkspace() {
  return (
    <div className="flex-1 flex flex-col pt-12 px-[52px] pb-[150px] gap-5 overflow-hidden">
      <div className="flex items-center gap-[11px]">
        <StarIcon />
        <h1 className="text-[26px] font-semibold text-[#111827] tracking-[-0.4px] leading-none">
          What's up next, 江薇?
        </h1>
      </div>
      <StatsCard />
    </div>
  )
}
