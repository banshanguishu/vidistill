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
        <button className="font-medium text-blue-600 hover:underline">💬 点此反馈</button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[90vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          {!submitted ? (
            <>
              <Dialog.Title className="mb-3 text-lg font-semibold">反馈问题或建议</Dialog.Title>
              <Dialog.Description className="sr-only">提交你遇到的问题或建议</Dialog.Description>
              <label className="mb-1 mt-3 block text-sm font-medium">问题描述 <span className="text-red-600">*</span></label>
              <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="请描述你遇到的问题或想提的建议..."
                className="min-h-[120px] w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
              <label className="mb-1 mt-3 block text-sm font-medium">联系方式（选填）</label>
              <input type="text" value={contact} onChange={(e) => setContact(e.target.value)} placeholder="邮箱或微信号，方便我回复你"
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
              {error && <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
              <div className="mt-5 flex justify-end gap-3">
                <Dialog.Close asChild>
                  <button className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">取消</button>
                </Dialog.Close>
                <button onClick={submit} disabled={!content.trim() || submitting}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-400">
                  {submitting ? '提交中...' : '提交'}
                </button>
              </div>
            </>
          ) : (
            <div className="py-8 text-center text-lg font-medium text-green-700">✓ 已收到反馈，感谢！</div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
