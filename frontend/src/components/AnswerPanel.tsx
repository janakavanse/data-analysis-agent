'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Analysis } from '@/lib/api'
import { Chart } from './Chart'
import { SummaryTable } from './SummaryTable'
import { CodePanel } from './CodePanel'
import { TransparencyPanel } from './TransparencyPanel'
import { CostLine } from './CostLine'
import { StubBadge } from './StubBadge'

export function AnswerPanel({ analysis }: { analysis: Analysis }) {
  const keyNumbers = analysis.key_numbers ?? {}
  const keyEntries = Object.entries(keyNumbers)

  return (
    <section
      data-testid="answer-panel"
      className="space-y-5 rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900">Answer</h2>
        {analysis.flagged && (
          <span
            data-testid="flagged-badge"
            title="The agent flagged this as a best-guess answer"
            className="rounded-full border border-amber-300 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700"
          >
            Best-guess
          </span>
        )}
      </div>

      {/* Prose answer — rendered as markdown, never raw text. */}
      <div
        data-testid="answer-prose"
        className="prose-answer text-[15px] leading-relaxed text-gray-800"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {analysis.answer || '_No answer text was returned._'}
        </ReactMarkdown>
      </div>

      {/* Key numbers — headline figures. */}
      {keyEntries.length > 0 && (
        <div data-testid="key-numbers" className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {keyEntries.map(([k, v]) => (
            <div key={k} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-gray-400">{prettify(k)}</div>
              <div className="mt-0.5 text-lg font-semibold text-gray-900">{formatValue(v)}</div>
            </div>
          ))}
        </div>
      )}

      <Chart spec={analysis.chart_spec} />

      <SummaryTable table={analysis.summary_table} />

      {/* Follow-up suggestions — labelled stub. */}
      <div
        data-testid="followup-stub"
        aria-disabled="true"
        className="flex cursor-not-allowed select-none flex-wrap items-center gap-2 rounded-lg border border-dashed border-gray-200 bg-gray-50/60 px-3 py-2 opacity-70"
      >
        <span className="text-xs font-medium text-gray-500">Follow-up suggestions</span>
        <StubBadge phase="Phase 2" />
      </div>

      <CodePanel code={analysis.code} />
      <TransparencyPanel payload={analysis.llm_payload} />

      <CostLine
        cost={analysis.cost_estimate}
        tokensIn={analysis.tokens_in}
        tokensOut={analysis.tokens_out}
      />
    </section>
  )
}

function prettify(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 4 })
  return String(v)
}
