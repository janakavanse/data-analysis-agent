'use client'

import { useState } from 'react'
import type { ResultTable } from '@/lib/api'
import ResultTableView from './ResultTable'

export type AssistantTurn = {
  answer: string
  code?: string | null
  result_table?: ResultTable | null
  failed?: boolean
}

export default function AssistantBubble({ turn }: { turn: AssistantTurn }) {
  const [open, setOpen] = useState(false)
  const hasWork = Boolean(turn.code || turn.result_table)

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-3">
        <div
          className={`rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed shadow-sm ${
            turn.failed
              ? 'border border-red-200 bg-red-50 text-red-800'
              : 'border border-slate-200 bg-white text-slate-800'
          }`}
        >
          <div className="mb-1 flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-[10px] font-bold text-white">
              AI
            </span>
            <span className="text-xs font-medium text-slate-500">Analyst</span>
          </div>
          <p className="whitespace-pre-wrap">{turn.answer}</p>
        </div>

        {hasWork && (
          <div className="overflow-hidden rounded-xl border border-indigo-100 bg-indigo-50/40">
            <button
              type="button"
              onClick={() => setOpen(o => !o)}
              aria-expanded={open}
              className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left text-sm font-semibold text-indigo-700 transition hover:bg-indigo-50"
            >
              <span className="flex items-center gap-2">
                <svg
                  className={`h-4 w-4 transition-transform ${open ? 'rotate-90' : ''}`}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M7.21 14.77a.75.75 0 0 1 .02-1.06L11.168 10 7.23 6.29a.75.75 0 1 1 1.04-1.08l4.5 4.25a.75.75 0 0 1 0 1.08l-4.5 4.25a.75.75 0 0 1-1.06-.02Z"
                    clipRule="evenodd"
                  />
                </svg>
                Show the work
              </span>
              <span className="text-xs font-normal text-indigo-400">
                {open ? 'hide' : 'code + numbers'}
              </span>
            </button>

            {open && (
              <div className="space-y-4 border-t border-indigo-100 px-4 py-4">
                {turn.code && (
                  <div>
                    <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Pandas code that ran
                    </p>
                    <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
                      <code>{turn.code}</code>
                    </pre>
                  </div>
                )}
                {turn.result_table && (
                  <div>
                    <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Computed result
                    </p>
                    <ResultTableView table={turn.result_table} />
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
