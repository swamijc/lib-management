import { useEffect, useRef, useState } from 'react'
import { useIsFetching, useIsMutating } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'

const SHOW_DELAY_MS = 350
const MIN_VISIBLE_MS = 280

export default function GlobalAsyncLoader() {
  const fetching = useIsFetching()
  const mutating = useIsMutating()
  const activeOps = fetching + mutating

  const [visible, setVisible] = useState(false)
  const visibleSince = useRef<number>(0)

  useEffect(() => {
    let timer: number | undefined

    if (activeOps > 0) {
      if (!visible) {
        timer = window.setTimeout(() => {
          visibleSince.current = Date.now()
          setVisible(true)
        }, SHOW_DELAY_MS)
      }
    } else if (visible) {
      const elapsed = Date.now() - visibleSince.current
      const wait = Math.max(0, MIN_VISIBLE_MS - elapsed)
      timer = window.setTimeout(() => setVisible(false), wait)
    }

    return () => {
      if (timer) window.clearTimeout(timer)
    }
  }, [activeOps, visible])

  return (
    <div className={`global-async-loader ${visible ? 'global-async-loader-visible' : ''}`} aria-live="polite" aria-busy={visible}>
      <div className="global-async-loader-bar" />
      <div className="global-async-loader-chip" role="status">
        <Loader2 size={14} className="animate-spin" />
        <span>{mutating > 0 ? 'Saving changes...' : 'Loading data...'}</span>
      </div>
    </div>
  )
}
