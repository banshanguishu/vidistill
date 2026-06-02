import * as Dialog from '@radix-ui/react-dialog'

// 教程视频地址（OSS 公共读）。换视频只改这一行即可。
const TUTORIAL_VIDEO_URL =
  'https://dbcproduct.oss-cn-shanghai.aliyuncs.com/testweb/video/VidistillUsage.mp4'

export function TutorialModal() {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-medium text-indigo-600 shadow-sm transition hover:border-indigo-200 hover:bg-indigo-50">
          📺 使用教程
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm" />
        <Dialog.Content className="dialog-content fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-5 shadow-2xl ring-1 ring-slate-200">
          <div className="mb-3 flex items-center justify-between">
            <Dialog.Title className="text-lg font-bold text-slate-800">使用教程</Dialog.Title>
            <Dialog.Close asChild>
              <button aria-label="关闭"
                className="flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-600">
                ✕
              </button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">vidistill 使用教程视频</Dialog.Description>
          {/* 关闭弹窗时 Radix 会卸载该节点，video 随之停止播放，无需手动暂停 */}
          <video
            src={TUTORIAL_VIDEO_URL}
            controls
            autoPlay
            playsInline
            className="max-h-[70vh] w-full rounded-xl bg-black"
          >
            你的浏览器不支持视频播放，
            <a href={TUTORIAL_VIDEO_URL} target="_blank" rel="noreferrer" className="text-indigo-600 underline">
              点此打开视频
            </a>
            。
          </video>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
