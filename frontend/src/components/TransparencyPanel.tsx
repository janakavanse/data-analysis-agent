'use client'

import { Collapsible } from './Collapsible'
import type { LlmPayload } from '@/lib/api'

export function TransparencyPanel({ payload }: { payload: LlmPayload | null }) {
  if (!payload) return null
  return (
    <Collapsible
      title="What was sent to the LLM"
      testId="transparency-panel"
      toggleTestId="transparency-toggle"
      bodyTestId="transparency-body"
    >
      <p className="mb-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
        <strong>No bulk rows left your machine.</strong> Only the schema, a small sample, and any
        prior result were shared with the model — your full dataset stayed local.
      </p>
      <pre className="overflow-x-auto rounded-md bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
        <code className="font-mono">{JSON.stringify(payload, null, 2)}</code>
      </pre>
    </Collapsible>
  )
}
