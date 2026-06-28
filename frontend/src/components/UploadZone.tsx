'use client'

import { useCallback, useRef, useState } from 'react'
import { uploadDataset, ApiRequestError, type Dataset } from '@/lib/api'

interface UploadZoneProps {
  dataset: Dataset | null
  onLoaded: (dataset: Dataset) => void
}

export function UploadZone({ dataset, onLoaded }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  const handleFile = useCallback(
    async (file: File | undefined) => {
      if (!file) return
      setError(null)
      setBusy(true)
      try {
        const ds = await uploadDataset(file)
        onLoaded(ds)
      } catch (e) {
        if (e instanceof ApiRequestError) {
          setError(e.message)
        } else {
          setError('Could not reach the server — is it running?')
        }
      } finally {
        setBusy(false)
      }
    },
    [onLoaded],
  )

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    void handleFile(e.dataTransfer.files?.[0])
  }

  return (
    <section
      data-testid="upload-zone"
      className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900">Dataset</h2>
        {dataset && (
          <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
            Loaded
          </span>
        )}
      </div>

      <div
        onDragOver={e => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors ${
          dragging ? 'border-blue-400 bg-blue-50' : 'border-gray-300 bg-gray-50'
        }`}
      >
        <p className="text-sm text-gray-600">
          Drag &amp; drop a CSV or Excel file here, or
        </p>
        <button
          type="button"
          data-testid="upload-button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50"
        >
          {busy ? 'Uploading…' : 'Choose a file'}
        </button>
        <input
          ref={inputRef}
          data-testid="file-input"
          type="file"
          accept=".csv,.xlsx,.xls,text/csv"
          className="hidden"
          onChange={e => void handleFile(e.target.files?.[0])}
        />
        <p className="mt-3 text-xs text-gray-400">
          A bundled sample lives at <code className="font-mono">data/sample/sales.csv</code> on the server.
        </p>
      </div>

      {error && (
        <div
          data-testid="upload-error"
          role="alert"
          className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {dataset && (
        <div data-testid="dataset-summary" className="mt-4">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-sm font-semibold text-gray-900">{dataset.name}</span>
            <span className="text-xs text-gray-500">
              {dataset.row_count.toLocaleString()} rows · {dataset.schema.length} columns
            </span>
          </div>
          <SamplePreview dataset={dataset} />
        </div>
      )}
    </section>
  )
}

function SamplePreview({ dataset }: { dataset: Dataset }) {
  const cols = dataset.schema.map(s => s.name)
  const rows = dataset.sample.slice(0, 5)
  if (rows.length === 0) return null
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-gray-50 text-gray-500">
          <tr>
            {cols.map(c => (
              <th key={c} className="whitespace-nowrap px-3 py-1.5 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((row, i) => (
            <tr key={i}>
              {cols.map(c => (
                <td key={c} className="whitespace-nowrap px-3 py-1.5 text-gray-700">
                  {formatCell(row[c])}
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
  if (typeof v === 'number') return v.toLocaleString()
  return String(v)
}
