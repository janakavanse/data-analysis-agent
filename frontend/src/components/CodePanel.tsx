'use client'

import { useState } from 'react'
import { Collapsible } from './Collapsible'

export function CodePanel({ code }: { code: string | null }) {
  const [copied, setCopied] = useState(false)
  if (!code) return null

  async function copy() {
    try {
      await navigator.clipboard.writeText(code ?? '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <Collapsible
      title="Show code"
      testId="code-panel"
      toggleTestId="code-toggle"
      bodyTestId="code-body"
      right={
        <span
          role="button"
          tabIndex={0}
          data-testid="copy-code"
          onClick={e => {
            e.stopPropagation()
            void copy()
          }}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.stopPropagation()
              void copy()
            }
          }}
          className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
        >
          {copied ? 'Copied' : 'Copy'}
        </span>
      }
    >
      <pre className="overflow-x-auto rounded-md bg-gray-900 p-3 text-xs leading-relaxed text-gray-100">
        <code className="font-mono">{code}</code>
      </pre>
    </Collapsible>
  )
}
