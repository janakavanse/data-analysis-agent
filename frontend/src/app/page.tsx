'use client'

import { useState } from 'react'
import { runAnalysis, ApiRequestError, type Dataset, type Analysis } from '@/lib/api'
import { UploadZone } from '@/components/UploadZone'
import { QuestionBox } from '@/components/QuestionBox'
import { StagedProgress } from '@/components/StagedProgress'
import { AnswerPanel } from '@/components/AnswerPanel'
import { StubRail } from '@/components/StubRail'

export default function Home() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleAsk(question: string) {
    if (!dataset) return
    setLoading(true)
    setError(null)
    setAnalysis(null)
    try {
      const result = await runAnalysis(dataset.dataset_id, question)
      setAnalysis(result)
    } catch (e) {
      if (e instanceof ApiRequestError) {
        setError(e.message)
      } else {
        setError('Could not reach the server — is it running?')
      }
    } finally {
      setLoading(false)
    }
  }

  function handleDatasetLoaded(ds: Dataset) {
    setDataset(ds)
    setAnalysis(null)
    setError(null)
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          Personal Data Analysis Agent
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload a spreadsheet and ask questions in plain language. Your full data stays on your
          machine — only the schema and a small sample are shared with the model.
        </p>
      </header>

      <div className="flex gap-6">
        <StubRail />

        <div className="min-w-0 flex-1 space-y-5">
          <UploadZone dataset={dataset} onLoaded={handleDatasetLoaded} />

          <QuestionBox enabled={!!dataset} loading={loading} onAsk={handleAsk} />

          {loading && <StagedProgress />}

          {error && !loading && (
            <div
              data-testid="analysis-error"
              role="alert"
              className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
            >
              <p className="font-medium">The analysis couldn&apos;t be completed.</p>
              <p className="mt-1 text-red-600">{error}</p>
            </div>
          )}

          {analysis && !loading && <AnswerPanel analysis={analysis} />}

          {!dataset && !loading && (
            <div
              data-testid="empty-no-dataset"
              className="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center"
            >
              <p className="text-base font-medium text-gray-700">Upload a dataset to begin</p>
              <p className="mt-1 text-sm text-gray-400">
                Drop a CSV or Excel file above, then ask a question about it.
              </p>
            </div>
          )}

          {dataset && !analysis && !loading && !error && (
            <div
              data-testid="empty-no-question"
              className="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center"
            >
              <p className="text-base font-medium text-gray-700">Ask your first question</p>
              <p className="mt-1 text-sm text-gray-400">
                Try &ldquo;What were total sales by month?&rdquo; or &ldquo;Which category sold the
                most?&rdquo;
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  )
}
