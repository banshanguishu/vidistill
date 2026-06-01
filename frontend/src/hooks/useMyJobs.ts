import { useCallback, useEffect, useRef, useState } from 'react'
import type { MyJob } from '../types'
import { getMyJobs } from '../api'

const TERMINAL = ['done', 'failed', 'cancelled']
const isTerminal = (s: string) => TERMINAL.includes(s)

export function useMyJobs() {
  const [jobs, setJobs] = useState<MyJob[]>([])
  const [activeCount, setActiveCount] = useState(0)
  const [queueFull, setQueueFull] = useState(false)
  const timerRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await getMyJobs()
      setJobs(data.jobs || [])
      setActiveCount(data.system.active_count)
      setQueueFull(data.system.queue_full)
      const hasActive = data.system.active_count > 0
      const hasNonTerminal = (data.jobs || []).some((j) => !isTerminal(j.status))
      if (!hasActive && !hasNonTerminal && timerRef.current) {
        clearInterval(timerRef.current); timerRef.current = null
      }
    } catch {
      // 瞬时错误，忽略
    }
  }, [])

  const ensurePolling = useCallback(() => {
    if (!timerRef.current) timerRef.current = window.setInterval(refresh, 3000)
  }, [refresh])

  const poke = useCallback(() => { refresh(); ensurePolling() }, [refresh, ensurePolling])

  useEffect(() => {
    refresh(); ensurePolling()
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [refresh, ensurePolling])

  return { jobs, activeCount, queueFull, refresh, poke }
}
