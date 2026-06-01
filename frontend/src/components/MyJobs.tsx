import type { MyJob } from '../types'
import { downloadUrl } from '../api'

const TERMINAL = ['done', 'failed', 'cancelled']
const isTerminal = (s: string) => TERMINAL.includes(s)

function statusLabel(j: MyJob): string {
  switch (j.status) {
    case 'queued': return j.queue_position ? `排队中 #${j.queue_position}` : '排队中'
    case 'pending': return '即将开始'
    case 'fetching':
    case 'transcribing':
    case 'summarizing':
    case 'rendering': return `处理中 ${j.progress}%`
    case 'done': return '已完成'
    case 'failed': return '失败'
    case 'cancelled': return '已取消'
    default: return j.status
  }
}

function badgeClass(status: string): string {
  switch (status) {
    case 'queued': return 'bg-indigo-50 text-indigo-700 ring-indigo-600/20'
    case 'done': return 'bg-emerald-50 text-emerald-700 ring-emerald-600/20'
    case 'failed': return 'bg-rose-50 text-rose-700 ring-rose-600/20'
    case 'cancelled': return 'bg-slate-100 text-slate-500 ring-slate-500/20'
    default: return 'bg-amber-50 text-amber-700 ring-amber-600/20'
  }
}

const DL_BTN = 'rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700'

interface Props {
  jobs: MyJob[]
  activeCount: number
  queueFull: boolean
  onCancel: (jobId: string) => void
}

export function MyJobs({ jobs, activeCount, queueFull, onCancel }: Props) {
  return (
    <div className="flex max-h-[520px] flex-col overflow-hidden rounded-2xl border border-slate-200/70 bg-white p-6 shadow-xl shadow-slate-300/30 sm:p-7">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-slate-800">我的任务<span className="ml-1.5 text-sm font-normal text-slate-400">最近 7 天</span></h2>
        {queueFull ? (
          <span className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-medium text-rose-700">⚠ 队列已满 10 / 10</span>
        ) : activeCount > 0 ? (
          <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">运行中 {activeCount} / 10</span>
        ) : null}
      </div>

      <div className="thin-scroll mt-4 min-h-0 flex-1 overflow-y-auto">
        {jobs.length > 0 ? (
          <table className="w-full border-collapse">
            <thead className="sticky top-0 bg-white">
              <tr className="text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                <th className="border-b border-slate-200 py-2.5 pr-2">标题</th>
                <th className="w-[120px] border-b border-slate-200 py-2.5 pr-2">状态</th>
                <th className="w-[200px] border-b border-slate-200 py-2.5">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id} className="transition hover:bg-slate-50/70">
                  <td className="break-words border-b border-slate-100 py-3 pr-2 text-sm text-slate-700">{j.video_title || j.job_id}</td>
                  <td className="whitespace-nowrap border-b border-slate-100 py-3 pr-2">
                    <span title={j.status === 'failed' ? '处理失败' : ''}
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${badgeClass(j.status)}`}>
                      {!isTerminal(j.status) ? (
                        <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-[1.5px] border-current border-t-transparent opacity-70" />
                      ) : (
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-current opacity-70" />
                      )}
                      {statusLabel(j)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap border-b border-slate-100 py-3">
                    {j.status === 'queued' && (
                      <button onClick={() => onCancel(j.job_id)}
                        className="rounded-lg border border-rose-300 px-3 py-1.5 text-xs font-medium text-rose-600 transition hover:bg-rose-500 hover:text-white">取消</button>
                    )}
                    {j.status === 'done' && (
                      <span className="flex flex-wrap gap-1.5">
                        <a href={downloadUrl(j.job_id, 'md')} download className={DL_BTN}>MD</a>
                        <a href={downloadUrl(j.job_id, 'html')} download className={DL_BTN}>HTML</a>
                        {j.available_formats.includes('pdf') && (
                          <a href={downloadUrl(j.job_id, 'pdf')} download className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700">PDF</a>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-2xl">🗂️</div>
            <p className="text-sm text-slate-500">暂无任务。如果之前提交过却看不到，请检查浏览器是否启用 Cookie。</p>
          </div>
        )}
      </div>
    </div>
  )
}
