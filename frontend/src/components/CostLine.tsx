'use client'

import { StubBadge } from './StubBadge'

export function CostLine({
  cost,
  tokensIn,
  tokensOut,
}: {
  cost: number
  tokensIn: number
  tokensOut: number
}) {
  const costStr = `$${cost.toFixed(4)}`
  return (
    <div
      data-testid="cost-line"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500"
    >
      <span>
        ~<span className="font-medium text-gray-700">{costStr}</span> ·{' '}
        {tokensIn.toLocaleString()} in / {tokensOut.toLocaleString()} out tokens
      </span>
      <span
        data-testid="daily-cost-stub"
        title="Daily cost total — coming in Phase 3"
        className="inline-flex items-center gap-1.5 text-gray-400"
      >
        <span aria-hidden>·</span> Daily total <StubBadge phase="Phase 3" />
      </span>
    </div>
  )
}
