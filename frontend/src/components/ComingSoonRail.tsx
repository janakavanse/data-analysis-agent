'use client'

function PhaseBadge({ phase }: { phase: number }) {
  return (
    <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
      Coming in Phase {phase}
    </span>
  )
}

function StubCard({
  title,
  phase,
  description,
  children,
}: {
  title: string
  phase: number
  description: string
  children?: React.ReactNode
}) {
  return (
    <div
      aria-disabled="true"
      className="select-none rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 p-4 opacity-90"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-500">{title}</h3>
        <PhaseBadge phase={phase} />
      </div>
      <p className="mt-1 text-xs text-slate-400">{description}</p>
      {children && <div className="mt-3">{children}</div>}
    </div>
  )
}

export default function ComingSoonRail() {
  return (
    <aside className="space-y-4" aria-label="Upcoming features (not yet available)">
      <p className="px-1 text-xs font-medium uppercase tracking-wide text-slate-400">Coming soon</p>

      <StubCard title="Charts" phase={2} description="Inline charts rendered locally alongside your answers.">
        <div className="flex h-20 items-end gap-1.5 rounded-lg bg-white/70 p-3">
          {[40, 70, 30, 90, 55].map((h, i) => (
            <div key={i} className="flex-1 rounded-t bg-slate-200" style={{ height: `${h}%` }} />
          ))}
        </div>
      </StubCard>

      <StubCard title="One-shot report" phase={3} description="Auto profile + key findings + a few charts, in one click.">
        <button
          type="button"
          disabled
          className="w-full cursor-not-allowed rounded-lg bg-slate-200 px-3 py-2 text-sm font-medium text-slate-400"
        >
          Generate report
        </button>
      </StubCard>

      <StubCard title="Excel support" phase={4} description="Upload .xlsx / .xls files just like a CSV." />

      <StubCard title="Insights" phase={5} description="Auto-surfaced findings — outliers, skew, dominant categories.">
        <div className="space-y-1.5 rounded-lg bg-white/70 p-3">
          <div className="h-2 w-3/4 rounded bg-slate-200" />
          <div className="h-2 w-1/2 rounded bg-slate-200" />
          <div className="h-2 w-2/3 rounded bg-slate-200" />
        </div>
      </StubCard>
    </aside>
  )
}
