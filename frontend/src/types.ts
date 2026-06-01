export type Style = 'short' | 'chapters'

export type JobStatus =
  | 'queued' | 'pending' | 'fetching' | 'transcribing'
  | 'summarizing' | 'rendering' | 'done' | 'failed' | 'cancelled'

export type Format = 'md' | 'html' | 'pdf'

export interface CreateJobResponse {
  job_id: string
  queue_position: number
}

export interface JobStatusResponse {
  job_id: string
  status: JobStatus
  progress: number
  queue_position: number | null
  error: string | null
  video_title: string
  available_formats: Format[]
}

export interface MyJob {
  job_id: string
  video_title: string
  status: JobStatus
  progress: number
  queue_position: number | null
  created_at: string
  available_formats: Format[]
}

export interface MyJobsResponse {
  jobs: MyJob[]
  system: { active_count: number; active_max: number; queue_full: boolean }
}
