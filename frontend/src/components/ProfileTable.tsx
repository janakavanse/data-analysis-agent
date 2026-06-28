import type { Dataset, ProfileColumn } from '../lib/api'

function fmtNum(v: number | null): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  if (Number.isInteger(v)) return v.toLocaleString()
  return v.toLocaleString(undefined, { maximumFractionDigits: 3 })
}

export function ProfileSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading profile">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-7 w-full animate-pulse rounded bg-gray-100 motion-reduce:animate-none" />
      ))}
    </div>
  )
}

export function ProfileTable({ dataset }: { dataset: Dataset }) {
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-gray-900">{dataset.name}</h2>
        <span className="text-xs text-gray-500">
          {dataset.row_count.toLocaleString()} rows · {dataset.profile.columns.length} columns
        </span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-gray-50 text-xs tracking-wide text-gray-500 uppercase">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">Column</th>
              <th scope="col" className="px-3 py-2 font-medium">Type</th>
              <th scope="col" className="px-3 py-2 font-medium">Missing</th>
              <th scope="col" className="px-3 py-2 font-medium">Min</th>
              <th scope="col" className="px-3 py-2 font-medium">Max</th>
              <th scope="col" className="px-3 py-2 font-medium">Mean</th>
              <th scope="col" className="px-3 py-2 font-medium">Distinct</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {dataset.profile.columns.map((c: ProfileColumn) => (
              <tr key={c.name} className="hover:bg-gray-50">
                <td className="px-3 py-2 font-medium text-gray-900">{c.name}</td>
                <td className="px-3 py-2 text-gray-600">
                  <code className="rounded bg-gray-100 px-1 py-0.5 text-xs text-gray-700">{c.dtype}</code>
                </td>
                <td className="px-3 py-2 text-gray-600">{fmtNum(c.missing)}</td>
                <td className="px-3 py-2 text-gray-600">{fmtNum(c.min)}</td>
                <td className="px-3 py-2 text-gray-600">{fmtNum(c.max)}</td>
                <td className="px-3 py-2 text-gray-600">{fmtNum(c.mean)}</td>
                <td className="px-3 py-2 text-gray-600">{fmtNum(c.distinct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
