'use client'

import { useRef, useState } from 'react'

export function UploadZone({
  onFile,
  busy,
  fileName,
}: {
  onFile: (file: File) => void
  busy: boolean
  fileName: string | null
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function pick(files: FileList | null) {
    if (!files || files.length === 0) return
    onFile(files[0])
  }

  return (
    <div
      onDragOver={e => {
        e.preventDefault()
        if (!busy) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => {
        e.preventDefault()
        setDragging(false)
        if (!busy) pick(e.dataTransfer.files)
      }}
      className={[
        'rounded-xl border-2 border-dashed p-6 text-center transition-colors',
        dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-white',
        busy ? 'opacity-60' : '',
      ].join(' ')}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        aria-label="Choose a CSV file"
        disabled={busy}
        onChange={e => pick(e.target.files)}
      />
      <p className="text-sm text-gray-600">
        {busy ? (
          <span className="inline-flex items-center gap-2">
            <Spinner /> Uploading &amp; profiling…
          </span>
        ) : (
          <>Drag a CSV here, or</>
        )}
      </p>
      {!busy && (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:ring-2 focus:ring-blue-400 focus:outline-none"
        >
          Choose CSV file
        </button>
      )}
      {fileName && !busy && (
        <p className="mt-3 text-xs text-gray-500">
          Loaded: <span className="font-medium text-gray-700">{fileName}</span>
        </p>
      )}
    </div>
  )
}

export function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 motion-reduce:animate-none"
    />
  )
}
