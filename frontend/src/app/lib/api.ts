// Thin fetch client for the data-analysis-agent API (spec/api.md).
// Every fetch call uses a path relative to the page origin (e.g. "/sessions"),
// never an absolute origin — basePath only affects page routing, not fetch().

export class NetworkError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NetworkError'
  }
}

export class ApiError extends Error {
  status: number
  code?: string
  body: unknown

  constructor(status: number, message: string, code?: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.body = body
  }
}

export interface ColumnSchema {
  name: string
  dtype: string
  null_count: number
  min: number | null
  max: number | null
  distinct_sample: string[] | null
}

export interface DatasetProfile {
  dataset_id: string
  original_filename: string
  file_type: string
  row_count: number
  column_count: number
  schema: ColumnSchema[]
}

export interface SessionInfo {
  session_id: string
  created_at: string
}

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface QueryCreated {
  query_id: string
  status: string
  turn_index: number
}

export interface QueryDetail {
  query_id: string
  status: string
  question: string
  turn_index?: number
  answer_text?: string | null
  result_table?: Record<string, unknown>[] | null
  generated_code?: string | null
  retry_count?: number
  token_usage?: TokenUsage | null
  chart_spec?: unknown
  suggested_followups?: string[] | null
  error?: string | null
  created_at?: string
  completed_at?: string | null
}

export interface QueryHistoryItem {
  query_id: string
  turn_index: number
  question: string
  status: string
  answer_text?: string | null
}

async function sendRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new NetworkError("Couldn't reach the server — check it's running and try again.")
  }

  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    body = null
  }

  if (!res.ok) {
    const parsed = body as { detail?: { code?: string; message?: string } } | null
    const message = parsed?.detail?.message ?? `Request failed (${res.status})`
    throw new ApiError(res.status, message, parsed?.detail?.code, body)
  }

  const envelope = body as { data?: T } | null
  return envelope?.data as T
}

export function createSession(): Promise<SessionInfo> {
  return sendRequest<SessionInfo>('/sessions', { method: 'POST' })
}

export function uploadDataset(sessionId: string, file: File): Promise<DatasetProfile> {
  const form = new FormData()
  form.append('file', file)
  return sendRequest<DatasetProfile>(`/sessions/${sessionId}/datasets`, {
    method: 'POST',
    body: form,
  })
}

export function getDataset(sessionId: string, datasetId: string): Promise<DatasetProfile> {
  return sendRequest<DatasetProfile>(`/sessions/${sessionId}/datasets/${datasetId}`)
}

export function createQuery(
  sessionId: string,
  datasetId: string,
  question: string,
): Promise<QueryCreated> {
  return sendRequest<QueryCreated>(`/sessions/${sessionId}/queries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, question }),
  })
}

export function getQuery(queryId: string): Promise<QueryDetail> {
  return sendRequest<QueryDetail>(`/queries/${queryId}`)
}

export function getSessionQueries(sessionId: string): Promise<QueryHistoryItem[]> {
  return sendRequest<QueryHistoryItem[]>(`/sessions/${sessionId}/queries`)
}
