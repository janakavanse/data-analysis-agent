// A clearly-labelled, non-functional placeholder for a deferred feature.
// Styled distinct from live controls (dashed border, muted, "Coming soon" badge)
// so it can never be mistaken for a broken live control.

export function StubPanel({
  title,
  phase,
  description,
}: {
  title: string
  phase: string
  description: string
}) {
  return (
    <section
      aria-disabled="true"
      data-stub="true"
      className="rounded-xl border border-dashed border-gray-300 bg-gray-50/60 p-4 text-gray-400 select-none"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-500">{title}</h3>
        <span className="shrink-0 rounded-full border border-gray-300 bg-white px-2 py-0.5 text-[11px] font-medium tracking-wide text-gray-400 uppercase">
          Coming soon
        </span>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed">{description}</p>
      <p className="mt-2 text-[11px] font-medium text-gray-400">{phase}</p>
    </section>
  )
}
