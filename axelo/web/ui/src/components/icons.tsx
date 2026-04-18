import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function IconBase({ children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      {...props}
    >
      {children}
    </svg>
  )
}

export function ArrowUpIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 18V6" />
      <path d="m7 11 5-5 5 5" />
    </IconBase>
  )
}

export function BranchIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M7 4v12" />
      <path d="M7 8h10" />
      <path d="M17 8v8" />
      <circle cx="7" cy="4" r="2" />
      <circle cx="7" cy="16" r="2" />
      <circle cx="17" cy="16" r="2" />
    </IconBase>
  )
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m6 9 6 6 6-6" />
    </IconBase>
  )
}

export function ClockIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
    </IconBase>
  )
}

export function FilePlusIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M12 11v6" />
      <path d="M9 14h6" />
    </IconBase>
  )
}

export function FolderIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z" />
    </IconBase>
  )
}

export function GithubIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M9 19c-4.5 1.4-4.5-2.4-6.3-2.8" />
      <path d="M15 21v-3.5c0-1 .1-1.4-.5-2 2.6-.3 5.5-1.3 5.5-6A4.7 4.7 0 0 0 18.8 6 4.4 4.4 0 0 0 18.7 3s-1-.3-3.2 1.2a11 11 0 0 0-5.8 0C7.5 2.7 6.5 3 6.5 3a4.4 4.4 0 0 0-.1 3A4.7 4.7 0 0 0 5 9.5c0 4.7 2.9 5.7 5.5 6-.6.6-.6 1.3-.5 2V21" />
    </IconBase>
  )
}

export function GridIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="4" y="4" width="6" height="6" rx="1.5" />
      <rect x="14" y="4" width="6" height="6" rx="1.5" />
      <rect x="4" y="14" width="6" height="6" rx="1.5" />
      <rect x="14" y="14" width="6" height="6" rx="1.5" />
    </IconBase>
  )
}

export function MicrophoneIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M6 11a6 6 0 0 0 12 0" />
      <path d="M12 17v4" />
    </IconBase>
  )
}

export function MoreIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="6" cy="12" r="1.5" />
      <circle cx="12" cy="12" r="1.5" />
      <circle cx="18" cy="12" r="1.5" />
    </IconBase>
  )
}

export function PlusIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </IconBase>
  )
}

export function PlugIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M9 8V4" />
      <path d="M15 8V4" />
      <path d="M8 11h8" />
      <path d="M12 11v9" />
      <path d="M7 8v3a5 5 0 1 0 10 0V8" />
    </IconBase>
  )
}

export function SearchIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </IconBase>
  )
}

export function SettingsIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.5 14 4l1.2 2 2.2.7.8 2-.8 2 .8 2-1.2 2-2.2.7L12 20.5l-2-.5-1.2-2-2.2-.7-.8-2 .8-2-.8-2 1.2-2L10 4z" />
      <circle cx="12" cy="12" r="3" />
    </IconBase>
  )
}

export function ShieldIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3 5 6v5c0 4.2 2.7 8 7 10 4.3-2 7-5.8 7-10V6z" />
      <path d="m9.5 12 1.8 1.8 3.5-3.8" />
    </IconBase>
  )
}

export function SlidersIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 6h8" />
      <path d="M16 6h4" />
      <path d="M4 12h4" />
      <path d="M12 12h8" />
      <path d="M4 18h10" />
      <path d="M18 18h2" />
      <circle cx="14" cy="6" r="2" />
      <circle cx="10" cy="12" r="2" />
      <circle cx="16" cy="18" r="2" />
    </IconBase>
  )
}

export function SparklesIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m12 3 1.4 3.6L17 8l-3.6 1.4L12 13l-1.4-3.6L7 8l3.6-1.4z" />
      <path d="m18 14 .7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
      <path d="m5 14 .9 2.3 2.3.9-2.3.9L5 20.5l-.9-2.3-2.3-.9 2.3-.9z" />
    </IconBase>
  )
}

export function TerminalIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m5 8 4 4-4 4" />
      <path d="M12 16h7" />
    </IconBase>
  )
}

export function WindowIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M4 9h16" />
    </IconBase>
  )
}
