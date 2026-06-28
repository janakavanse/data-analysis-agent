'use client'

import type { SummaryTable as SummaryTableData } from '@/lib/api'

export function SummaryTable({ table }: { table: SummaryTableData | null }) {
  if (!table || table.columns.length === 0 || table.rows.length === 0) {
    return null
  }
  return (
    <div data-testid="summary-table" className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            {table.columns.map(c => (
              <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {table.rows.map((row, i) => (
            <tr key={i} className="hover:bg-gray-50">
              {row.map((cell, j) => (
                <td key={j} className="whitespace-nowrap px-3 py-2 text-gray-800">
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

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 4 })
  return String(v)
}
