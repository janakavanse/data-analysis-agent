'use client'

import { useState } from 'react'

interface CollapsibleProps {
  title: string
  testId?: string
  toggleTestId?: string
  bodyTestId?: string
  defaultOpen?: boolean
  right?: React.ReactNode
  children: React.ReactNode
}

export function Collapsible({
  title,
  testId,
  toggleTestId,
  bodyTestId,
  defaultOpen = false,
  right,
  children,
}: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div data-testid={testId} className="rounded-lg border border-gray-200 bg-white">
      <button
        type="button"
        data-testid={toggleTestId}
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm font-medium text-gray-800 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500"
      >
        <span className="flex items-center gap-2">
          <span
            aria-hidden
            className={`inline-block text-gray-400 transition-transform ${open ? 'rotate-90' : ''}`}
          >
            ▶
          </span>
          {title}
        </span>
        {right}
      </button>
      {open && (
        <div data-testid={bodyTestId} className="border-t border-gray-100 px-4 py-3">
          {children}
        </div>
      )}
    </div>
  )
}
