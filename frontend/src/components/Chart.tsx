'use client'

import dynamic from 'next/dynamic'
import type { ChartSpec } from '@/lib/api'

// Plotly must be client-only in a static export: no SSR. The dynamic import keeps
// plotly.js out of the server bundle and renders the figure entirely in the browser.
const Plot = dynamic(() => import('react-plotly.js'), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-gray-400">
      Loading chart…
    </div>
  ),
})

export function Chart({ spec }: { spec: ChartSpec | null }) {
  const hasData = !!spec && Array.isArray(spec.data) && spec.data.length > 0
  if (!hasData) {
    return (
      <div
        data-testid="chart-empty"
        className="flex h-32 items-center justify-center rounded-lg border border-dashed border-gray-200 bg-gray-50 text-sm text-gray-400"
      >
        No chart was produced for this answer.
      </div>
    )
  }

  return (
    <div data-testid="chart" className="w-full overflow-hidden rounded-lg border border-gray-200">
      <Plot
        data={spec!.data as Plotly.Data[]}
        layout={{
          autosize: true,
          margin: { t: 30, r: 16, b: 40, l: 48 },
          ...(spec!.layout ?? {}),
        }}
        config={{ displaylogo: false, responsive: true }}
        useResizeHandler
        style={{ width: '100%', height: '360px' }}
      />
    </div>
  )
}
