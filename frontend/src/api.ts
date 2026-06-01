import type {
  CreateJobResponse, JobStatusResponse, MyJobsResponse, Style,
} from './types'

async function parseError(resp: Response): Promise<string> {
  try {
    const data = await resp.json()
    return data.detail || `错误 ${resp.status}`
  } catch {
    return `错误 ${resp.status}`
  }
}

export async function createJob(url: string, style: Style): Promise<CreateJobResponse> {
  const resp = await fetch('/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, style }),
  })
  if (!resp.ok) throw new Error(await parseError(resp))
  return resp.json()
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  const resp = await fetch(`/jobs/${jobId}`)
  if (!resp.ok) throw new Error(await parseError(resp))
  return resp.json()
}

export async function cancelJob(jobId: string): Promise<void> {
  await fetch(`/jobs/${jobId}`, { method: 'DELETE' })
}

export async function getMyJobs(): Promise<MyJobsResponse> {
  const resp = await fetch('/my/jobs')
  if (!resp.ok) throw new Error(await parseError(resp))
  return resp.json()
}

export async function sendFeedback(content: string, contact: string | null): Promise<void> {
  const resp = await fetch('/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, contact }),
  })
  if (!resp.ok) throw new Error(await parseError(resp))
}

export function downloadUrl(jobId: string, fmt: string): string {
  return `/jobs/${jobId}/download/${fmt}`
}
