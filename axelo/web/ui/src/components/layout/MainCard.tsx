import { ReactNode } from 'react'

interface MainCardProps {
  children: ReactNode
}

export function MainCard({ children }: MainCardProps) {
  return (
    <div className="flex-1 bg-white border border-[#e2e2e2] rounded-[14px] shadow-[0_2px_10px_rgba(0,0,0,0.07),0_1px_3px_rgba(0,0,0,0.04)] overflow-hidden relative flex flex-col min-w-0">
      {children}
    </div>
  )
}
