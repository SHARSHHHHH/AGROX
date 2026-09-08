import type { ReactNode } from 'react'

/**
 * Machinery illustrations as inline SVG.
 *
 * WHY SVG RATHER THAN PHOTOS
 * --------------------------
 * Stock photos would mean either bundling megabytes of images or hot-linking
 * to a CDN. On a rural connection the first is slow and the second often
 * fails entirely, leaving broken-image icons on every card.
 *
 * These are a few hundred bytes each, render instantly, scale to any size and
 * work with no network at all. When an owner uploads a real photo of their
 * machine it is shown instead; this is the fallback.
 */

interface Props {
  type: string
  className?: string
}

const C = {
  body: '#2f6b3f',
  bodyDark: '#1f4a2b',
  accent: '#f0a92c',
  wheel: '#2b2b2b',
  wheelRim: '#8a8a8a',
  metal: '#9aa5ad',
  sky: '#eef5ee',
}

function Frame({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 200 130" className="w-full h-full" role="img">
      <rect width="200" height="130" fill={C.sky} />
      <line x1="0" y1="112" x2="200" y2="112" stroke="#cfe0cf" strokeWidth="3" />
      {children}
    </svg>
  )
}

const Wheel = ({ cx, cy, r }: { cx: number; cy: number; r: number }) => (
  <g>
    <circle cx={cx} cy={cy} r={r} fill={C.wheel} />
    <circle cx={cx} cy={cy} r={r * 0.45} fill={C.wheelRim} />
    <circle cx={cx} cy={cy} r={r * 0.15} fill={C.wheel} />
  </g>
)

const SHAPES: Record<string, ReactNode> = {
  tractor: (
    <>
      <rect x="72" y="52" width="52" height="34" rx="4" fill={C.body} />
      <rect x="80" y="34" width="34" height="22" rx="3" fill={C.bodyDark} />
      <rect x="84" y="38" width="26" height="14" rx="2" fill="#cfe4f5" />
      <rect x="120" y="62" width="34" height="20" rx="3" fill={C.body} />
      <rect x="150" y="56" width="6" height="16" rx="2" fill={C.accent} />
      <Wheel cx={86} cy={96} r={17} />
      <Wheel cx={143} cy={100} r={13} />
      <rect x="60" y="66" width="14" height="6" rx="2" fill={C.metal} />
    </>
  ),
  rotavator: (
    <>
      <rect x="46" y="46" width="108" height="16" rx="3" fill={C.body} />
      <rect x="52" y="62" width="96" height="26" rx="3" fill={C.bodyDark} />
      {[60, 76, 92, 108, 124, 140].map((x) => (
        <g key={x}>
          <rect x={x} y="88" width="6" height="16" rx="2" fill={C.metal} />
          <path d={`M${x} 104 l6 0 l-3 8 z`} fill={C.wheelRim} />
        </g>
      ))}
      <rect x="92" y="32" width="16" height="16" rx="3" fill={C.accent} />
    </>
  ),
  cultivator: (
    <>
      <rect x="50" y="44" width="100" height="12" rx="3" fill={C.body} />
      <rect x="94" y="30" width="12" height="16" rx="2" fill={C.accent} />
      {[58, 76, 94, 112, 130, 144].map((x, i) => (
        <path key={x} d={`M${x} 56 q2 26 ${i % 2 ? 6 : -6} 46`}
              stroke={C.metal} strokeWidth="5" fill="none" strokeLinecap="round" />
      ))}
    </>
  ),
  seeder: (
    <>
      <path d="M56 40 L144 40 L134 66 L66 66 Z" fill={C.body} />
      <rect x="66" y="66" width="68" height="14" rx="3" fill={C.bodyDark} />
      {[74, 90, 106, 122].map((x) => (
        <g key={x}>
          <rect x={x} y="80" width="5" height="20" fill={C.metal} />
          <circle cx={x + 2.5} cy="104" r="7" fill={C.wheel} />
        </g>
      ))}
      <rect x="92" y="28" width="16" height="12" rx="2" fill={C.accent} />
    </>
  ),
  tiller: (
    <>
      <rect x="70" y="56" width="46" height="26" rx="4" fill={C.body} />
      <rect x="78" y="44" width="16" height="12" rx="2" fill={C.bodyDark} />
      <path d="M116 60 L152 40" stroke={C.metal} strokeWidth="5" strokeLinecap="round" />
      <path d="M116 68 L152 50" stroke={C.metal} strokeWidth="5" strokeLinecap="round" />
      <Wheel cx={88} cy={94} r={16} />
      {[104, 116].map((x) => (
        <rect key={x} x={x} y="84" width="5" height="18" rx="2" fill={C.metal} />
      ))}
    </>
  ),
  sprayer: (
    <>
      <rect x="62" y="42" width="46" height="44" rx="6" fill={C.body} />
      <rect x="68" y="50" width="34" height="14" rx="2" fill="#bfe0c6" opacity="0.7" />
      <rect x="108" y="60" width="10" height="8" rx="2" fill={C.metal} />
      <path d="M118 64 Q142 58 152 46" stroke={C.metal} strokeWidth="4" fill="none" />
      <rect x="150" y="40" width="14" height="5" rx="2" fill={C.accent} />
      {[158, 164, 170].map((x, i) => (
        <circle key={x} cx={x} cy={34 + i * 3} r="2" fill="#7fb8e0" />
      ))}
      <Wheel cx={76} cy={98} r={12} />
      <Wheel cx={100} cy={98} r={12} />
    </>
  ),
  drone: (
    <>
      <rect x="82" y="58" width="36" height="18" rx="5" fill={C.body} />
      <rect x="90" y="76" width="20" height="12" rx="3" fill={C.bodyDark} />
      {[[62, 50], [138, 50]].map(([x, y]) => (
        <g key={x}>
          <line x1="100" y1="64" x2={x} y2={y} stroke={C.metal} strokeWidth="4" />
          <ellipse cx={x} cy={y} rx="22" ry="3.5" fill={C.wheelRim} opacity="0.85" />
          <circle cx={x} cy={y} r="4" fill={C.accent} />
        </g>
      ))}
      {[92, 100, 108].map((x) => (
        <circle key={x} cx={x} cy={96 + (x % 7)} r="2" fill="#7fb8e0" />
      ))}
    </>
  ),
  harvester: (
    <>
      <rect x="70" y="42" width="62" height="40" rx="5" fill={C.body} />
      <rect x="78" y="28" width="30" height="18" rx="3" fill={C.bodyDark} />
      <rect x="82" y="32" width="22" height="11" rx="2" fill="#cfe4f5" />
      <rect x="30" y="62" width="42" height="26" rx="3" fill={C.accent} />
      {[34, 42, 50, 58, 66].map((x) => (
        <rect key={x} x={x} y="88" width="4" height="10" fill={C.metal} />
      ))}
      <rect x="132" y="48" width="26" height="10" rx="3" fill={C.metal} />
      <Wheel cx={92} cy={96} r={18} />
      <Wheel cx={132} cy={100} r={12} />
    </>
  ),
  thresher: (
    <>
      <rect x="54" y="46" width="92" height="42" rx="5" fill={C.body} />
      <rect x="62" y="54" width="30" height="20" rx="3" fill={C.bodyDark} />
      <path d="M146 52 L172 40 L172 62 Z" fill={C.accent} />
      <circle cx="112" cy="66" r="14" fill={C.bodyDark} />
      <circle cx="112" cy="66" r="6" fill={C.metal} />
      <Wheel cx={72} cy={98} r={12} />
      <Wheel cx={130} cy={98} r={12} />
    </>
  ),
  baler: (
    <>
      <rect x="58" y="46" width="76" height="42" rx="5" fill={C.body} />
      <circle cx="150" cy="76" r="20" fill={C.accent} />
      <circle cx="150" cy="76" r="13" fill="#d99a1f" />
      <circle cx="150" cy="76" r="6" fill={C.accent} />
      <rect x="40" y="66" width="20" height="8" rx="2" fill={C.metal} />
      <Wheel cx={78} cy={98} r={13} />
      <Wheel cx={118} cy={98} r={13} />
    </>
  ),
  leveller: (
    <>
      <rect x="56" y="60" width="88" height="14" rx="3" fill={C.body} />
      <rect x="60" y="74" width="80" height="18" rx="2" fill={C.metal} />
      <rect x="96" y="26" width="8" height="34" fill={C.bodyDark} />
      <circle cx="100" cy="24" r="8" fill={C.accent} />
      <path d="M100 24 L150 34" stroke={C.accent} strokeWidth="2"
            strokeDasharray="4 3" />
      <Wheel cx={70} cy={98} r={11} />
      <Wheel cx={130} cy={98} r={11} />
    </>
  ),
  pump: (
    <>
      <rect x="70" y="56" width="54" height="32" rx="5" fill={C.body} />
      <circle cx="96" cy="72" r="12" fill={C.bodyDark} />
      <circle cx="96" cy="72" r="5" fill={C.metal} />
      <rect x="124" y="64" width="14" height="10" rx="2" fill={C.metal} />
      <path d="M138 69 Q160 66 164 92" stroke={C.metal} strokeWidth="6"
            fill="none" strokeLinecap="round" />
      <path d="M56 62 Q36 66 34 92" stroke={C.wheelRim} strokeWidth="6"
            fill="none" strokeLinecap="round" />
      <rect x="66" y="88" width="62" height="8" rx="2" fill={C.bodyDark} />
    </>
  ),
  trolley: (
    <>
      <path d="M46 50 L156 50 L150 84 L52 84 Z" fill={C.body} />
      <rect x="52" y="58" width="96" height="6" rx="2" fill={C.bodyDark} opacity="0.6" />
      <rect x="30" y="70" width="20" height="7" rx="2" fill={C.metal} />
      <Wheel cx={78} cy={96} r={14} />
      <Wheel cx={126} cy={96} r={14} />
      <rect x="60" y="40" width="24" height="10" rx="2" fill={C.accent} />
    </>
  ),
}

export function MachineryImage({ type, className = '' }: Props) {
  const shape = SHAPES[type] || SHAPES.tractor
  return (
    <div className={`bg-field-50 overflow-hidden ${className}`}>
      <Frame>{shape}</Frame>
    </div>
  )
}

export default MachineryImage
