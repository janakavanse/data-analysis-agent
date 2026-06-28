// API client for the local analysis backend.
// Served single-origin at :8001 — the static app lives at /app, the API at root,
// so all calls use root-relative paths (same origin, no CORS).

export type SchemaColumn = { name: string; dtype: string }

export type ResultTable = {
  kind: 'table' | 'scalar' | string
  columns?: string[]
  rows?: Array<Array<string | number | boolean | null>>
  value?: string | number | boolean | null
}

export type DatasetMeta = {
  session_id: string
  filename: string
  row_count: number
  schema: SchemaColumn[]
  sample_rows: Array<Record<string, unknown>>
}

export type AskResult = {
  answer: string
  code: string | null
  result_table: ResultTable | null
  status: 'completed' | 'failed' | string
}

export type SessionMessage = {
  role: 'user' | 'assistant'
  content: string
  code?: string | null
  result_table?: ResultTable | null
  created_at?: string
}

export type SessionDetail = {
  session_id: string
  dataset: { filename: string; row_count: number; schema: SchemaColumn[] }
  messages: SessionMessage[]
}

export class ApiError extends Error {
  code: string
  status: number
  constructor(message: string, code: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

async function parseError(res: Response): Promise<never> {
  let message = `Request failed (${res.status})`
  let code = 'error'
  try {
    const body = await res.json()
    if (body?.detail?.message) message = body.detail.message
    if (body?.detail?.code) code = body.detail.code
  } catch {
    // non-JSON body — keep the default message
  }
  throw new ApiError(message, code, res.status)
}

export async function uploadDataset(file: File): Promise<DatasetMeta> {
  const form = new FormData()
  form.append('file', file)
  let res: Response
  try {
    res = await fetch('/datasets', { method: 'POST', body: form })
  } catch {
    throw new ApiError('Network error — is the server running?', 'network', 0)
  }
  if (!res.ok) return parseError(res)
  const body = await res.json()
  return body.data as DatasetMeta
}

export async function askQuestion(sessionId: string, question: string): Promise<AskResult> {
  let res: Response
  try {
    res = await fetch(`/sessions/${sessionId}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
  } catch {
    throw new ApiError('Network error — is the server running?', 'network', 0)
  }
  if (!res.ok) return parseError(res)
  const body = await res.json()
  return body.data as AskResult
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  let res: Response
  try {
    res = await fetch(`/sessions/${sessionId}`)
  } catch {
    throw new ApiError('Network error — is the server running?', 'network', 0)
  }
  if (!res.ok) return parseError(res)
  const body = await res.json()
  return body.data as SessionDetail
}
