'use client'

import { useEffect, useRef, useState } from 'react'
import { getQuery, NetworkError } from '../lib/api'
import type { QueryDetail } from '../lib/api'
import { AnswerCard } from './AnswerCard'

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'needs_clarification', 'unanswerable'])
const POLL_INTERVAL_MS = 750
// Heuristic only: if a query sticks on "running_analysis" for several poll
// cycles in a row, briefly surface a retry hint. The polling response does
// not carry a dedicated "retry started" signal, so this is a best-effort
// approximation per spec/ui.md, not a precise detection of the retry edge.
const RETRY_HINT_STUCK_CYCLES = 4
const RETRY_HINT_WINDOW = 8

function statusLabel(status: string, stuckCycles: number): string {
  if (
    status === 'running_analysis' &&
    stuckCycles >= RETRY_HINT_STUCK_CYCLES &&
    stuckCycles % RETRY_HINT_WINDOW < RETRY_HINT_STUCK_CYCLES
  ) {
    return "That didn't work — retrying with a corrected approach…"
  }
  switch (status) {
    case 'pending':
      return 'Preparing…'
    case 'generating_code':
      return 'Generating code…'
    case 'running_analysis':
      return 'Running analysis…'
    default:
      return 'Working…'
  }
}

interface Props {
  queryId: string
  question: string
  turnIndex: number
  initialStatus: string
  onTerminal: (queryId: string) => void
  onNetworkError: (message: string) => void
  onFollowupClick?: (question: string) => void
}

export function QueryTurn({
  queryId,
  question,
  initialStatus,
  onTerminal,
  onNetworkError,
  onFollowupClick,
}: Props) {
  const [status, setStatus] = useState(initialStatus)
  const [detail, setDetail] = useState<QueryDetail | null>(null)
  const [stuckCycles, setStuckCycles] = useState(0)
  const lastStatusRef = useRef(initialStatus)
  const notifiedTerminalRef = useRef(false)

  useEffect(() => {
    if (TERMINAL_STATUSES.has(status)) return
    let cancelled = false
    const interval = setInterval(async () => {
      try {
        const result = await getQuery(queryId)
        if (cancelled) return
        setDetail(result)
        if (result.status === lastStatusRef.current) {
          setStuckCycles(c => c + 1)
        } else {
          lastStatusRef.current = result.status
          setStuckCycles(0)
        }
        setStatus(result.status)
      } catch (err) {
        if (err instanceof NetworkError) {
          onNetworkError(err.message)
        }
      }
    }, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [queryId, status, onNetworkError])

  useEffect(() => {
    if (TERMINAL_STATUSES.has(status) && !notifiedTerminalRef.current) {
      notifiedTerminalRef.current = true
      onTerminal(queryId)
    }
  }, [status, queryId, onTerminal])

  return (
    <div className="space-y-3" data-testid="qa-turn" data-status={status}>
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2.5 text-sm text-white shadow-sm">
          {question}
        </div>
      </div>

      {!TERMINAL_STATUSES.has(status) && (
        <div className="flex items-center gap-2 text-sm text-gray-500" data-testid="query-status">
          <span className="h-3 w-3 animate-pulse rounded-full bg-blue-400" aria-hidden />
          {statusLabel(status, stuckCycles)}
        </div>
      )}

      {status === 'completed' && detail && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm" data-testid="answer-card">
          <AnswerCard detail={detail} onFollowupClick={onFollowupClick} />
        </div>
      )}

      {status === 'needs_clarification' && (
        <div
          className="flex items-start gap-2 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800"
          data-testid="clarification-bubble"
        >
          <span aria-hidden>💬</span>
          <div>
            <p className="font-medium">{detail?.error ?? 'Could you clarify your question?'}</p>
            <p className="mt-1 text-blue-600">Answer in the box below to continue.</p>
          </div>
        </div>
      )}

      {status === 'unanswerable' && (
        <div
          className="flex items-start gap-2 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800"
          data-testid="unanswerable-bubble"
        >
          <span aria-hidden>💬</span>
          <div>
            <p className="font-medium">{detail?.error ?? "This can't be answered from this data."}</p>
          </div>
        </div>
      )}

      {status === 'failed' && (
        <div
          className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
          role="alert"
          data-testid="query-failed"
        >
          <span aria-hidden>⚠️</span>
          <div>
            <p className="font-medium">{detail?.error ?? 'This question could not be answered.'}</p>
            <p className="mt-1 text-red-600">Try rephrasing your question, e.g. using the exact column names.</p>
          </div>
        </div>
      )}
    </div>
  )
}
