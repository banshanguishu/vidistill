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
  ['short', '短摘要', '几句话讲清核心内容，再列几条要点。适合快速判断这视频值不值得看。'],
  ['chapters', '章节笔记', '按视频章节拆分，每章一段小结加几条要点，并标注对应时间点。适合反复查阅。'],
] as const

const DOWNLOAD_BTN =
  'flex-1 min-w-[140px] rounded-xl bg-emerald-600 px-4 py-2.5 text-center text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700'

/** 仅校验“是不是一个合法的 http(s) URL”。挡不了“格式对但不是视频”——那由后端兜底。 */
function isValidHttpUrl(value: string): boolean {
  let parsed: URL
  try {
    parsed = new URL(value.trim())
  } catch {
    return false
  }
  return parsed.protocol === 'http:' || parsed.protocol === 'https:'
}

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
    if (!isValidHttpUrl(url)) return  // 兜底：按钮已禁用，这里防回车等绕过
    setPhase('submitting'); setErrorMessage('')
    try {
      const data = await createJob(url.trim(), style)
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

  const urlValid = isValidHttpUrl(url)
  const showUrlError = url.trim() !== '' && !urlValid

  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white p-6 shadow-xl shadow-slate-300/30 sm:p-7">
      {(phase === 'idle' || phase === 'submitting' || phase === 'error_input') && (
        <div>
          <label htmlFor="url" className="mb-1.5 block text-sm font-semibold text-slate-700">视频链接</label>
          <div className="relative">
            <input
              id="url" type="url" value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder="粘贴视频链接"
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 pr-10 text-slate-800 placeholder:text-slate-400 transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            />
            {url && (
              <button
                type="button" onClick={() => setUrl('')} aria-label="清空"
                className="absolute right-3 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full bg-slate-300 text-xs text-white transition hover:bg-slate-400"
              >
                ✕
              </button>
            )}
          </div>
          <p className="mt-1.5 text-sm text-slate-400">支持 YouTube、Bilibili 等主流视频网站。视频时长不超过 30 分钟。</p>
          {showUrlError && (
            <p className="mt-1.5 text-sm text-rose-600">请输入有效的视频链接（需以 http:// 或 https:// 开头）</p>
          )}

          <label className="mb-2 mt-5 block text-sm font-semibold text-slate-700">总结形态</label>
          <div className="flex flex-wrap gap-3">
            {STYLE_OPTIONS.map(([val, title, desc]) => (
              <label key={val}
                className={`relative flex-1 min-w-[240px] cursor-pointer rounded-xl border p-4 transition ${style === val ? 'border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-500/30' : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'}`}>
                <input type="radio" name="style" value={val} checked={style === val} onChange={() => setStyle(val)} className="hidden" />
                {style === val && (
                  <span className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500 text-[11px] text-white">✓</span>
                )}
                <strong className="block text-slate-800">{title}</strong>
                <span className="mt-1 block text-sm text-slate-500">{desc}</span>
              </label>
            ))}
          </div>

          <button onClick={submit} disabled={phase === 'submitting' || !urlValid}
            className="btn-gradient mt-6 w-full rounded-xl py-3 font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:shadow-indigo-500/40 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none">
            {phase === 'submitting' ? '提交中...' : '开始生成'}
          </button>
          {phase === 'error_input' && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-700">{errorMessage}</div>
          )}
        </div>
      )}

      {phase === 'polling' && (
        <div className="py-2">
          <div className="font-semibold text-slate-800">{videoTitle || '处理中'}</div>
          <div className="mt-2 flex items-center gap-2 text-sm text-slate-500">
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-500" />
            <span>{statusLabel()}</span>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div className="progress-fill h-full rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-1.5 text-right text-sm font-medium tabular-nums text-slate-400">{progress}%</div>
        </div>
      )}

      {phase === 'ready' && jobId && (
        <div>
          <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-700">
            <span className="text-lg">✓</span><span className="font-semibold">总结完成！</span>
          </div>
          <div className="mt-3 font-semibold text-slate-800">{videoTitle}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <a className={DOWNLOAD_BTN} href={downloadUrl(jobId, 'md')} download>下载 Markdown</a>
            <a className={DOWNLOAD_BTN} href={downloadUrl(jobId, 'html')} download>下载 HTML</a>
            {availableFormats.includes('pdf') ? (
              <a className={DOWNLOAD_BTN} href={downloadUrl(jobId, 'pdf')} download>下载 PDF</a>
            ) : (
              <button disabled title="PDF 需在服务器环境（含 GTK/字体库）生成；本地 Windows 环境无法生成。Docker 部署后可用。"
                className="flex-1 min-w-[140px] cursor-not-allowed rounded-xl bg-slate-100 px-4 py-2.5 text-center text-sm font-semibold text-slate-400">下载 PDF（不可用）</button>
            )}
          </div>
          <button onClick={reset} className="mt-4 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50">再来一个</button>
        </div>
      )}

      {phase === 'error_processing' && (
        <div>
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700">{errorMessage}</div>
          <div className="mt-4 flex gap-2">
            <button onClick={() => { setErrorMessage(''); submit() }} className="rounded-xl bg-slate-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800">重试</button>
            <button onClick={reset} className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50">换一个视频</button>
          </div>
        </div>
      )}
    </div>
  )
}
