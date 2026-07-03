'use client'

import dynamic from 'next/dynamic'
import type { ChartSpec } from '../lib/api'

// Plotly needs `window`, so it must never be evaluated during the Next.js
// static export's server-side render pass — dynamic import with ssr:false
// defers it to the browser only.
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

export function PlotlyChart({ spec }: { spec: ChartSpec }) {
  return (
    <div data-testid="chart" className="rounded-lg border border-gray-200 bg-white p-2">
      <Plot
        data={(spec.data ?? []) as Plotly.Data[]}
        layout={{
          autosize: true,
          margin: { t: 32, r: 16, b: 40, l: 48 },
          ...(spec.layout ?? {}),
        }}
        useResizeHandler
        style={{ width: '100%', height: '360px' }}
        config={{ displaylogo: false, responsive: true }}
      />
    </div>
  )
}
