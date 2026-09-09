import { ReactNode } from 'react'

const STATUS_COLORS: Record<string, string> = {
  'VERY LOW': 'bg-red-100 text-red-800 border-red-200',
  LOW: 'bg-orange-100 text-orange-800 border-orange-200',
  OPTIMAL: 'bg-green-100 text-green-800 border-green-200',
  HIGH: 'bg-blue-100 text-blue-800 border-blue-200',
  'VERY HIGH': 'bg-purple-100 text-purple-800 border-purple-200',
  ACIDIC: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  ALKALINE: 'bg-indigo-100 text-indigo-800 border-indigo-200',
  CRITICAL: 'bg-red-100 text-red-800 border-red-200',
  WARNING: 'bg-orange-100 text-orange-800 border-orange-200',
  INFO: 'bg-blue-100 text-blue-800 border-blue-200',
  Good: 'bg-green-100 text-green-800 border-green-200',
  Fair: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  Poor: 'bg-red-100 text-red-800 border-red-200',
}

export function StatusPill({ status, colors }: { status: string; colors?: Record<string, string> }) {
  const cls = colors?.[status] || STATUS_COLORS[status] || 'bg-gray-100 text-gray-700 border-gray-200'
  return (
    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold border ${cls}`}>
      {status}
    </span>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-2xl border border-gray-100 shadow-sm p-5 ${className}`}>
      {children}
    </div>
  )
}

export function StatCard({
  label, value, unit, status, recommendation, icon,
}: {
  label: string; value: ReactNode; unit?: string; status?: string
  recommendation?: string; icon?: string
}) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <span className="text-sm font-medium text-gray-500">{icon} {label}</span>
        {status && <StatusPill status={status} />}
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-4xl font-bold text-field-800 font-display">{value}</span>
        {unit && <span className="text-lg text-gray-400">{unit}</span>}
      </div>
      {recommendation && (
        <p className="mt-2 text-sm text-gray-600 leading-snug">{recommendation}</p>
      )}
    </Card>
  )
}

export function Spinner() {
  return (
    <div className="flex justify-center py-8">
      <div className="w-8 h-8 border-3 border-field-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

export function Empty({ msg }: { msg: string }) {
  return <p className="text-center text-gray-400 py-8">{msg}</p>
}

export function DataSourceBadge({ status = 'DEMO' }: { status?: string }) {
  return <span className="inline-block rounded-full border px-2 py-0.5 text-xs font-semibold text-gray-600">{status}</span>
}

export function Button({
  children, onClick, variant = 'primary', disabled, type = 'button', className = '',
}: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'ghost' | 'danger' | 'outline'
  disabled?: boolean; type?: 'button' | 'submit'; className?: string
}) {
  const base = 'px-4 py-2 rounded-xl font-semibold text-sm transition disabled:opacity-50'
  const styles = {
    primary: 'bg-field-600 text-white hover:bg-field-700',
    ghost: 'bg-field-50 text-field-700 hover:bg-field-100',
    danger: 'bg-red-500 text-white hover:bg-red-600',
    outline: 'border border-gray-300 text-gray-700 hover:bg-gray-50',
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${styles[variant]} ${className}`}>
      {children}
    </button>
  )
}
