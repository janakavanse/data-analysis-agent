'use client'

import { useMemo, useState } from 'react'
import type { QueryDetail } from '../lib/api'
import { exportQuery, ApiError, NetworkError } from '../lib/api'
import { PlotlyChart } from './PlotlyChart'

type SortDirection = 'asc' | 'desc'

function isNumeric(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (isNumeric(value)) {
    // Thousands separators for large numbers; sensible decimal places for
    // fractional values. Strings/dates pass through untouched (see below).
    const decimals = Number.isInteger(value) ? 0 : 2
    return value.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
  }
  return String(value)
}

export function AnswerCard({
  detail,
  onFollowupClick,
}: {
  detail: QueryDetail
  onFollowupClick?: (question: string) => void
}) {
  const [showCode, setShowCode] = useState(false)
  const [sortColumn, setSortColumn] = useState<string | null>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [exportError, setExportError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const table = detail.result_table ?? null
  const columns = table && table.length > 0 ? Object.keys(table[0]) : []
  const usage = detail.token_usage
  const followups = detail.suggested_followups ?? null
  const chartSpec = detail.chart_spec ?? null

  const sortedTable = useMemo(() => {
    if (!table || !sortColumn) return table
    const copy = [...table]
    copy.sort((a, b) => {
      const av = a[sortColumn]
      const bv = b[sortColumn]
      let cmp: number
      if (isNumeric(av) && isNumeric(bv)) {
        cmp = av - bv
      } else {
        cmp = String(av ?? '').localeCompare(String(bv ?? ''))
      }
      return sortDirection === 'asc' ? cmp : -cmp
    })
    return copy
  }, [table, sortColumn, sortDirection])

  function handleSort(col: string) {
    if (sortColumn === col) {
      setSortDirection(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortColumn(col)
      setSortDirection('asc')
    }
  }

  async function handleExport() {
    setExportError(null)
    setExporting(true)
    try {
      const { blob, filename } = await exportQuery(detail.query_id, 'csv')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      if (err instanceof NetworkError) {
        setExportError(err.message)
      } else if (err instanceof ApiError && err.status === 400) {
        setExportError('This answer has no exportable data table.')
      } else if (err instanceof ApiError) {
        setExportError(err.message)
      } else {
        setExportError('Export failed. Please try again.')
      }
    } finally {
      setExporting(false)
    }
  }

  const usageThinking = usage?.thinking_tokens ?? 0

  return (
    <div className="space-y-4">
      <p className="text-lg font-semibold leading-snug text-gray-900" data-testid="answer-text">
        {detail.answer_text}
      </p>

      {sortedTable && sortedTable.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200" data-testid="result-table">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {columns.map(col => (
                  <th
                    key={col}
                    onClick={() => handleSort(col)}
                    className="cursor-pointer select-none px-3 py-2 text-left font-medium text-gray-600 hover:text-gray-900"
                  >
                    {col}
                    {sortColumn === col && (
                      <span className="ml-1 text-gray-400" aria-hidden>
                        {sortDirection === 'asc' ? '▲' : '▼'}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {sortedTable.map((row, i) => (
                <tr key={i}>
                  {columns.map(col => (
                    <td key={col} className="px-3 py-2 text-gray-700">
                      {formatCell(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Chart: real, interactive Plotly figure — rendered only when the
          backend produced one for this turn. A purely scalar answer shows
          no chart panel at all (per spec/ui.md), not an empty placeholder. */}
      {chartSpec && <PlotlyChart spec={chartSpec} />}

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
            {usageThinking > 0
              ? `${usage.prompt_tokens} + ${usage.completion_tokens} + ${usageThinking} (thinking) = ${usage.total_tokens} tokens`
              : `${usage.prompt_tokens} + ${usage.completion_tokens} = ${usage.total_tokens} tokens`}
          </span>
        )}
        {detail.retry_count === 1 && (
          <span className="rounded-full bg-amber-50 px-3 py-1 font-medium text-amber-700" data-testid="retry-note">
            Retried once after the first attempt failed.
          </span>
        )}
      </div>

      {/* Follow-up chips: real and clickable, only rendered when the
          backend suggested some for this turn. */}
      {followups && followups.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-400">Suggested follow-ups</p>
          <div className="flex flex-wrap gap-2">
            {followups.map(text => (
              <button
                key={text}
                type="button"
                data-testid="followup-chip"
                onClick={() => onFollowupClick?.(text)}
                className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                {text}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col items-start gap-1">
        <button
          type="button"
          onClick={handleExport}
          disabled={exporting}
          data-testid="export-button"
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {exporting ? 'Exporting…' : 'Export cleaned data'}
        </button>
        {exportError && (
          <p className="text-xs text-red-600" data-testid="export-error">
            {exportError}
          </p>
        )}
      </div>
    </div>
  )
}
