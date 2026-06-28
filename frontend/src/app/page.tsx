'use client'

import { useEffect, useRef, useState } from 'react'
import {
  askQuestion,
  getSession,
  type DatasetMeta,
  type ResultTable,
} from '@/lib/api'
import UploadZone from '@/components/UploadZone'
import DatasetHeader from '@/components/DatasetHeader'
import ComingSoonRail from '@/components/ComingSoonRail'
import AssistantBubble, { type AssistantTurn } from '@/components/AssistantBubble'

const STORAGE_KEY = 'analysis.session_id'

type ChatItem =
  | { role: 'user'; content: string }
  | ({ role: 'assistant' } & AssistantTurn)

type DatasetState = {
  session_id: string
  filename: string
  row_count: number
  schema: DatasetMeta['schema']
}

export default function Home() {
  const [dataset, setDataset] = useState<DatasetState | null>(null)
  const [messages, setMessages] = useState<ChatItem[]>([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [restoring, setRestoring] = useState(true)
  const transcriptEndRef = useRef<HTMLDivElement>(null)

  // On load, replay a prior session if one exists (server-side history).
  useEffect(() => {
    const stored = typeof window !== 'undefined' ? window.localStorage.getItem(STORAGE_KEY) : null
    if (!stored) {
      setRestoring(false)
      return
    }
    let active = true
    ;(async () => {
      try {
        const detail = await getSession(stored)
        if (!active) return
        setDataset({
          session_id: detail.session_id,
          filename: detail.dataset.filename,
          row_count: detail.dataset.row_count,
          schema: detail.dataset.schema,
        })
        setMessages(
          detail.messages.map(m =>
            m.role === 'user'
              ? { role: 'user', content: m.content }
              : {
                  role: 'assistant',
                  answer: m.content,
                  code: m.code ?? null,
                  result_table: m.result_table ?? null,
                },
          ),
        )
      } catch {
        // Stale/unknown session — start fresh.
        if (active) window.localStorage.removeItem(STORAGE_KEY)
      } finally {
        if (active) setRestoring(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, asking])

  function handleLoaded(meta: DatasetMeta) {
    window.localStorage.setItem(STORAGE_KEY, meta.session_id)
    setDataset({
      session_id: meta.session_id,
      filename: meta.filename,
      row_count: meta.row_count,
      schema: meta.schema,
    })
    setMessages([])
  }

  function handleReset() {
    window.localStorage.removeItem(STORAGE_KEY)
    setDataset(null)
    setMessages([])
    setQuestion('')
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q || !dataset || asking) return

    setMessages(prev => [...prev, { role: 'user', content: q }])
    setQuestion('')
    setAsking(true)

    try {
      const res = await askQuestion(dataset.session_id, q)
      const turn: ChatItem = {
        role: 'assistant',
        answer: res.answer,
        code: res.code,
        result_table: res.result_table as ResultTable | null,
        failed: res.status === 'failed',
      }
      setMessages(prev => [...prev, turn])
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not analyze that — try rephrasing.'
      setMessages(prev => [...prev, { role: 'assistant', answer: message, failed: true }])
    } finally {
      setAsking(false)
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:py-10">
      <header className="mb-8">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-lg font-bold text-white">
            ⌘
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">Local Data Analyst</h1>
            <p className="text-sm text-slate-500">
              Chat with your spreadsheet — privately. Your data never leaves this machine; every answer shows its work.
            </p>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px]">
        {/* Main column: upload + transcript + input */}
        <section className="flex min-h-[60vh] flex-col gap-6">
          {restoring ? (
            <div className="flex flex-1 items-center justify-center rounded-2xl border border-slate-200 bg-white py-20 text-sm text-slate-400">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-500" />
              <span className="ml-2">Restoring your session…</span>
            </div>
          ) : !dataset ? (
            <UploadZone onLoaded={handleLoaded} busy={false} />
          ) : (
            <>
              <DatasetHeader
                filename={dataset.filename}
                rowCount={dataset.row_count}
                schema={dataset.schema}
                onReset={handleReset}
              />

              <div className="flex flex-1 flex-col rounded-2xl border border-slate-200 bg-slate-50/50">
                <div className="flex-1 space-y-4 overflow-y-auto p-5">
                  {messages.length === 0 && !asking && (
                    <div className="flex h-full flex-col items-center justify-center py-12 text-center">
                      <p className="text-sm font-medium text-slate-600">Ask a question about your data</p>
                      <p className="mt-1 max-w-sm text-xs text-slate-400">
                        Try “what’s the average of a numeric column?” or “how many rows per category?”.
                        Then click “Show the work” to see the exact pandas and the numbers.
                      </p>
                    </div>
                  )}

                  {messages.map((m, i) =>
                    m.role === 'user' ? (
                      <div key={i} className="flex justify-end">
                        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-2.5 text-sm text-white shadow-sm">
                          {m.content}
                        </div>
                      </div>
                    ) : (
                      <AssistantBubble key={i} turn={m} />
                    ),
                  )}

                  {asking && (
                    <div className="flex justify-start">
                      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3 shadow-sm">
                        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
                        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
                        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" />
                        <span className="ml-1 text-xs text-slate-400">running locally…</span>
                      </div>
                    </div>
                  )}

                  <div ref={transcriptEndRef} />
                </div>

                <form onSubmit={handleAsk} className="flex items-center gap-2 border-t border-slate-200 p-3">
                  <input
                    type="text"
                    value={question}
                    onChange={e => setQuestion(e.target.value)}
                    disabled={asking}
                    placeholder="Ask a question about your data…"
                    className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                  />
                  <button
                    type="submit"
                    disabled={asking || !question.trim()}
                    className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {asking ? 'Asking…' : 'Send'}
                  </button>
                </form>
              </div>
            </>
          )}
        </section>

        <ComingSoonRail />
      </div>
    </main>
  )
}
