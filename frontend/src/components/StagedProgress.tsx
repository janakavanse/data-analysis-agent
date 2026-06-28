'use client'

import { useEffect, useState } from 'react'
import { StubBadge } from './StubBadge'

const STAGES = ['Planning', 'Writing code', 'Running on your data', 'Building chart'] as const

/**
 * Phase 1 POST /analyses is synchronous, so we animate the stepper through the
 * stages on a timer while the request is in flight. Clearly labelled as staged
 * progress; live streaming is a labelled stub.
 */
export function StagedProgress() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      setActive(prev => Math.min(prev + 1, STAGES.length - 1))
    }, 1200)
    return () => clearInterval(id)
  }, [])

  return (
    <section
      data-testid="staged-progress"
      className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900">Working on your answer</h2>
        <span
          data-testid="streaming-stub"
          title="Live token streaming — coming in Phase 3"
          className="inline-flex items-center gap-1.5 text-xs text-gray-400"
        >
          <StubBadge phase="Phase 3" />
          Live streaming
        </span>
      </div>

      <ol className="space-y-3">
        {STAGES.map((stage, i) => {
          const done = i < active
          const current = i === active
          return (
            <li key={stage} className="flex items-center gap-3">
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                  done
                    ? 'bg-emerald-500 text-white'
                    : current
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-400'
                }`}
              >
                {done ? '✓' : i + 1}
              </span>
              <span
                className={`text-sm ${
                  current ? 'font-medium text-gray-900' : done ? 'text-gray-600' : 'text-gray-400'
                }`}
              >
                {stage}
              </span>
              {current && (
                <span
                  aria-hidden
                  className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600"
                />
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
