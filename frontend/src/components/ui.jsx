/**
 * Shared UI atoms — CoWorkX dark design system.
 * All colors come from index.css token classes (no hardcoded hex in JSX).
 */

import { formatDistanceToNow } from 'date-fns'

/** Pulsing live-bar + section title. */
export function SectionHeader({ title, live = false, right = null }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div className={`live-bar${live ? ' live' : ''}`} />
      <div className="between">
        <span className="label">{title}</span>
        {right}
      </div>
    </div>
  )
}

/** 4-bar signal indicator (replaces status dots). */
export function SignalBars({ status }) {
  return (
    <span className={`signal ${status}`}>
      <i /><i /><i /><i />
    </span>
  )
}

/** Status tag pill. */
export function StatusTag({ status }) {
  return <span className={`tag ${status}`}>{status}</span>
}

/** Action pill (light bg for contrast on dark cards). */
export function ActionPill({ action }) {
  const known = ['navigate', 'click', 'type', 'extract',
                 'browser_navigate', 'browser_click', 'browser_type',
                 'browser_extract', 'browser_screenshot', 'task_complete']
  const cls = known.includes(action) ? action : 'default'
  return <span className={`pill ${cls}`}>{String(action).replace('browser_', '')}</span>
}

/** Relative timestamp. */
export function RelTime({ value }) {
  if (!value) return <span className="mono ter" style={{ fontSize: '0.625rem' }}>—</span>
  let d
  try { d = formatDistanceToNow(new Date(value), { addSuffix: true }) }
  catch { d = '' }
  return <span className="mono ter" style={{ fontSize: '0.625rem' }}>{d}</span>
}
