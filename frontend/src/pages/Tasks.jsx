/**
 * Tasks — list of all tasks, newest first. Dark premium.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Navbar from '../components/Navbar'
import { SectionHeader, StatusTag, RelTime } from '../components/ui'

const API = 'http://localhost:8000'

export default function Tasks() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    load(); const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  async function load() {
    try {
      const res = await fetch(`${API}/tasks`)
      const data = await res.json()
      setTasks(Array.isArray(data) ? data : [])
    } catch (e) { console.error(e) } finally { setLoading(false) }
  }

  const anyRunning = tasks.some(t => t.status === 'running')

  return (
    <div>
      <Navbar />
      <div className="page">
        <SectionHeader title="Tasks" live={anyRunning} />

        {loading && <p className="ter">Loading…</p>}

        {!loading && tasks.length === 0 && (
          <div className="card" style={{ padding: 48, textAlign: 'center' }}>
            <p className="sec" style={{ marginBottom: 16 }}>No tasks yet.</p>
            <Link to="/" className="btn">Go to Marketplace</Link>
          </div>
        )}

        {tasks.length > 0 && (
          <div className="card" style={{ overflow: 'hidden' }}>
            {tasks.map(t => (
              <Link key={t.id} to={`/tasks/${t.id}`} style={s.row}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="between">
                    <span style={{ fontSize: '0.875rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t.task_description}
                    </span>
                    <RelTime value={t.created_at} />
                  </div>
                  <div className="row" style={{ gap: 10, marginTop: 6 }}>
                    <StatusTag status={t.status} />
                    {t.steps_count != null && <span className="ter" style={{ fontSize: '0.6875rem' }}>{t.steps_count} steps</span>}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const s = {
  row: { display: 'flex', gap: 12, padding: '14px 16px', borderBottom: '1px solid var(--border-subtle)', color: 'inherit' },
}
