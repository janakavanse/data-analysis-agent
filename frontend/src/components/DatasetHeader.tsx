'use client'

import type { SchemaColumn } from '@/lib/api'

export default function DatasetHeader({
  filename,
  rowCount,
  schema,
  onReset,
}: {
  filename: string
  rowCount: number
  schema: SchemaColumn[]
  onReset: () => void
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <svg className="h-5 w-5 shrink-0 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            <h2 className="truncate text-base font-semibold text-slate-800">{filename}</h2>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {rowCount.toLocaleString()} rows · {schema.length} columns · loaded locally
          </p>
        </div>
        <button
          type="button"
          onClick={onReset}
          className="shrink-0 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
        >
          Upload another
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {schema.map(col => (
          <span
            key={col.name}
            className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700"
            title={`dtype: ${col.dtype}`}
          >
            <span className="font-medium">{col.name}</span>
            <span className="font-mono text-[10px] text-slate-400">{col.dtype}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
