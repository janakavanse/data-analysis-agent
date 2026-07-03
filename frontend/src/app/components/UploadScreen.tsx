'use client'

import { useRef, useState } from 'react'
import { uploadDataset, ApiError, NetworkError } from '../lib/api'
import type { DatasetProfile } from '../lib/api'

interface Props {
  sessionId: string | null
  onUploaded: (dataset: DatasetProfile) => void
  onNetworkError: (message: string) => void
}

const UNREADABLE_FILE_MESSAGE =
  "This file couldn't be read as a spreadsheet — check it's a valid CSV or XLSX."

export function UploadScreen({ sessionId, onUploaded, onNetworkError }: Props) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    if (!sessionId) {
      setError('Session is not ready yet — please wait a moment and try again.')
      return
    }
    const name = file.name.toLowerCase()
    if (!name.endsWith('.csv') && !name.endsWith('.xlsx')) {
      setError(UNREADABLE_FILE_MESSAGE)
      return
    }

    setUploading(true)
    setError(null)
    try {
      const dataset = await uploadDataset(sessionId, file)
      onUploaded(dataset)
    } catch (err) {
      if (err instanceof NetworkError) {
        onNetworkError(err.message)
      } else if (err instanceof ApiError && err.status === 400) {
        setError(UNREADABLE_FILE_MESSAGE)
      } else {
        setError('Something went wrong while uploading this file. Please try again.')
      }
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragActive(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  return (
    <section className="mx-auto w-full max-w-2xl">
      <p className="mb-4 text-sm text-gray-600">Upload a CSV or Excel file to start asking questions.</p>

      <div
        onDragOver={e => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
          dragActive ? 'border-blue-400 bg-blue-50' : 'border-gray-300 bg-white hover:border-gray-400'
        } ${uploading ? 'pointer-events-none opacity-60' : ''}`}
        data-testid="upload-dropzone"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={handleChange}
          disabled={uploading}
          aria-label="Upload spreadsheet file"
          data-testid="file-input"
        />
        {uploading ? (
          <>
            <span
              className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600"
              aria-hidden
            />
            <p className="text-sm font-medium text-gray-700" data-testid="upload-status">
              Uploading and profiling your file…
            </p>
          </>
        ) : (
          <>
            <p className="text-sm font-medium text-gray-700">Drop a .csv or .xlsx file here, or click to browse</p>
            <p className="text-xs text-gray-400">CSV or Excel only</p>
          </>
        )}
      </div>

      {error && (
        <div
          className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
          role="alert"
          data-testid="upload-error"
        >
          <span aria-hidden>⚠️</span>
          <div className="flex-1">
            <p>{error}</p>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-2 rounded-lg border border-red-300 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
            >
              Try another file
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
