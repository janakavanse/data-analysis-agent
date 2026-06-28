// Typed fetch client for the Personal Data Analysis Agent.
//
// IMPORTANT: the static app is served under basePath '/app/', but the JSON API
// lives at the ORIGIN ROOT (/datasets, /analyses, ...). A static export does NOT
// rewrite fetch() URLs through basePath, so we build absolute URLs from
// window.location.origin to be unambiguous in every environment.

export interface SchemaField {
  name: string
  dtype: string
}

export type SampleRow = Record<string, unknown>

export interface Dataset {
  dataset_id: string
  name: string
  schema: SchemaField[]
  sample: SampleRow[]
  row_count: number
}

export interface SummaryTable {
  columns: string[]
  rows: unknown[][]
}

export interface ChartSpec {
  // Plotly figure: { data: [...], layout: {...} }
  data?: unknown[]
  layout?: Record<string, unknown>
}

export interface LlmPayload {
  schema?: SchemaField[]
  sample?: SampleRow[]
  prior_result?: unknown
}

export interface Analysis {
  run_id: string
  status: string
  stage: string
  answer: string
  key_numbers: Record<string, unknown> | null
  summary_table: SummaryTable | null
  chart_spec: ChartSpec | null
  code: string | null
  llm_payload: LlmPayload | null
  tokens_in: number
  tokens_out: number
  cost_estimate: number
  flagged: boolean
  error_message?: string | null
}

export interface ApiError {
  code: string
  message: string
}

export class ApiRequestError extends Error {
  code: string
  status: number
  constructor(code: string, message: string, status: number) {
    super(message)
    this.code = code
    this.status = status
    this.name = 'ApiRequestError'
  }
}

function apiBase(): string {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin
  }
  // SSR/build-time fallback — never actually called in a static client export.
  return ''
}

async function parseEnvelope<T>(res: Response): Promise<T> {
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    body = null
  }

  if (!res.ok) {
    const detail = (body as { detail?: ApiError } | null)?.detail
    throw new ApiRequestError(
      detail?.code ?? 'HTTP_ERROR',
      detail?.message ?? `Request failed (${res.status})`,
      res.status,
    )
  }

  const data = (body as { data?: T } | null)?.data
  if (data === undefined || data === null) {
    throw new ApiRequestError('EMPTY_RESPONSE', 'The server returned no data.', res.status)
  }
  return data
}

/** Upload a CSV/.xlsx file. POST /datasets (multipart). */
export async function uploadDataset(file: File): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${apiBase()}/datasets`, {
    method: 'POST',
    body: form,
  })
  return parseEnvelope<Dataset>(res)
}

/** Ask a plain-language question about a dataset. POST /analyses. */
export async function runAnalysis(datasetId: string, question: string): Promise<Analysis> {
  const res = await fetch(`${apiBase()}/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, question }),
  })
  return parseEnvelope<Analysis>(res)
}

/** Fetch a run (used for staged-progress polling / history). GET /analyses/{id}. */
export async function getAnalysis(runId: string): Promise<Analysis> {
  const res = await fetch(`${apiBase()}/analyses/${runId}`)
  return parseEnvelope<Analysis>(res)
}

/** Fetch dataset metadata. GET /datasets/{id}. */
export async function getDataset(datasetId: string): Promise<Dataset> {
  const res = await fetch(`${apiBase()}/datasets/${datasetId}`)
  return parseEnvelope<Dataset>(res)
}
