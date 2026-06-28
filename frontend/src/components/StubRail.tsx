'use client'

import { StubItem, StubBadge } from './StubBadge'

/**
 * Left rail of clearly-labelled, non-functional Phase-1 stubs. Each reads as a
 * planned feature, visibly disabled — never as a broken control.
 */
export function StubRail() {
  return (
    <aside
      data-testid="stub-rail"
      className="hidden w-72 shrink-0 space-y-5 lg:block"
    >
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Sessions</h3>
          <StubBadge phase="Phase 2" />
        </div>
        <button
          type="button"
          disabled
          className="mb-2 w-full cursor-not-allowed rounded-lg border border-dashed border-gray-200 bg-gray-50/60 px-3 py-2 text-left text-sm font-medium text-gray-400 opacity-70"
          title="New session — coming in Phase 2"
        >
          + New session
        </button>
        <p className="text-xs text-gray-400">
          Saved &amp; resumable sessions arrive in Phase 2.
        </p>
      </div>

      <div className="space-y-2">
        <StubItem label="Dataset profile" phase="Phase 2" description="Full column statistics" />
        <StubItem label="Column notes & business rules" phase="Phase 3" description="Annotate your data" />
        <StubItem label="Daily cost total" phase="Phase 3" description="Running spend tracker" />
        <StubItem label="Export" phase="Phase 4" description="CSV · chart image · report" />
        <StubItem label="Save as dataset" phase="Phase 4" description="Reuse a derived table" />
        <StubItem label="Analysis library" phase="Phase 4" description="Re-run past analyses" />
        <StubItem label="Connect a database" phase="Phase 5" description="Attach DuckDB / SQLite" />
        <StubItem label="Join multiple files" phase="Phase 5" description="Inferred relationships" />
      </div>
    </aside>
  )
}
