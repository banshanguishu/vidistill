import { cancelJob } from './api'
import { SubmitForm } from './components/SubmitForm'
import { MyJobs } from './components/MyJobs'
import { FeedbackModal } from './components/FeedbackModal'
import { useMyJobs } from './hooks/useMyJobs'

export default function App() {
  const my = useMyJobs()
  return (
    <div className="min-h-screen bg-gray-50 text-gray-800">
      <div className="mx-auto max-w-3xl px-6 py-10">
        <header className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight">vidistill</h1>
          <p className="mt-1 text-gray-500">粘贴视频链接 → AI 总结 → 下载</p>
          <p className="mt-1 flex items-center gap-1 text-sm text-gray-400">
            <span>使用中遇到问题或想提建议？</span>
            <FeedbackModal />
          </p>
        </header>

        <SubmitForm onJobCreated={my.poke} />

        <div className="mt-6">
          <MyJobs
            jobs={my.jobs}
            activeCount={my.activeCount}
            queueFull={my.queueFull}
            onCancel={async (id) => { await cancelJob(id); my.refresh() }}
          />
        </div>
      </div>
    </div>
  )
}
