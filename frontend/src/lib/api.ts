// Same-origin API client. The app is served from the backend at /app/,
// so all URLs are relative and resolve against http://localhost:8001.

export interface ProfileColumn {
  name: string
  dtype: string
  missing: number
  min: number | null
  max: number | null
  mean: number | null
  distinct: number
}

export interface DatasetProfile {
  columns: ProfileColumn[]
}

export interface Dataset {
  dataset_id: string
  name: string
  row_count: number
  profile: DatasetProfile
}

export interface ApiErrorBody {
  detail?: { message?: string } | string
  message?: string
}

export async function uploadDataset(file: File): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)

  let res: Response
  try {
    res = await fetch('/datasets', { method: 'POST', body: form })
  } catch {
    throw new Error('Network error — is the server running?')
  }

  let body: { data?: Dataset } & ApiErrorBody = {}
  try {
    body = await res.json()
  } catch {
    // fall through to status-based messaging
  }

  if (!res.ok) {
    throw new Error(extractError(body, res.status))
  }
  if (!body.data) {
    throw new Error('Upload succeeded but the server returned no profile.')
  }
  return body.data
}

function extractError(body: ApiErrorBody, status: number): string {
  if (typeof body.detail === 'object' && body.detail?.message) return body.detail.message
  if (typeof body.detail === 'string') return body.detail
  if (body.message) return body.message
  if (status === 400) return 'Unsupported file or it could not be parsed. Upload a valid CSV.'
  if (status === 413) return 'That file is too large (limit ~100MB).'
  return `Request failed (${status}).`
}

// ---- SSE over POST ----
// EventSource only supports GET, and this endpoint is POST, so we read the
// ReadableStream manually and split the buffer on the SSE record separator "\n\n".

export type StreamEvent =
  | { event: 'step'; data: { stage: string } }
  | { event: 'code'; data: { code: string } }
  | { event: 'token'; data: { text: string } }
  | { event: 'result'; data: { kind: string; payload: unknown } }
  | { event: 'done'; data: { run_id: string; status: string; tokens?: unknown; cost_usd?: number } }
  | { event: 'error'; data: { message: string } }
  | { event: string; data: unknown }

export interface QueryRequest {
  dataset_id: string
  question: string
}

export async function streamQuery(
  req: QueryRequest,
  onEvent: (ev: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch('/sessions/new/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(req),
      signal,
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    throw new Error('Network error — is the server running?')
  }

  if (!res.ok || !res.body) {
    let body: ApiErrorBody = {}
    try {
      body = await res.json()
    } catch {
      /* ignore */
    }
    throw new Error(extractError(body, res.status))
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep: number
    // Records are separated by a blank line (\n\n).
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const parsed = parseRecord(raw)
      if (parsed) onEvent(parsed)
    }
  }

  // flush any trailing record without a final blank line
  const tail = parseRecord(buffer)
  if (tail) onEvent(tail)
}

function parseRecord(raw: string): StreamEvent | null {
  const lines = raw.split('\n')
  let event = 'message'
  const dataParts: string[] = []
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataParts.push(line.slice(5).trim())
  }
  if (dataParts.length === 0) return null
  const dataStr = dataParts.join('\n')
  try {
    return { event, data: JSON.parse(dataStr) } as StreamEvent
  } catch {
    return null
  }
}
