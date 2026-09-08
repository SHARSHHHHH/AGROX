/**
 * Icons for the circular farming module.
 *
 * WHY NOT EMOJI
 * -------------
 * Emoji render differently on every device — 🐄 is a different animal on
 * Samsung than on a Pixel, and several of the ones this module needed (a
 * digester, a slurry pit, worm castings) simply do not exist as emoji, so
 * they were being approximated by something misleading.
 *
 * These are flat two-tone SVGs on a shared 24x24 grid, drawn to read at 20px
 * on a phone. They inherit colour from the parent, so the same icon works on
 * a green card and an amber one.
 */

type Props = { size?: number; className?: string }

const base = (size: number) => ({
  width: size, height: size, viewBox: '0 0 24 24',
  fill: 'none', stroke: 'currentColor', strokeWidth: 1.7,
  strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
})

export function CattleIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 9c0-1.5 1-2.5 2.5-2.5S9 7.5 9 9" />
      <path d="M15 9c0-1.5 1-2.5 2.5-2.5S20 7.5 20 9" />
      <path d="M6 9h12v5a6 6 0 0 1-12 0V9Z" />
      <circle cx="10" cy="12" r=".6" fill="currentColor" />
      <circle cx="14" cy="12" r=".6" fill="currentColor" />
      <path d="M10.5 16.5h3" />
    </svg>
  )
}

export function DungIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 18h16a2.5 2.5 0 0 0 0-5h-1a3 3 0 0 0-5-3 3.5 3.5 0 0 0-6 1.5A2.7 2.7 0 0 0 4 18Z" />
      <path d="M8.5 15.5h.01M12 16h.01M15 15h.01" />
    </svg>
  )
}

export function ResidueIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 20V9" />
      <path d="M12 12c0-2.5-1.5-4.5-4-5 0 2.5 1.5 4.5 4 5Z" />
      <path d="M12 12c0-2.5 1.5-4.5 4-5 0 2.5-1.5 4.5-4 5Z" />
      <path d="M12 9c0-2 1-3.5 2.5-4.5C15 6.5 14 8.5 12 9Z" />
      <path d="M5 20h14" />
    </svg>
  )
}

export function FlameIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 3c2.5 3 4.5 5 4.5 8.5A4.5 4.5 0 0 1 12 16a4.5 4.5 0 0 1-4.5-4.5C7.5 8 9.5 6 12 3Z" />
      <path d="M12 16v5" />
      <path d="M8 21h8" />
    </svg>
  )
}

export function SlurryIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M5 8h14l-1.2 11a2 2 0 0 1-2 1.8H8.2a2 2 0 0 1-2-1.8L5 8Z" />
      <path d="M4 8h16" />
      <path d="M7 13c1.5-1 3-1 4.5 0s3 1 4.5 0" />
    </svg>
  )
}

export function FieldIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3 19h18" />
      <path d="M12 19v-6" />
      <path d="M12 13c-2 0-3.5-1.5-3.5-3.5C10.5 9.5 12 11 12 13Z" />
      <path d="M12 13c2 0 3.5-1.5 3.5-3.5C13.5 9.5 12 11 12 13Z" />
      <path d="M6 19c0-2 1-3 2.5-3M18 19c0-2-1-3-2.5-3" />
    </svg>
  )
}

export function ShareIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <circle cx="8" cy="8" r="2.5" />
      <circle cx="16" cy="8" r="2.5" />
      <path d="M3.5 19c0-2.5 2-4.5 4.5-4.5s4.5 2 4.5 4.5" />
      <path d="M13 19c0-2.5 2-4.5 4.5-4.5s3 1.4 3 3" />
    </svg>
  )
}

export function WormIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 16c0-2 1.5-3 3-3s3 1 3 3 1.5 3 3 3 3-1 3-3-1.5-3-3-3" />
      <path d="M17 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
      <path d="M16 6.5h.01M18 6.5h.01" />
    </svg>
  )
}

export function HeapIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3 19h18" />
      <path d="M4 19c1-5 4-8 8-8s7 3 8 8" />
      <path d="M9 14.5c1-1 2-1.5 3-1.5s2 .5 3 1.5" />
    </svg>
  )
}

export function ShedIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3 11 12 4l9 7" />
      <path d="M5 11v9h14v-9" />
      <path d="M9.5 20v-5h5v5" />
    </svg>
  )
}

export function DrumIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <ellipse cx="12" cy="6" rx="6" ry="2.4" />
      <path d="M6 6v12c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4V6" />
      <path d="M6 12c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4" />
    </svg>
  )
}

export function PlantIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 21v-8" />
      <path d="M12 13c-3 0-5-2-5-5 3 0 5 2 5 5Z" />
      <path d="M12 13c3 0 5-2 5-5-3 0-5 2-5 5Z" />
      <path d="M8 21h8" />
    </svg>
  )
}

export function ToolIcon({ size = 24, className = '' }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M14.5 5.5a3.5 3.5 0 0 0 4.6 4.6l-8.4 8.4a2.3 2.3 0 0 1-3.2-3.2l8.4-8.4Z" />
      <path d="M5 5l3 3" />
    </svg>
  )
}

/** Maps a cycle node or method key to its icon. */
export const CIRCULAR_ICONS: Record<string, (p: Props) => JSX.Element> = {
  cattle: CattleIcon, dung: DungIcon, residue: ResidueIcon,
  biogas: FlameIcon, digestate: SlurryIcon, own_farm: FieldIcon,
  surplus: ShareIcon, crops: PlantIcon,
  vermicompost: WormIcon, compost: HeapIcon, fym: ShedIcon,
  liquid: DrumIcon, technician: ToolIcon,
}

export function CircularIcon({ name, size = 24, className = '' }:
                             Props & { name: string }) {
  const Cmp = CIRCULAR_ICONS[name] || PlantIcon
  return <Cmp size={size} className={className} />
}
