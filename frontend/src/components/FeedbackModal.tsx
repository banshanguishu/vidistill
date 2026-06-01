import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { sendFeedback } from '../api'

export function FeedbackModal() {
  const [open, setOpen] = useState(false)
  const [content, setContent] = useState('')
  const [contact, setContact] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  const onOpenChange = (o: boolean) => {
    setOpen(o)
    if (o) { setContent(''); setContact(''); setSubmitted(false); setError('') }
  }

  const submit = async () => {
    if (!content.trim()) return
    setSubmitting(true); setError('')
    try {
      await sendFeedback(content.trim(), contact.trim() || null)
      setSubmitted(true)
      setTimeout(() => setOpen(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>
        <button className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-medium text-indigo-600 shadow-sm transition hover:border-indigo-200 hover:bg-indigo-50">💬 点此反馈</button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm" />
        <Dialog.Content className="dialog-content fixed left-1/2 top-1/2 z-50 w-[90vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-6 shadow-2xl ring-1 ring-slate-200">
          {!submitted ? (
            <>
              <Dialog.Title className="mb-1 text-lg font-bold text-slate-800">反馈问题或建议</Dialog.Title>
              <Dialog.Description className="sr-only">提交你遇到的问题或建议</Dialog.Description>
              <label className="mb-1.5 mt-4 block text-sm font-semibold text-slate-700">问题描述 <span className="text-rose-500">*</span></label>
              <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="请描述你遇到的问题或想提的建议..."
                className="min-h-[120px] w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-slate-800 placeholder:text-slate-400 transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/40" />
              <label className="mb-1.5 mt-4 block text-sm font-semibold text-slate-700">联系方式（选填）</label>
              <input type="text" value={contact} onChange={(e) => setContact(e.target.value)} placeholder="邮箱或微信号，方便我回复你"
                className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-slate-800 placeholder:text-slate-400 transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/40" />
              {error && <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-700">{error}</div>}
              <div className="mt-5 flex justify-end gap-3">
                <Dialog.Close asChild>
                  <button className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50">取消</button>
                </Dialog.Close>
                <button onClick={submit} disabled={!content.trim() || submitting}
                  className="btn-gradient rounded-xl px-5 py-2 text-sm font-semibold text-white shadow-md shadow-indigo-500/30 transition disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none">
                  {submitting ? '提交中...' : '提交'}
                </button>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-3 py-10 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-2xl text-emerald-600">✓</div>
              <p className="text-lg font-semibold text-emerald-700">已收到反馈，感谢！</p>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
