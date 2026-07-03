'use client'

interface Props {
  message: string
  onDismiss: () => void
}

export function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 shadow-sm"
    >
      <span className="flex items-center gap-2">
        <span aria-hidden>⚠️</span>
        {message}
      </span>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 rounded px-2 py-1 text-red-700 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-400"
      >
        Dismiss
      </button>
    </div>
  )
}
