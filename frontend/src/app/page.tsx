'use client'

import { useRef, useState } from 'react'
import { uploadDataset, streamQuery, type Dataset } from '../lib/api'
import { UploadZone } from '../components/UploadZone'
import { ProfileTable, ProfileSkeleton } from '../components/ProfileTable'
import {
  AnswerStream,
  initialStreamState,
  type QueryStreamState,
} from '../components/AnswerStream'
import { StubPanel } from '../components/StubPanel'

const PRIVACY_LINE =
  'Your raw data never leaves this machine — only schema & summaries go to the model.'

export default function Home() {
  // upload / profile state
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)

  // query / stream state
  const [question, setQuestion] = useState('')
  const [stream, setStream] = useState<QueryStreamState>(initialStreamState)
  const abortRef = useRef<AbortController | null>(null)

  const streaming = stream.status === 'streaming'

  async function handleFile(file: File) {
    setUploading(true)
    setUploadError(null)
    setFileName(file.name)
    setDataset(null)
    try {
      const ds = await uploadDataset(file)
      setDataset(ds)
    } catch (e) {
      setUploadError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault()
    if (!dataset || !question.trim() || streaming) return

    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    let next: QueryStreamState = {
      steps: [],
      answer: '',
      code: null,
      status: 'streaming',
      errorMessage: null,
    }
    setStream(next)

    try {
      await streamQuery(
        { dataset_id: dataset.dataset_id, question: question.trim() },
        ev => {
          next = reduce(next, ev)
          setStream({ ...next })
        },
        ctrl.signal,
      )
      // if the stream ended without an explicit done/error, mark done
      setStream(prev =>
        prev.status === 'streaming' ? { ...prev, status: 'done' } : prev,
      )
    } catch (err) {
      setStream(prev => ({
        ...prev,
        status: 'error',
        errorMessage: (err as Error).message,
      }))
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:py-12">
      <header className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900 sm:text-3xl">
          Privacy-preserving data analysis
        </h1>
        <p className="mt-2 inline-flex items-center gap-2 rounded-lg bg-green-50 px-3 py-1.5 text-sm font-medium text-green-800">
          <LockIcon />
          {PRIVACY_LINE}
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* primary column */}
        <div className="space-y-6">
          {/* upload + profile */}
          <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold tracking-wide text-gray-500 uppercase">
              1. Upload data
            </h2>
            <UploadZone onFile={handleFile} busy={uploading} fileName={fileName} />

            {uploadError && (
              <div
                role="alert"
                className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
              >
                {uploadError}
              </div>
            )}

            <div className="mt-5">
              {uploading && <ProfileSkeleton />}
              {!uploading && dataset && <ProfileTable dataset={dataset} />}
              {!uploading && !dataset && !uploadError && (
                <p className="text-sm text-gray-400">
                  Upload a CSV to see an automatic profile of every column.
                </p>
              )}
            </div>
          </section>

          {/* ask */}
          <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold tracking-wide text-gray-500 uppercase">
              2. Ask a question
            </h2>
            <form onSubmit={handleAsk} className="flex flex-col gap-3 sm:flex-row">
              <label htmlFor="question" className="sr-only">
                Your question about the data
              </label>
              <input
                id="question"
                type="text"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                disabled={!dataset || streaming}
                placeholder={
                  dataset
                    ? 'e.g. What is the total revenue by month?'
                    : 'Upload a dataset first…'
                }
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:bg-gray-50 disabled:text-gray-400"
              />
              <button
                type="submit"
                disabled={!dataset || !question.trim() || streaming}
                className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 focus:ring-2 focus:ring-blue-400 focus:outline-none disabled:opacity-50"
              >
                {streaming ? 'Analysing…' : 'Ask'}
              </button>
            </form>
          </section>

          {/* answer */}
          <section className="space-y-3">
            <h2 className="text-sm font-semibold tracking-wide text-gray-500 uppercase">
              3. Answer
            </h2>
            <AnswerStream state={stream} />
          </section>
        </div>

        {/* sidebar — labelled stubs for deferred features */}
        <aside className="space-y-4">
          <p className="text-xs font-medium tracking-wide text-gray-400 uppercase">
            Coming soon
          </p>
          <StubPanel
            title="Charts"
            phase="Phase 2"
            description="Interactive charts rendered locally from your results."
          />
          <StubPanel
            title="Summary tables"
            phase="Phase 2"
            description="Structured result tables alongside the written answer."
          />
          <StubPanel
            title="Suggested follow-ups"
            phase="Phase 2"
            description="One-tap follow-up questions based on your last answer."
          />
          <StubPanel
            title="Cost & token meter"
            phase="Phase 2"
            description="Per-query token usage and a running daily cost total."
          />
          <StubPanel
            title="File library & compare"
            phase="Phase 3"
            description="Keep multiple datasets and ask questions across files."
          />
          <StubPanel
            title="Excel sheets"
            phase="Phase 3"
            description="Upload multi-sheet Excel workbooks and pick a sheet."
          />
          <StubPanel
            title="Audit-trail browser"
            phase="Phase 3"
            description="Browse every past query, the code it ran, and its result."
          />
          <StubPanel
            title="Clarify & confirm plan"
            phase="Phase 3"
            description="The agent asks to clarify and confirms its plan when ambiguous."
          />
        </aside>
      </div>
    </main>
  )
}

function reduce(state: QueryStreamState, ev: { event: string; data: unknown }): QueryStreamState {
  switch (ev.event) {
    case 'step': {
      const stage = (ev.data as { stage?: string })?.stage
      if (!stage) return state
      return { ...state, steps: [...state.steps, stage] }
    }
    case 'code': {
      const code = (ev.data as { code?: string })?.code ?? ''
      return { ...state, code }
    }
    case 'token': {
      const text = (ev.data as { text?: string })?.text ?? ''
      return { ...state, answer: state.answer + text }
    }
    case 'done':
      return { ...state, status: 'done' }
    case 'error':
      return {
        ...state,
        status: 'error',
        errorMessage: (ev.data as { message?: string })?.message ?? 'Analysis failed.',
      }
    default:
      return state
  }
}

function LockIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className="h-4 w-4 shrink-0 fill-green-700"
    >
      <path d="M10 1a4 4 0 0 0-4 4v2H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-1V5a4 4 0 0 0-4-4Zm2 6H8V5a2 2 0 1 1 4 0v2Z" />
    </svg>
  )
}
