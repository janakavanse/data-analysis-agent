'use client'

import { useState } from 'react'

interface QuestionBoxProps {
  enabled: boolean
  loading: boolean
  onAsk: (question: string) => void
}

export function QuestionBox({ enabled, loading, onAsk }: QuestionBoxProps) {
  const [question, setQuestion] = useState('')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q || !enabled || loading) return
    onAsk(q)
  }

  return (
    <form
      onSubmit={submit}
      data-testid="question-box"
      className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
    >
      <label htmlFor="question" className="mb-2 block text-sm font-semibold text-gray-900">
        Ask a question
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id="question"
          data-testid="question-input"
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          disabled={!enabled || loading}
          placeholder={
            enabled
              ? 'e.g. What were total sales by month?'
              : 'Upload a dataset first to ask a question'
          }
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400"
        />
        <button
          type="submit"
          data-testid="ask-button"
          disabled={!enabled || loading || !question.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50"
        >
          {loading && (
            <span
              aria-hidden
              className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
            />
          )}
          {loading ? 'Analysing…' : 'Ask'}
        </button>
      </div>
      {!enabled && (
        <p className="mt-2 text-xs text-gray-400">
          The Ask button activates once a dataset is loaded.
        </p>
      )}
    </form>
  )
}
