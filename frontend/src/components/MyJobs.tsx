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
    case 'queued': return 'bg-blue-100 text-blue-700'
    case 'done': return 'bg-green-100 text-green-700'
    case 'failed': return 'bg-red-100 text-red-700'
    case 'cancelled': return 'bg-gray-100 text-gray-500'
    default: return 'bg-orange-100 text-orange-700'
  }
}

interface Props {
  jobs: MyJob[]
  activeCount: number
  queueFull: boolean
  onCancel: (jobId: string) => void
}

export function MyJobs({ jobs, activeCount, queueFull, onCancel }: Props) {
  return (
    <div className="flex max-h-[500px] flex-col overflow-hidden rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">我的任务（最近 7 天）</h2>

      {queueFull && (
        <div className="mt-2 self-start rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-700">⚠ 当前队列已满（10 / 10），请稍后再提交</div>
      )}
      {!queueFull && activeCount > 0 && (
        <div className="mt-2 self-start rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm text-blue-700">✓ 当前队列：{activeCount} / 10</div>
      )}

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
        {jobs.length > 0 ? (
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="border-b-2 border-gray-200 py-2 pr-2">标题</th>
                <th className="w-[120px] border-b-2 border-gray-200 py-2 pr-2">状态</th>
                <th className="w-[200px] border-b-2 border-gray-200 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id} className="hover:bg-gray-50">
                  <td className="break-words border-b border-gray-100 py-3 pr-2">{j.video_title || j.job_id}</td>
                  <td className="whitespace-nowrap border-b border-gray-100 py-3 pr-2">
                    <span title={j.status === 'failed' ? '处理失败' : ''}
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${badgeClass(j.status)}`}>
                      {!isTerminal(j.status) && (
                        <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-[1.5px] border-current border-t-transparent opacity-70" />
                      )}
                      {statusLabel(j)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap border-b border-gray-100 py-3">
                    {j.status === 'queued' && (
                      <button onClick={() => onCancel(j.job_id)}
                        className="rounded-md border border-red-500 px-3 py-1.5 text-xs font-medium text-red-500 transition hover:bg-red-500 hover:text-white">取消</button>
                    )}
                    {j.status === 'done' && (
                      <span className="flex flex-wrap gap-1">
                        <a href={downloadUrl(j.job_id, 'md')} download className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700">MD</a>
                        <a href={downloadUrl(j.job_id, 'html')} download className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700">HTML</a>
                        {j.available_formats.includes('pdf') && (
                          <a href={downloadUrl(j.job_id, 'pdf')} download className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700">PDF</a>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="mt-2 text-sm text-gray-500">暂无任务。如果之前提交过却看不到，请检查浏览器是否启用 Cookie。</div>
        )}
      </div>
    </div>
  )
}
