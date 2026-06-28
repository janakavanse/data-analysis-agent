'use client'

import type { ResultTable } from '@/lib/api'

function formatCell(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    // Trim noisy float tails while keeping integers clean.
    return Number.isInteger(value) ? value.toString() : value.toLocaleString(undefined, { maximumFractionDigits: 4 })
  }
  return String(value)
}

export default function ResultTableView({ table }: { table: ResultTable }) {
  // Scalar result — a single computed value.
  if (table.kind === 'scalar' || (table.value !== undefined && table.value !== null && !table.rows)) {
    return (
      <div className="inline-flex items-baseline gap-2 rounded-md bg-slate-900 px-4 py-3">
        <span className="text-xs uppercase tracking-wide text-slate-400">Result</span>
        <span className="font-mono text-lg font-semibold text-emerald-300">{formatCell(table.value)}</span>
      </div>
    )
  }

  const columns = table.columns ?? []
  const rows = table.rows ?? []

  if (columns.length === 0 && rows.length === 0) {
    return <p className="text-sm text-slate-500">No tabular result.</p>
  }

  return (
    <div className="overflow-x-auto rounded-md border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {columns.map((col, i) => (
              <th key={i} className="px-3 py-2 text-left font-semibold text-slate-700">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {rows.map((row, ri) => (
            <tr key={ri} className="even:bg-slate-50/50">
              {row.map((cell, ci) => (
                <td key={ci} className="whitespace-nowrap px-3 py-2 font-mono text-slate-800">
                  {formatCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
