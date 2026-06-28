'use client'

import { useState } from 'react'
import { Spinner } from './UploadZone'

const STAGE_LABELS: Record<string, string> = {
  planning: 'Planning…',
  plan: 'Planning…',
  generate_code: 'Writing analysis code…',
  codegen: 'Writing analysis code…',
  running: 'Running analysis locally…',
  execute: 'Running analysis locally…',
  summarize: 'Summarising results…',
  summarizing: 'Summarising results…',
}

export interface QueryStreamState {
  steps: string[]
  answer: string
  code: string | null
  status: 'idle' | 'streaming' | 'done' | 'error'
  errorMessage: string | null
}

export const initialStreamState: QueryStreamState = {
  steps: [],
  answer: '',
  code: null,
  status: 'idle',
  errorMessage: null,
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? `${stage[0]?.toUpperCase()}${stage.slice(1)}…`
}

export function AnswerStream({ state }: { state: QueryStreamState }) {
  const [showCode, setShowCode] = useState(false)

  if (state.status === 'idle') {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 text-center text-sm text-gray-400">
        Ask a question above to see a streamed answer, with the exact code that ran.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* live step badges */}
      {state.steps.length > 0 && (
        <ol className="flex flex-wrap items-center gap-2" aria-label="Analysis progress">
          {state.steps.map((s, i) => {
            const isLast = i === state.steps.length - 1
            const active = isLast && state.status === 'streaming'
            return (
              <li
                key={`${s}-${i}`}
                className={[
                  'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium',
                  active
                    ? 'border-blue-200 bg-blue-50 text-blue-700'
                    : 'border-gray-200 bg-gray-50 text-gray-500',
                ].join(' ')}
              >
                {active && <Spinner />}
                {stageLabel(s)}
              </li>
            )
          })}
        </ol>
      )}

      {/* error */}
      {state.status === 'error' && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
        >
          <p className="font-medium">Analysis failed</p>
          <p className="mt-1">{state.errorMessage ?? 'Something went wrong.'}</p>
        </div>
      )}

      {/* streamed answer */}
      {(state.answer || state.status === 'streaming') && (
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-[15px] leading-relaxed whitespace-pre-wrap text-gray-900">
            {state.answer}
            {state.status === 'streaming' && (
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-blue-500 align-middle motion-reduce:animate-none" />
            )}
          </div>
        </div>
      )}

      {/* show code disclosure */}
      {state.code && (
        <div className="rounded-xl border border-gray-200 bg-white">
          <button
            type="button"
            aria-expanded={showCode}
            onClick={() => setShowCode(v => !v)}
            className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-gray-700 hover:bg-gray-50 focus:ring-2 focus:ring-blue-400 focus:outline-none"
          >
            <span>{showCode ? 'Hide code' : 'Show code'} — the exact pandas that ran</span>
            <span aria-hidden="true" className="text-gray-400">{showCode ? '−' : '+'}</span>
          </button>
          {showCode && (
            <div className="border-t border-gray-100 p-4">
              <pre className="overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs leading-relaxed text-gray-100">
                <code>{state.code}</code>
              </pre>
              <p className="mt-2 text-xs text-gray-500">
                This ran locally on your machine — your data rows stayed local.
              </p>
            </div>
          )}
        </div>
      )}

      {state.status === 'done' && (
        <p className="text-xs font-medium text-green-600">Complete.</p>
      )}
    </div>
  )
}
