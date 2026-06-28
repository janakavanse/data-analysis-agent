'use client'

import { useRef, useState } from 'react'
import { uploadDataset, type DatasetMeta } from '@/lib/api'

export default function UploadZone({
  onLoaded,
  busy,
}: {
  onLoaded: (meta: DatasetMeta) => void
  busy: boolean
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFile(file: File | undefined) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Could not read this file as CSV. CSV only for now — Excel coming soon (Phase 4).')
      return
    }
    setError(null)
    setUploading(true)
    try {
      const meta = await uploadDataset(file)
      onLoaded(meta)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not read this file as CSV.'
      setError(message)
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a CSV file"
        onClick={() => !uploading && !busy && inputRef.current?.click()}
        onKeyDown={e => {
          if ((e.key === 'Enter' || e.key === ' ') && !uploading && !busy) inputRef.current?.click()
        }}
        onDragOver={e => {
          e.preventDefault()
          if (!uploading && !busy) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => {
          e.preventDefault()
          setDragging(false)
          if (!uploading && !busy) void handleFile(e.dataTransfer.files?.[0])
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
          dragging
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-slate-300 bg-white hover:border-indigo-400 hover:bg-slate-50'
        } ${uploading || busy ? 'pointer-events-none opacity-60' : ''}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={e => void handleFile(e.target.files?.[0])}
        />
        {uploading ? (
          <div className="flex items-center gap-3 text-sm font-medium text-indigo-600">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-600" />
            Reading your file…
          </div>
        ) : (
          <>
            <svg className="mb-3 h-9 w-9 text-indigo-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.233-2.33 4.5 4.5 0 0 1 1.5 8.892" />
            </svg>
            <p className="text-sm font-semibold text-slate-700">
              Drop a CSV here, or <span className="text-indigo-600">click to browse</span>
            </p>
            <p className="mt-1 text-xs text-slate-400">
              CSV only for now — Excel support coming soon (Phase 4)
            </p>
          </>
        )}
      </div>

      {error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  )
}
