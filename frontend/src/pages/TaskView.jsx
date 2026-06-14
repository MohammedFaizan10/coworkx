/**
 * TaskView — 60% stream + 40% agent log. Dark premium. Socket.io logic intact.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { io } from 'socket.io-client'
import { ArrowLeft, Volume2, VolumeX } from 'lucide-react'
import Navbar from '../components/Navbar'
import { SectionHeader, ActionPill, StatusTag, RelTime } from '../components/ui'

import { API } from '../config'

export default function TaskView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const canvasRef = useRef(null)
  const logRef = useRef(null)
  const frameCount = useRef(0)

  const [task, setTask] = useState(null)
  const [steps, setSteps] = useState([])
  const [status, setStatus] = useState('queued')
  const [output, setOutput] = useState(null)
  const [streamLive, setStreamLive] = useState(false)
  const [muted, setMuted] = useState(false)   // default unmuted for the demo
  const narrated = useRef(new Set())

  useEffect(() => {
    let cancelled = false
    fetch(`${API}/tasks/${id}`).then(r => r.json()).then(d => {
      if (cancelled) return
      setTask(d); setStatus(d.status || 'queued'); setSteps(d.steps || [])
      if (d.status === 'completed') setOutput(d.output_url)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [id])

  const renderFrame = useCallback(async (data) => {
    const canvas = canvasRef.current
    if (!canvas) return
    try {
      const bmp = await createImageBitmap(new Blob([data], { type: 'image/jpeg' }))
      canvas.getContext('2d').drawImage(bmp, 0, 0, canvas.width, canvas.height)
      bmp.close(); frameCount.current += 1; setStreamLive(true)
    } catch { /* drop */ }
  }, [])

  useEffect(() => {
    if (!id) return
    const socket = io(API, { transports: ['polling', 'websocket'], reconnection: true })
    socket.on('connect', () => socket.emit('join_task_room', { task_id: id }))
    socket.on('stream_frame', renderFrame)
    socket.on('stream_ended', () => setStreamLive(false))
    socket.on('task_update', (msg) => {
      if (msg.task_id !== id) return
      if (msg.type === 'step' && msg.step) {
        setSteps(prev => prev.some(x => x.step_number === msg.step.step_number) ? prev : [...prev, msg.step])
      } else if (msg.type === 'status') {
        setStatus(msg.status)
        if (msg.status === 'completed') setOutput(msg.output)
      }
    })
    return () => socket.disconnect()
  }, [id, renderFrame])

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [steps])

  // ── TTS narration (Sarvam bulbul:v3, Hindi). ───────────────────────────
  // NOTE: Chrome blocks autoplay until the user interacts with the page.
  // The "Submit Task" click on the previous page counts as interaction,
  // so narration works once we land here from a submit.
  useEffect(() => {
    if (muted || steps.length === 0) return
    const last = steps[steps.length - 1]
    if (!last || narrated.current.has(last.step_number)) return
    narrated.current.add(last.step_number)
    const text = String(last.reasoning || '').replace(/^\[.*?\]\s*/, '')   // strip [🧠 model · ms]
    if (!text.trim()) return
    ;(async () => {
      try {
        const res = await fetch(`${API}/sarvam/speak`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, language: 'hi-IN' }),
        })
        const data = await res.json()
        if (!data.audio_base64) return
        const audio = new Audio('data:audio/wav;base64,' + data.audio_base64)
        audio.play().catch(() => {})   // silent — autoplay may be blocked
      } catch { /* silent */ }
    })()
  }, [steps, muted])

  const running = status === 'running' || status === 'queued'
  const nodeId = task?.machine_id ? `node_${String(task.machine_id).slice(0, 4)}` : 'node_····'

  return (
    <div>
      <Navbar />
      <div style={s.bar}>
        <button className="btn-ghost" onClick={() => navigate('/')} style={{ padding: '4px 8px' }}>
          <ArrowLeft size={16} /> Marketplace
        </button>
        <StatusTag status={status} />
      </div>

      <div style={s.split}>
        {/* STREAM */}
        <div style={s.left}>
          <div className="between" style={{ marginBottom: 12 }}>
            <span className="mono ter" style={{ fontSize: '0.75rem' }}>{id}</span>
          </div>
          <div style={s.canvasWrap}>
            <canvas ref={canvasRef} width={1280} height={720} style={{ width: '100%', display: 'block' }} />
            {!streamLive && (
              <div style={s.overlay}>
                <span className="ter" style={{ fontSize: '0.8125rem' }}>
                  {status === 'completed' ? 'Stream ended' : 'Waiting for stream…'}
                </span>
              </div>
            )}
          </div>
          <p className="mono ter" style={{ fontSize: '0.6875rem', textAlign: 'center', marginTop: 8 }}>
            Live stream · {nodeId}
          </p>
        </div>

        {/* LOG */}
        <div style={s.right}>
          <SectionHeader title="Agent Log" live={running}
            right={<button className="btn-ghost" style={{ padding: 4 }} onClick={() => setMuted(m => !m)}>
              {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            </button>} />
          <p className="sec" style={{ fontSize: '0.8125rem', marginBottom: 12 }}>{task?.task_description}</p>

          <div ref={logRef} style={s.log}>
            {steps.length === 0 && <p className="ter" style={{ fontSize: '0.8125rem' }}>No steps yet. Waiting for the agent…</p>}
            {steps.map(step => (
              <div key={step.step_number} style={s.step}>
                <span className="mono ter" style={{ fontSize: '0.6875rem', width: 24, flexShrink: 0 }}>{step.step_number}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="between">
                    <ActionPill action={step.action_type} />
                    <span className="row" style={{ gap: 6 }}>
                      {narrated.current.has(step.step_number) && <Volume2 size={12} color="var(--text-tertiary)" />}
                      <RelTime value={step.executed_at} />
                    </span>
                  </div>
                  {step.reasoning && <p className="sec" style={{ fontSize: '0.75rem', marginTop: 4 }}>{step.reasoning}</p>}
                </div>
              </div>
            ))}
          </div>

          {status === 'completed' && (
            <div style={s.result}>
              <div className="label" style={{ color: 'var(--success)', marginBottom: 8 }}>Result</div>
              <p style={{ fontSize: '0.8125rem', wordBreak: 'break-word' }}>{output || 'Task finished.'}</p>
            </div>
          )}
          {status === 'failed' && (
            <div style={{ ...s.result, background: 'var(--danger-dim)', borderColor: 'var(--danger-border)' }}>
              <div className="label" style={{ color: 'var(--danger)', marginBottom: 8 }}>Failed</div>
              <p style={{ fontSize: '0.8125rem' }}>{task?.error_message || 'Task failed.'}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const s = {
  bar:   { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 24px',
           borderBottom: '1px solid var(--border-subtle)', maxWidth: 1280, margin: '0 auto' },
  split: { display: 'flex', maxWidth: 1280, margin: '0 auto', padding: 24, gap: 24, alignItems: 'flex-start' },
  left:  { flex: '0 0 58%', maxWidth: '58%', borderRight: '1px solid var(--border-subtle)', paddingRight: 24 },
  right: { flex: 1, minWidth: 0 },
  canvasWrap: { position: 'relative', background: 'var(--bg-void)', borderRadius: 'var(--radius-lg)', overflow: 'hidden', border: '1px solid var(--border-subtle)', lineHeight: 0 },
  overlay: { position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  log:   { border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', background: 'var(--bg-surface)',
           padding: 16, height: 440, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 },
  step:  { display: 'flex', gap: 10, alignItems: 'flex-start', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 10 },
  result:{ marginTop: 16, background: 'var(--success-dim)', border: '1px solid var(--success-border)', borderRadius: 'var(--radius-md)', padding: 14 },
}
