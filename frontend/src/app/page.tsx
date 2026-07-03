'use client'

import { useCallback, useEffect, useState } from 'react'
import { createSession, createQuery, ApiError, NetworkError } from './lib/api'
import type { DatasetProfile } from './lib/api'
import { UploadScreen } from './components/UploadScreen'
import { DatasetProfileCard } from './components/DatasetProfileCard'
import { QAThread } from './components/QAThread'
import type { TurnRecord } from './components/QAThread'
import { ErrorBanner } from './components/ErrorBanner'

const SESSION_STORAGE_KEY = 'data-analysis-agent:session'

interface StoredSession {
  sessionId: string
  dataset: DatasetProfile | null
}

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [dataset, setDataset] = useState<DatasetProfile | null>(null)
  const [bannerError, setBannerError] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [turns, setTurns] = useState<TurnRecord[]>([])
  const [inFlightQueryId, setInFlightQueryId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const initSession = useCallback(async () => {
    setSessionError(null)
    try {
      const stored = typeof window !== 'undefined' ? window.sessionStorage.getItem(SESSION_STORAGE_KEY) : null
      if (stored) {
        const parsed: StoredSession = JSON.parse(stored)
        setSessionId(parsed.sessionId)
        if (parsed.dataset) setDataset(parsed.dataset)
        return
      }
      const session = await createSession()
      setSessionId(session.session_id)
    } catch (err) {
      if (err instanceof NetworkError) {
        setBannerError(err.message)
      } else {
        setSessionError('Could not start a session. Please reload the page.')
      }
    }
  }, [])

  useEffect(() => {
    initSession()
  }, [initSession])

  useEffect(() => {
    if (!sessionId || typeof window === 'undefined') return
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ sessionId, dataset }))
  }, [sessionId, dataset])

  function handleUploaded(profile: DatasetProfile) {
    setDataset(profile)
    setTurns([])
    setInFlightQueryId(null)
    setNotice(null)
  }

  function handleReplaceClick() {
    setDataset(null)
    setTurns([])
    setInFlightQueryId(null)
  }

  async function handleAsk(question: string) {
    if (!sessionId || !dataset || inFlightQueryId) return
    setNotice(null)
    try {
      const created = await createQuery(sessionId, dataset.dataset_id, question)
      setTurns(t => [
        ...t,
        { queryId: created.query_id, question, turnIndex: created.turn_index, initialStatus: created.status },
      ])
      setInFlightQueryId(created.query_id)
    } catch (err) {
      if (err instanceof NetworkError) {
        setBannerError(err.message)
      } else if (err instanceof ApiError && err.status === 409) {
        setNotice('Still working on the previous question…')
      } else if (err instanceof ApiError) {
        setNotice(err.message)
      } else {
        setNotice('Something went wrong submitting your question. Please try again.')
      }
    }
  }

  function handleTerminal(queryId: string) {
    setInFlightQueryId(current => (current === queryId ? null : current))
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Data Analysis Agent</h1>
        <p className="text-sm text-gray-500">Upload a spreadsheet, then ask questions about it in plain English.</p>
      </header>

      {bannerError && <ErrorBanner message={bannerError} onDismiss={() => setBannerError(null)} />}

      {sessionError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          {sessionError}
        </div>
      )}

      {dataset && <DatasetProfileCard dataset={dataset} onReplaceClick={handleReplaceClick} />}

      {!dataset ? (
        <UploadScreen sessionId={sessionId} onUploaded={handleUploaded} onNetworkError={setBannerError} />
      ) : (
        <QAThread
          turns={turns}
          inFlight={inFlightQueryId !== null}
          notice={notice}
          onAsk={handleAsk}
          onTerminal={handleTerminal}
          onNetworkError={setBannerError}
        />
      )}
    </main>
  )
}
