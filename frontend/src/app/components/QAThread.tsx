'use client'

import { useEffect, useRef, useState } from 'react'
import { QueryTurn } from './QueryTurn'

export interface TurnRecord {
  queryId: string
  question: string
  turnIndex: number
  initialStatus: string
}

interface Props {
  turns: TurnRecord[]
  inFlight: boolean
  notice: string | null
  onAsk: (question: string) => void
  onTerminal: (queryId: string) => void
  onNetworkError: (message: string) => void
}

export function QAThread({ turns, inFlight, notice, onAsk, onTerminal, onNetworkError }: Props) {
  const [question, setQuestion] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns.length])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || inFlight) return
    onAsk(trimmed)
    setQuestion('')
  }

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="flex flex-col gap-6" data-testid="qa-thread">
        {turns.length === 0 && (
          <p className="rounded-lg border border-dashed border-gray-200 bg-white p-6 text-center text-sm text-gray-400">
            Ask a question about your data to get started — e.g. &quot;what is the average amount?&quot;
          </p>
        )}
        {turns.map(turn => (
          <QueryTurn
            key={turn.queryId}
            queryId={turn.queryId}
            question={turn.question}
            turnIndex={turn.turnIndex}
            initialStatus={turn.initialStatus}
            onTerminal={onTerminal}
            onNetworkError={onNetworkError}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {notice && <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">{notice}</p>}

      <form
        onSubmit={handleSubmit}
        className="sticky bottom-0 space-y-1.5 border-t border-gray-200 bg-gray-50 pt-3 pb-2"
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            disabled={inFlight}
            placeholder="Ask a question about your data…"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-100"
            aria-label="Ask a question about your data"
            data-testid="question-input"
          />
          <button
            type="submit"
            disabled={inFlight || !question.trim()}
            className="shrink-0 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="send-button"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-400">
          Tip: reference exact column names for best results — clarifying questions for ambiguous phrasing arrive in
          Phase 2.
        </p>
      </form>
    </div>
  )
}
