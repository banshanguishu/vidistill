import { cancelJob } from './api'
import { SubmitForm } from './components/SubmitForm'
import { MyJobs } from './components/MyJobs'
import { FeedbackModal } from './components/FeedbackModal'
import { TutorialModal } from './components/TutorialModal'
import { useMyJobs } from './hooks/useMyJobs'

export default function App() {
  const my = useMyJobs()
  return (
    <div className="app-bg min-h-screen text-slate-800">
      <div className="mx-auto max-w-3xl px-5 py-12 sm:px-6">
        <header className="mb-8">
          <div className="flex items-center gap-3">
            <div className="logo-mark flex h-11 w-11 items-center justify-center rounded-2xl text-lg text-white shadow-lg shadow-indigo-500/30">
              ▶
            </div>
            <div>
              <h1 className="text-gradient text-2xl font-extrabold leading-tight tracking-tight">vidistill</h1>
              <p className="text-sm text-slate-500">粘贴视频链接 → AI 总结 → 下载</p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <TutorialModal />
            <FeedbackModal />
          </div>
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

        <footer className="mt-10 text-center text-xs text-slate-400">
          vidistill · 团队内部工具
        </footer>
      </div>
    </div>
  )
}
