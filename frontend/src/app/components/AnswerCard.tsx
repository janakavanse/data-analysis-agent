'use client'

import { useState } from 'react'
import type { QueryDetail } from '../lib/api'

const FOLLOWUP_STUB_CHIPS = [
  'e.g. break this down further',
  'e.g. compare to another column',
  'e.g. filter to a subset',
]

export function AnswerCard({ detail }: { detail: QueryDetail }) {
  const [showCode, setShowCode] = useState(false)
  const table = detail.result_table ?? null
  const columns = table && table.length > 0 ? Object.keys(table[0]) : []
  const usage = detail.token_usage

  return (
    <div className="space-y-4">
      <p className="text-lg font-semibold leading-snug text-gray-900" data-testid="answer-text">
        {detail.answer_text}
      </p>

      {table && table.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200" data-testid="result-table">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {columns.map(col => (
                  <th key={col} className="px-3 py-2 text-left font-medium text-gray-600">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {table.map((row, i) => (
                <tr key={i}>
                  {columns.map(col => (
                    <td key={col} className="px-3 py-2 text-gray-700">
                      {String(row[col] ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Chart area — non-functional stub, arrives in Phase 2 */}
      <div
        aria-disabled="true"
        data-testid="chart-stub"
        className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-center text-sm text-gray-400"
      >
        <span className="rounded-full bg-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
          Phase 2
        </span>
        Interactive chart — coming in Phase 2
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowCode(v => !v)}
          className="text-sm font-medium text-blue-600 hover:text-blue-700 focus:outline-none focus:underline"
          aria-expanded={showCode}
          data-testid="toggle-code"
        >
          {showCode ? 'Hide generated code ▴' : 'Show generated code ▾'}
        </button>
        {showCode && (
          <pre
            className="mt-2 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs text-gray-100"
            data-testid="generated-code"
          >
            <code>{detail.generated_code ?? ''}</code>
          </pre>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
        {usage && (
          <span className="rounded-full bg-gray-100 px-3 py-1 font-medium text-gray-600" data-testid="token-usage">
            {usage.prompt_tokens} + {usage.completion_tokens} = {usage.total_tokens} tokens
          </span>
        )}
        {detail.retry_count === 1 && (
          <span className="rounded-full bg-amber-50 px-3 py-1 font-medium text-amber-700" data-testid="retry-note">
            Retried once after the first attempt failed.
          </span>
        )}
      </div>

      {/* Follow-up chips — non-functional stub, arrives in Phase 2 */}
      <div data-testid="followup-stub">
        <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-400">
          Suggested follow-ups — coming in Phase 2
        </p>
        <div className="flex flex-wrap gap-2">
          {FOLLOWUP_STUB_CHIPS.map(text => (
            <span
              key={text}
              aria-disabled="true"
              className="cursor-not-allowed select-none rounded-full border border-dashed border-gray-200 px-3 py-1 text-xs text-gray-300"
            >
              {text}
            </span>
          ))}
        </div>
      </div>

      <button
        type="button"
        disabled
        title="Export becomes available in Phase 2"
        data-testid="export-stub"
        className="cursor-not-allowed rounded-lg border border-gray-200 bg-gray-100 px-4 py-2 text-sm font-medium text-gray-400"
      >
        Export cleaned data (coming in Phase 2)
      </button>
    </div>
  )
}
