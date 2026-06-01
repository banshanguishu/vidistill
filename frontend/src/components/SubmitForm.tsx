import { useEffect, useRef, useState } from 'react'
import type { Format, JobStatus, Style } from '../types'
import { createJob, downloadUrl, getJob } from '../api'

type Phase = 'idle' | 'submitting' | 'polling' | 'ready' | 'error_input' | 'error_processing'

const STATUS_LABELS: Record<string, (pos: number | null) => string> = {
  queued: (pos) => (pos ? `正在排队（第 ${pos} 位）...` : '正在排队...'),
  pending: () => '即将开始...',
  fetching: () => '正在抓取视频信息...',
  transcribing: () => '正在转写音频...',
  summarizing: () => '正在生成摘要...',
  rendering: () => '正在渲染输出...',
}

const STYLE_OPTIONS = [
  ['short', '短摘要', '3-5 句核心要点 + 5-10 条 bullet。适合快速判断"这视频值不值得看"。'],
  ['chapters', '章节笔记', '按视频章节切分，每章一段总结 + bullet，带时间戳。适合反复查阅。'],
] as const

export function SubmitForm({ onJobCreated }: { onJobCreated?: () => void }) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [url, setUrl] = useState('')
  const [style, setStyle] = useState<Style>('chapters')
  const [jobId, setJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState<JobStatus>('pending')
  const [queuePosition, setQueuePosition] = useState<number | null>(null)
  const [videoTitle, setVideoTitle] = useState('')
  const [availableFormats, setAvailableFormats] = useState<Format[]>([])
  const [errorMessage, setErrorMessage] = useState('')
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (phase === 'submitting' || phase === 'polling') {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [phase])

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  const stopPolling = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
  }

  const reset = () => {
    stopPolling()
    setPhase('idle'); setUrl(''); setJobId(null); setProgress(0)
    setErrorMessage(''); setVideoTitle(''); setAvailableFormats([])
  }

  const poll = async (id: string) => {
    try {
      const data = await getJob(id)
      setStatus(data.status)
      setProgress(data.progress)
      setVideoTitle(data.video_title || '')
      setAvailableFormats(data.available_formats || [])
      setQueuePosition(data.queue_position)
      if (data.status === 'done') { stopPolling(); setPhase('ready') }
      else if (data.status === 'failed') { stopPolling(); setErrorMessage(data.error || '处理失败'); setPhase('error_processing') }
      else if (data.status === 'cancelled') { stopPolling(); reset() }
    } catch {
      // 瞬时网络错误，继续轮询
    }
  }

  const startPolling = (id: string) => {
    timerRef.current = window.setInterval(() => poll(id), 2000)
    poll(id)
  }

  const submit = async () => {
    setPhase('submitting'); setErrorMessage('')
    try {
      const data = await createJob(url, style)
      setJobId(data.job_id)
      setQueuePosition(data.queue_position)
      setPhase('polling')
      onJobCreated?.()
      startPolling(data.job_id)
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : '提交失败')
      setPhase('error_input')
    }
  }

  const statusLabel = () => (STATUS_LABELS[status] ? STATUS_LABELS[status](queuePosition) : status)

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      {(phase === 'idle' || phase === 'submitting' || phase === 'error_input') && (
        <div>
          <label htmlFor="url" className="block font-semibold mb-1">视频链接</label>
          <input
            id="url" type="url" value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=... 或 https://www.bilibili.com/video/..."
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-sm text-gray-500 mt-1">支持 YouTube、Bilibili 等 yt-dlp 兼容平台。视频时长不超过 30 分钟。</p>

          <label className="block font-semibold mt-4 mb-2">总结形态</label>
          <div className="flex flex-wrap gap-3">
            {STYLE_OPTIONS.map(([val, title, desc]) => (
              <label key={val}
                className={`flex-1 min-w-[240px] cursor-pointer rounded-md border p-3 transition ${style === val ? 'border-blue-500 bg-blue-50' : 'border-gray-300'}`}>
                <input type="radio" name="style" value={val} checked={style === val} onChange={() => setStyle(val)} className="hidden" />
                <strong className="block">{title}</strong>
                <span className="text-sm text-gray-600">{desc}</span>
              </label>
            ))}
          </div>

          <button onClick={submit} disabled={phase === 'submitting' || !url}
            className="mt-6 w-full rounded-md bg-blue-600 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:bg-gray-400">
            {phase === 'submitting' ? '提交中...' : '开始生成'}
          </button>
          {phase === 'error_input' && (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-700">{errorMessage}</div>
          )}
        </div>
      )}

      {phase === 'polling' && (
        <div>
          <div className="font-semibold">{videoTitle || '处理中'}</div>
          <div className="mt-2 flex items-center gap-2 text-sm text-gray-600">
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-200 border-t-blue-600" />
            <span>{statusLabel()}</span>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded bg-gray-200">
            <div className="h-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-1 text-sm text-gray-500">{progress}%</div>
        </div>
      )}

      {phase === 'ready' && jobId && (
        <div>
          <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-green-700">总结完成！</div>
          <div className="mt-2 font-semibold">{videoTitle}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <a className="flex-1 min-w-[140px] rounded-md bg-green-700 px-4 py-2 text-center font-semibold text-white hover:bg-green-800" href={downloadUrl(jobId, 'md')} download>下载 Markdown</a>
            <a className="flex-1 min-w-[140px] rounded-md bg-green-700 px-4 py-2 text-center font-semibold text-white hover:bg-green-800" href={downloadUrl(jobId, 'html')} download>下载 HTML</a>
            {availableFormats.includes('pdf') ? (
              <a className="flex-1 min-w-[140px] rounded-md bg-green-700 px-4 py-2 text-center font-semibold text-white hover:bg-green-800" href={downloadUrl(jobId, 'pdf')} download>下载 PDF</a>
            ) : (
              <button disabled title="PDF 需在服务器环境（含 GTK/字体库）生成；本地 Windows 环境无法生成。Docker 部署后可用。"
                className="flex-1 min-w-[140px] cursor-not-allowed rounded-md bg-gray-300 px-4 py-2 text-center font-semibold text-gray-600">下载 PDF（不可用）</button>
            )}
          </div>
          <button onClick={reset} className="mt-4 rounded-md bg-gray-600 px-4 py-2 text-white hover:bg-gray-700">再来一个</button>
        </div>
      )}

      {phase === 'error_processing' && (
        <div>
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-700">{errorMessage}</div>
          <div className="mt-4 flex gap-2">
            <button onClick={() => { setErrorMessage(''); submit() }} className="rounded-md bg-gray-600 px-4 py-2 text-white hover:bg-gray-700">重试</button>
            <button onClick={reset} className="rounded-md bg-gray-600 px-4 py-2 text-white hover:bg-gray-700">换一个视频</button>
          </div>
        </div>
      )}
    </div>
  )
}
