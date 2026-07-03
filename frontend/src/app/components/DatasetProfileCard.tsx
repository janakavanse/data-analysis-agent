'use client'

import type { DatasetProfile } from '../lib/api'

interface Props {
  dataset: DatasetProfile
  onReplaceClick: () => void
}

export function DatasetProfileCard({ dataset, onReplaceClick }: Props) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm" data-testid="dataset-profile-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Active dataset</p>
          <h2 className="text-lg font-semibold text-gray-900">{dataset.original_filename}</h2>
          <p className="mt-1 text-sm text-gray-600" data-testid="dataset-counts">
            {dataset.row_count.toLocaleString()} rows · {dataset.column_count} columns
          </p>
        </div>
        <button
          type="button"
          onClick={onReplaceClick}
          className="shrink-0 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400"
        >
          Replace file
        </button>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5" data-testid="dataset-columns">
        {dataset.schema.map(col => (
          <span key={col.name} className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-700">
            <span className="font-medium">{col.name}</span>
            <span className="text-gray-400"> · {col.dtype}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
