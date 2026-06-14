/**
 * StreamView.jsx — Live Screen Stream Canvas
 *
 * Connects to coordinator via Socket.io.
 * Joins the task room so it receives binary JPEG frames.
 * Renders each frame to a <canvas> using createImageBitmap
 * (fast, GPU-accelerated, no memory leaks).
 *
 * Props:
 *   taskId       (string) — UUID of the running task
 *   taskDesc     (string) — task description to display
 *   onComplete   (fn)     — called when task_completed event fires
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { io } from 'socket.io-client'

const COORDINATOR_URL = 'http://localhost:8000'

export default function StreamView({ taskId, taskDesc, onComplete }) {
  const canvasRef   = useRef(null)
  const socketRef   = useRef(null)
  const frameCount  = useRef(0)
  const lastFrameTs = useRef(Date.now())

  const [status,     setStatus]     = useState('connecting')  // connecting | streaming | completed | error
  const [frameStats, setFrameStats] = useState({ count: 0, fps: 0, kbps: 0 })
  const [output,     setOutput]     = useState(null)

  // ── FPS counter updates every second ────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      setFrameStats(prev => ({
        ...prev,
        fps: frameCount.current,
      }))
      frameCount.current = 0
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  // ── Render one JPEG frame to canvas ─────────────────────────────────────
  const renderFrame = useCallback(async (data) => {
    const canvas = canvasRef.current
    if (!canvas) return

    try {
      // data arrives as ArrayBuffer from socket.io binary event
      const blob   = new Blob([data], { type: 'image/jpeg' })
      const bitmap = await createImageBitmap(blob)
      const ctx    = canvas.getContext('2d')
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
      bitmap.close()   // Release GPU memory immediately

      frameCount.current += 1
      setFrameStats(prev => ({ ...prev, count: prev.count + 1 }))
    } catch (err) {
      // createImageBitmap failed — fall back to Image element
      try {
        const blob = new Blob([data], { type: 'image/jpeg' })
        const url  = URL.createObjectURL(blob)
        const img  = new Image()
        img.onload = () => {
          const ctx = canvasRef.current?.getContext('2d')
          if (ctx) ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
          URL.revokeObjectURL(url)
          frameCount.current += 1
        }
        img.onerror = () => URL.revokeObjectURL(url)
        img.src = url
      } catch (e) {
        // Ignore frame render errors
      }
    }
  }, [])

  // ── Socket.io connection ─────────────────────────────────────────────────
  useEffect(() => {
    if (!taskId) return

    const socket = io(COORDINATOR_URL, {
      transports: ['polling', 'websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
    })
    socketRef.current = socket

    socket.on('connect', () => {
      console.log('Socket.io connected:', socket.id)
      setStatus('connecting')
      // Join the room for this task so we receive its stream frames
      socket.emit('join_task_room', { task_id: taskId })
    })

    socket.on('room_joined', (data) => {
      console.log('Joined room:', data.room)
      setStatus('streaming')
    })

    // ── THE MAIN EVENT — binary JPEG frame from coordinator ───────────────
    socket.on('stream_frame', (data) => {
      renderFrame(data)
    })

    socket.on('stream_ended', (data) => {
      if (data.task_id === taskId) {
        console.log('Stream ended for task:', taskId)
      }
    })

    socket.on('task_completed', (data) => {
      if (data.task_id === taskId) {
        setStatus('completed')
        setOutput(data.output || 'Task completed')
        if (onComplete) onComplete(data)
      }
    })

    socket.on('connect_error', (err) => {
      console.error('Socket.io connect error:', err.message)
      setStatus('error')
    })

    socket.on('disconnect', () => {
      console.log('Socket.io disconnected')
    })

    return () => {
      socket.disconnect()
      socketRef.current = null
    }
  }, [taskId, renderFrame, onComplete])

  // ── Status badge styling ─────────────────────────────────────────────────
  const badgeStyle = {
    connecting: { background: '#f59e0b', color: '#000' },
    streaming:  { background: '#10d48e', color: '#000' },
    completed:  { background: '#6366f1', color: '#fff' },
    error:      { background: '#ef4444', color: '#fff' },
  }[status] || {}

  return (
    <div style={styles.wrapper}>

      {/* Header bar */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <div style={{ ...styles.badge, ...badgeStyle }}>
            {status === 'streaming'  && '● LIVE'}
            {status === 'connecting' && '◌ CONNECTING'}
            {status === 'completed'  && '✓ COMPLETE'}
            {status === 'error'      && '✕ ERROR'}
          </div>
          <span style={styles.taskDesc} title={taskDesc}>
            {taskDesc?.length > 60 ? taskDesc.slice(0, 60) + '…' : taskDesc}
          </span>
        </div>
        <div style={styles.stats}>
          {frameStats.fps} fps · {frameStats.count} frames
        </div>
      </div>

      {/* Canvas — 1280x720 scaled to fill container */}
      <div style={styles.canvasWrap}>
        {status === 'connecting' && (
          <div style={styles.overlay}>
            <div style={styles.spinner} />
            <div style={styles.overlayText}>Waiting for stream…</div>
            <div style={styles.overlaySubtext}>Task ID: {taskId?.slice(0, 8)}…</div>
          </div>
        )}
        <canvas
          ref={canvasRef}
          width={1280}
          height={720}
          style={styles.canvas}
        />
      </div>

      {/* Output panel — shown after task completes */}
      {status === 'completed' && output && (
        <div style={styles.output}>
          <div style={styles.outputLabel}>TASK OUTPUT</div>
          <div style={styles.outputText}>{output}</div>
        </div>
      )}

      {/* Task ID footer */}
      <div style={styles.footer}>
        Task: {taskId} · Room: task_{taskId?.slice(0, 8)}…
      </div>

    </div>
  )
}

// ── Styles ───────────────────────────────────────────────────────────────────
const styles = {
  wrapper: {
    background: '#06090f',
    border: '1px solid #1a2d44',
    borderRadius: 12,
    overflow: 'hidden',
    fontFamily: "'IBM Plex Mono', 'Courier New', monospace",
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 16px',
    background: '#0b1018',
    borderBottom: '1px solid #1a2d44',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  },
  badge: {
    padding: '3px 10px',
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.12em',
  },
  taskDesc: {
    color: '#7a90a8',
    fontSize: 13,
  },
  stats: {
    color: '#4a6080',
    fontSize: 11,
  },
  canvasWrap: {
    position: 'relative',
    background: '#000',
    lineHeight: 0,
  },
  canvas: {
    width: '100%',
    display: 'block',
  },
  overlay: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'rgba(6,9,15,0.9)',
    zIndex: 10,
    gap: 12,
  },
  overlayText: {
    color: '#dde8f5',
    fontSize: 16,
    fontWeight: 600,
  },
  overlaySubtext: {
    color: '#4a6080',
    fontSize: 12,
  },
  spinner: {
    width: 36,
    height: 36,
    border: '3px solid #1a2d44',
    borderTop: '3px solid #10d48e',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  output: {
    background: '#0b1018',
    borderTop: '1px solid #1a2d44',
    padding: '12px 16px',
  },
  outputLabel: {
    fontSize: 10,
    color: '#10d48e',
    letterSpacing: '0.2em',
    marginBottom: 6,
  },
  outputText: {
    color: '#dde8f5',
    fontSize: 13,
    lineHeight: 1.6,
  },
  footer: {
    padding: '6px 16px',
    background: '#06090f',
    borderTop: '1px solid #111927',
    color: '#2a3d54',
    fontSize: 10,
  },
}