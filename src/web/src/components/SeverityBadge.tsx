import type { Severity } from '../types'

const config: Record<Severity, { bg: string; text: string; ring: string; label: string }> = {
  Low:      { bg: 'bg-green-50',  text: 'text-green-800',  ring: 'ring-green-200',  label: 'Low' },
  Medium:   { bg: 'bg-yellow-50', text: 'text-yellow-800', ring: 'ring-yellow-200', label: 'Medium' },
  High:     { bg: 'bg-orange-50', text: 'text-orange-800', ring: 'ring-orange-200', label: 'High' },
  Critical: { bg: 'bg-red-50',    text: 'text-red-800',    ring: 'ring-red-200',    label: 'Critical' },
}

interface Props {
  severity: Severity
  size?: 'sm' | 'md' | 'lg'
}

export default function SeverityBadge({ severity, size = 'md' }: Props) {
  const c = config[severity]
  const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : size === 'lg' ? 'text-base px-4 py-1.5' : 'text-sm px-3 py-1'
  return (
    <span className={`inline-flex items-center font-semibold rounded-full ring-1 ${c.bg} ${c.text} ${c.ring} ${sizeClass}`}>
      {severity === 'Critical' && (
        <svg className="w-3.5 h-3.5 mr-1" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
        </svg>
      )}
      {c.label}
    </span>
  )
}
