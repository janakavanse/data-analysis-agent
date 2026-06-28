'use client'

/**
 * A small "Coming soon" badge for labelled, non-functional stubs.
 * Stubs must read as planned features, never as bugs.
 */
export function StubBadge({ phase, className = '' }: { phase?: string; className?: string }) {
  return (
    <span
      data-testid="stub-badge"
      title={phase ? `Coming in ${phase}` : 'Coming in a later phase'}
      className={`inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ${className}`}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-amber-400" />
      Coming soon{phase ? ` · ${phase}` : ''}
    </span>
  )
}

/**
 * Wraps a deferred control: visibly disabled, dimmed, non-interactive,
 * with a tooltip explaining it is a planned feature.
 */
export function StubItem({
  label,
  phase,
  description,
}: {
  label: string
  phase?: string
  description?: string
}) {
  return (
    <div
      data-testid="stub-item"
      aria-disabled="true"
      title={phase ? `${label} — coming in ${phase}` : `${label} — coming soon`}
      className="flex cursor-not-allowed select-none items-start justify-between gap-2 rounded-lg border border-dashed border-gray-200 bg-gray-50/60 px-3 py-2 opacity-70"
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-gray-500">{label}</div>
        {description && <div className="mt-0.5 text-xs text-gray-400">{description}</div>}
      </div>
      <StubBadge phase={phase} className="shrink-0" />
    </div>
  )
}
