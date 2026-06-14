/**
 * CoWorkX Worker Node — control panel for the friend's machine.
 * Talks to daemon_api.py on port 5175. No terminal needed.
 */

import { useEffect, useRef, useState } from 'react'
import {
  Server, Play, Square, Copy, ChevronDown, ChevronRight, Cpu, MemoryStick,
} from 'lucide-react'

const API = 'http://localhost:5175'

export default function App() {
  const [status, setStatus] = useState({ running: false, connected: false, uptime: 0, heartbeat_count: 0, machine_id: null })
  const [specs, setSpecs] = useState(null)
  const [tasks, setTasks] = useState([])
  const [busy, setBusy] = useState(false)
  const [apiUp, setApiUp] = useState(true)

  useEffect(() => {
    poll()
    const id = setInterval(poll, 2000)
    fetchSpecs()
    return () => clearInterval(id)
  }, [])

  async function poll() {
    try {
      const [st, tk] = await Promise.all([
        fetch(`${API}/status`).then(r => r.json()),
        fetch(`${API}/tasks`).then(r => r.json()).catch(() => []),
      ])
      setStatus(st); setTasks(Array.isArray(tk) ? tk : []); setApiUp(true)
    } catch { setApiUp(false) }
  }
  async function fetchSpecs() {
    try { setSpecs(await fetch(`${API}/specs`).then(r => r.json())) } catch {}
  }

  async function start() { setBusy(true); try { await fetch(`${API}/start`, { method: 'POST' }) } finally { setBusy(false); poll() } }
  async function stop()  { setBusy(true); try { await fetch(`${API}/stop`,  { method: 'POST' }) } finally { setBusy(false); poll() } }

  const conn = !apiUp ? 'offline' : (status.connected ? 'connected' : (status.running ? 'connecting' : 'idle'))
  const connText = !apiUp ? 'Control API offline' : (status.connected ? 'Connected' : (status.running ? 'Connecting…' : 'Stopped'))
  const anyRunning = tasks.some(t => t.status === 'running')

  return (
    <div>
      {/* HEADER */}
      <header style={s.header}>
        <div className="row" style={{ gap: 10 }}>
          <span style={{ fontWeight: 600, fontSize: '1rem' }}>CoWorkX</span>
          <span style={{ color: 'var(--border)' }}>|</span>
          <span className="muted" style={{ fontSize: '0.875rem' }}>Worker Node</span>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <span className={`dot ${conn}`} />
          <span className="label">{connText}</span>
        </div>
      </header>

      <div style={s.page}>
        {/* SECTION 1 — CONTROL */}
        {!status.running ? (
          <div style={s.controlEmpty}>
            <Server size={48} color="var(--accent)" />
            <h2 style={{ fontSize: '1.5rem', marginTop: 16 }}>Worker Node Offline</h2>
            <p className="muted" style={{ fontSize: '0.875rem', maxWidth: 360, textAlign: 'center', marginTop: 8 }}>
              Start the daemon to connect this machine to the CoWorkX network and earn credits.
            </p>
            <button className="btn-primary btn-lg" style={{ width: 200, marginTop: 24 }} disabled={busy || !apiUp} onClick={start}>
              <Play size={20} /> Start Worker
            </button>
            {!apiUp && <p style={{ color: 'var(--danger)', fontSize: '0.8125rem', marginTop: 12 }}>
              Control API not reachable — run <span className="mono">python daemon_api.py</span>
            </p>}
          </div>
        ) : (
          <div>
            <div style={s.statRow}>
              <Stat label="Uptime" value={fmtUptime(status.uptime)} />
              <Stat label="Heartbeats" value={status.heartbeat_count} />
              <Stat label="Tasks Done" value={tasks.length} />
            </div>
            <button className="btn-danger" style={{ marginTop: 16 }} disabled={busy} onClick={stop}>
              <Square size={16} /> Stop Worker
            </button>
          </div>
        )}

        {/* SECTION 2 — THIS MACHINE */}
        <Section title="This Machine">
          <div style={s.twoCol}>
            <div>
              <SpecRow label="GPU" value={specs?.gpu} />
              <SpecRow label="CPU" value={specs?.cpu} />
              <SpecRow label="RAM" value={specs ? `${specs.ram_total_gb} GB (${specs.ram_free_gb} GB free)` : '…'} />
              <SpecRow label="OS" value={specs?.os} />
              <SpecRow label="Storage" value={specs ? `${specs.disk_free_gb} GB free` : '…'} />
              <div style={{ marginTop: 12 }}>
                <div className="label" style={{ marginBottom: 4 }}>AI Model</div>
                <span className="pill">{specs?.model || '…'}</span>
                <p className="faint" style={{ fontSize: '0.6875rem', marginTop: 6 }}>Running locally • No internet needed</p>
              </div>
            </div>
            <div>
              <CopyRow label="Coordinator URL" value={specs?.coordinator_url} />
              <CopyRow label="Machine ID" value={status.machine_id || '—'} />
            </div>
          </div>
        </Section>

        {/* SECTION 3 — ACTIVE TASKS */}
        <Section title="Active Tasks" live={anyRunning}>
          {tasks.length === 0 ? (
            <p className="faint" style={{ fontSize: '0.8125rem' }}>No tasks running. Waiting for work…</p>
          ) : (
            tasks.map(t => (
              <div key={t.task_id} className="row" style={{ gap: 10, padding: '8px 0' }}>
                <span className={`dot ${t.status === 'running' ? 'running' : 'idle'}`} />
                <span className="mono" style={{ fontSize: '0.75rem' }}>{t.task_id.slice(0, 12)}…</span>
                <span className="label">{t.status}</span>
              </div>
            ))
          )}
        </Section>

        {/* SECTION 4 — LIVE LOG */}
        <LiveLog />
      </div>
    </div>
  )
}

/* ── Live log (SSE, collapsible) ───────────────────────────────────────── */
function LiveLog() {
  const [open, setOpen] = useState(true)
  const [lines, setLines] = useState([])
  const boxRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const es = new EventSource(`${API}/stream/log`)
    es.onmessage = (e) => setLines(prev => [...prev.slice(-400), e.data])
    es.onerror = () => {}
    return () => es.close()
  }, [open])

  useEffect(() => { if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight }, [lines])

  function color(line) {
    if (line.includes('ERROR') || line.includes('❌')) return '#DC2626'
    if (line.includes('NEW TASK') || line.includes('🧠')) return '#1D6AE5'
    if (line.includes('✅') || line.includes('Registered')) return '#16A34A'
    return '#A8A5A2'
  }

  return (
    <div style={{ marginTop: 32 }}>
      <button onClick={() => setOpen(o => !o)} style={s.logToggle} className="label">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Daemon Log
      </button>
      {open && (
        <div ref={boxRef} style={s.logBox}>
          {lines.length === 0 && <span style={{ color: '#6B7280' }}>Waiting for daemon output…</span>}
          {lines.map((l, i) => (
            <div key={i} style={{ color: color(l), animation: 'fadeIn 0.2s' }}>{l}</div>
          ))}
        </div>
      )}
      <style>{`@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }`}</style>
    </div>
  )
}

/* ── Small components ──────────────────────────────────────────────────── */
function Section({ title, live, children }) {
  return (
    <div style={{ marginTop: 32 }}>
      <div className={`accent-line${live ? ' live' : ''}`} />
      <div className="label" style={{ marginBottom: 16 }}>{title}</div>
      <div className="card" style={{ padding: 24 }}>{children}</div>
    </div>
  )
}
function Stat({ label, value }) {
  return (
    <div className="card stat-card" style={{ padding: 24, flex: 1 }}>
      <div className="grad-text" style={{ fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em' }}>{value}</div>
      <div className="label" style={{ marginTop: 4 }}>{label}</div>
    </div>
  )
}
function SpecRow({ label, value }) {
  return (
    <div className="row" style={{ gap: 12, marginBottom: 8 }}>
      <span className="label" style={{ width: 64 }}>{label}</span>
      <span style={{ fontSize: '0.875rem' }}>{value || '…'}</span>
    </div>
  )
}
function CopyRow({ label, value }) {
  const [copied, setCopied] = useState(false)
  function copy() { navigator.clipboard?.writeText(value || ''); setCopied(true); setTimeout(() => setCopied(false), 1200) }
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="label" style={{ marginBottom: 4 }}>{label}</div>
      <button onClick={copy} style={s.copyRow} title="Copy">
        <span className="mono" style={{ fontSize: '0.75rem', overflow: 'hidden', textOverflow: 'ellipsis' }}>{value || '—'}</span>
        <Copy size={14} color={copied ? 'var(--success)' : 'var(--text-faint)'} />
      </button>
    </div>
  )
}

const fmtUptime = (s) => {
  if (!s) return '0m'
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`
}

const s = {
  header: { height: 52, background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' },
  page:   { maxWidth: 880, margin: '0 auto', padding: 32 },
  controlEmpty: { display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center',
                  padding: '48px 24px', border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-surface)' },
  statRow: { display: 'flex', gap: 16 },
  twoCol:  { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32 },
  logToggle: { background: 'none', border: 'none', display: 'flex', alignItems: 'center', gap: 6, padding: 0, marginBottom: 12 },
  logBox:  { height: 240, overflowY: 'auto', background: 'var(--bg-void)', borderRadius: 'var(--radius-md)', padding: 16,
             fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', lineHeight: 1.7, border: '1px solid var(--border-subtle)' },
  copyRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, width: '100%',
             background: 'var(--bg-muted)', border: '1px solid var(--border)', borderRadius: 4, padding: '8px 10px' },
}
