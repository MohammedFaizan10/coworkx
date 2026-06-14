/**
 * Marketplace — filter chips + premium machine cards + task modal.
 * Dark premium design system. Fetch + submit + voice logic preserved.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mic, X, ArrowRight } from 'lucide-react'
import Navbar from '../components/Navbar'
import { SignalBars, StatusTag } from '../components/ui'

import { API } from '../config'
const STATUS_FILTERS = ['online', 'busy', 'offline']
const MODEL_FILTERS = ['gemma3:4b', 'gemma4', 'llava-phi3']

export default function Marketplace() {
  const navigate = useNavigate()
  const [machines, setMachines] = useState([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState(null)   // null = all
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    load(); const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  async function load() {
    try {
      const res = await fetch(`${API}/machines`)
      const data = await res.json()
      setMachines(Array.isArray(data) ? data : [])
    } catch (e) { console.error(e) } finally { setLoading(false) }
  }

  const filtered = useMemo(
    () => statusFilter ? machines.filter(m => m.status === statusFilter) : machines,
    [machines, statusFilter])

  return (
    <div>
      <Navbar />
      <div className="page">
        <div style={{ marginBottom: 8 }}>
          <div className="live-bar" />
          <h1 style={{ fontSize: '1.5rem' }}>Marketplace</h1>
          <p className="sec" style={{ fontSize: '0.875rem', marginTop: 4 }}>
            {filtered.length} node{filtered.length === 1 ? '' : 's'} on the network
          </p>
        </div>

        {/* FILTER CHIPS */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '20px 0 24px' }}>
          <button className={`chip${!statusFilter ? ' active' : ''}`} onClick={() => setStatusFilter(null)}>All</button>
          {STATUS_FILTERS.map(st => (
            <button key={st} className={`chip${statusFilter === st ? ' active' : ''}`}
              onClick={() => setStatusFilter(st)} style={{ textTransform: 'capitalize' }}>{st}</button>
          ))}
          <span style={{ flex: 1 }} />
          {MODEL_FILTERS.map(m => (
            <span key={m} className="model-pill" style={{ opacity: 0.7 }}>{m}</span>
          ))}
        </div>

        {loading && <p className="ter">Loading nodes…</p>}
        {!loading && filtered.length === 0 && (
          <div className="card" style={{ padding: 48, textAlign: 'center' }}>
            <p className="sec" style={{ marginBottom: 16 }}>No nodes match this filter.</p>
            <button className="btn" onClick={() => setStatusFilter(null)}>Show all</button>
          </div>
        )}

        <div style={s.grid}>
          {filtered.map((m, i) => (
            <MachineCard key={m.id} m={m} idx={i} onRun={() => setSelected(m)} />
          ))}
        </div>
      </div>

      {selected && <TaskModal machine={selected} onClose={() => setSelected(null)} navigate={navigate} />}
    </div>
  )
}

/* ── Machine card ──────────────────────────────────────────────────────── */
function MachineCard({ m, idx = 0, onRun }) {
  const online = m.status === 'online'
  const model = m.ai_model || (m.gpu_model ? 'gemma3:4b' : 'llava-phi3')
  const modelClass = model === 'gemma3:4b' ? 'violet' : (model === 'gemma4' ? 'accent' : '')
  const uptimePct = online ? 100 : (m.status === 'busy' ? 65 : 0)
  const nodeId = `node_${String(m.id).slice(0, 4)} · ${cityFrom(m)}`

  return (
    <div className={`card ${m.status}`} style={{ padding: 20, animationDelay: `${idx * 50}ms` }}>
      <div className="between" style={{ marginBottom: 16, alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: '0.875rem', letterSpacing: '-0.02em' }}>{m.display_name}</div>
          <div className="mono ter" style={{ fontSize: '0.6875rem', marginTop: 2 }}>{nodeId}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
          <StatusTag status={m.status} />
          <SignalBars status={m.status} />
        </div>
      </div>

      <div style={s.specGrid}>
        <Cell k="OS" v={(m.os || '—').toUpperCase()} />
        <Cell k="RAM" v={m.ram_gb ? `${m.ram_gb} GB` : '—'} />
        <Cell k="CPU" v={shorten(m.cpu_model)} />
        <Cell k="GPU" v={shorten(m.gpu_model) || '—'} />
      </div>

      <div style={{ margin: '14px 0' }}>
        <span className={`model-pill ${modelClass}`}>{model}</span>
      </div>

      <div className="between" style={{ marginBottom: 12 }}>
        <span className="mono ter" style={{ fontSize: '0.75rem' }}>
          {Number(m.price_per_hour || 0).toFixed(2)} CWX / task
        </span>
        <button onClick={online ? onRun : undefined}
          className={online ? 'btn-primary' : 'btn-muted'}
          style={{ height: 'auto', padding: '8px 18px', fontSize: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
          Run Task →
        </button>
      </div>

      <div className={`activity ${m.status === 'busy' ? 'busy' : ''}`}>
        <i style={{ width: `${uptimePct}%` }} />
      </div>
    </div>
  )
}

function Cell({ k, v }) {
  return (
    <div className="spec-cell">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  )
}

/* ── Task modal ────────────────────────────────────────────────────────── */
function TaskModal({ machine, onClose, navigate }) {
  const [desc, setDesc] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [lang, setLang] = useState('te-IN')
  const [recState, setRecState] = useState('idle')   // idle|recording|processing|done|error
  const recorderRef = useRef(null)

  const cost = Number(machine.price_per_hour || 0).toFixed(2)

  function blobToBase64(blob) {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(String(reader.result).split(',', 2)[1] || '')
      reader.readAsDataURL(blob)
    })
  }

  async function startRecording() {
    if (recState === 'recording') { recorderRef.current?.stop(); return }
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const chunks = []
      recorder.ondataavailable = e => chunks.push(e.data)
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        setRecState('processing')
        try {
          const blob = new Blob(chunks, { type: 'audio/wav' })
          const base64 = await blobToBase64(blob)
          const res = await fetch(`${API}/sarvam/transcribe`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audio_base64: base64, language: lang }),
          })
          const data = await res.json()
          if (data.transcript) { setDesc(data.transcript); setRecState('done') }
          else { setRecState('error') }
        } catch { setRecState('error') }
      }
      recorderRef.current = recorder
      recorder.start()
      setRecState('recording')
      setTimeout(() => { try { recorder.stop() } catch {} }, 5000)
    } catch {
      setRecState('error')
      setError('Microphone permission denied.')
    }
  }

  async function submit() {
    if (!desc.trim()) { setError('Describe what you want the agent to do.'); return }
    setSubmitting(true); setError('')
    try {
      const res = await fetch(`${API}/tasks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ machine_id: machine.id, task_description: desc.trim(), task_type: 'browsing' }),
      })
      const task = await res.json()
      if (!res.ok) { setError(task.detail || 'Failed to submit task'); setSubmitting(false); return }
      navigate(`/tasks/${task.id}`)
    } catch { setError('Network error — is the coordinator running?'); setSubmitting(false) }
  }

  const recording = recState === 'recording'
  const statusText = {
    recording:  'Listening... (5s)',
    processing: 'Transcribing...',
    done:       'Tap to speak again',
    error:      'Could not hear clearly, please type',
  }[recState] || ''
  const statusColor = recState === 'error' ? 'var(--danger)' : 'var(--text-tertiary)'

  const LANGS = [{ c: 'te-IN', t: 'తెలుగు' }, { c: 'hi-IN', t: 'हिंदी' }, { c: 'en-IN', t: 'English' }]

  return (
    <div style={s.backdrop} onClick={onClose}>
      <div style={s.modal} onClick={e => e.stopPropagation()}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 700, letterSpacing: '-0.03em' }}>New Task</h2>
        <p className="sec" style={s.modalInfo}>
          {machine.display_name} · {(machine.os || '').toUpperCase()} · {machine.ram_gb}GB
        </p>

        <div style={{ position: 'relative' }}>
          <textarea className="textarea" value={desc} autoFocus
            placeholder="Describe what you want the agent to do..."
            onChange={e => { setDesc(e.target.value); setError('') }}
            style={{ paddingBottom: 44 }} />
          <button onClick={startRecording} title="Voice input"
            style={{ ...s.mic, borderColor: recording ? 'var(--danger-border)' : 'var(--accent-border)',
                     color: recording ? 'var(--danger)' : 'var(--accent)' }}>
            <Mic size={16} />
          </button>
        </div>

        {statusText && <p style={{ fontSize: '0.75rem', color: statusColor, marginTop: 6 }}>{statusText}</p>}

        <div style={{ display: 'flex', gap: 6, marginTop: 10, alignItems: 'center' }}>
          <span className="ter" style={{ fontSize: '0.6875rem' }}>Speak in:</span>
          {LANGS.map(l => (
            <button key={l.c} className={`chip${lang === l.c ? ' active' : ''}`}
              style={{ fontSize: '0.6875rem', padding: '4px 12px' }} onClick={() => setLang(l.c)}>{l.t}</button>
          ))}
        </div>

        <p className="ter" style={{ fontSize: '0.75rem', marginTop: 12 }}>Est. {cost} CWX</p>
        {error && <p style={{ color: 'var(--danger)', fontSize: '0.8125rem', marginTop: 8 }}>{error}</p>}

        <div className="between" style={{ marginTop: 20 }}>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={submitting} onClick={submit}>
            {submitting ? 'Submitting…' : <>Submit Task <ArrowRight size={16} /></>}
          </button>
        </div>
      </div>
    </div>
  )
}

const cityFrom = (m) => {
  if (m.latitude == null) return 'Unknown'
  return `${Number(m.latitude).toFixed(1)},${Number(m.longitude).toFixed(1)}`
}
const shorten = (v) => !v ? '' : (v.length > 16 ? v.slice(0, 16) + '…' : v)

const s = {
  grid:     { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 },
  specGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  backdrop: { position: 'fixed', inset: 0, background: 'rgba(5,8,16,0.75)', backdropFilter: 'blur(4px)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24 },
  modal:    { width: 480, maxWidth: '100%', background: 'var(--bg-surface)', border: '1px solid var(--border-normal)',
              borderRadius: 'var(--radius-lg)', padding: 28 },
  modalInfo:{ fontSize: '0.8125rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 14, marginBottom: 18, marginTop: 4 },
  mic:      { position: 'absolute', left: 8, bottom: 8, width: 32, height: 32, borderRadius: '50%', background: 'var(--bg-muted)',
              border: '1px solid var(--accent-border)', display: 'flex', alignItems: 'center', justifyContent: 'center' },
}
