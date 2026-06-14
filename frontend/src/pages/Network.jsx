/**
 * Network — stat cards + Leaflet map (CartoDB Positron) + task feed. Dark premium.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import Navbar from '../components/Navbar'
import { SectionHeader, RelTime } from '../components/ui'

const API = 'http://localhost:8000'
const COLOR = { online: '#10B981', busy: '#F59E0B', offline: '#EF4444' }

export default function Network() {
  const [machines, setMachines] = useState([])
  const [tasks, setTasks] = useState([])

  useEffect(() => {
    load(); const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  async function load() {
    try {
      const [m, t] = await Promise.all([
        fetch(`${API}/machines`).then(r => r.json()),
        fetch(`${API}/tasks`).then(r => r.json()),
      ])
      setMachines(Array.isArray(m) ? m : [])
      setTasks(Array.isArray(t) ? t : [])
    } catch (e) { console.error(e) }
  }

  const stats = useMemo(() => {
    const online = machines.filter(m => m.status === 'online').length
    const completed = tasks.filter(t => t.status === 'completed').length
    const running = tasks.filter(t => t.status === 'running').length
    return [
      { label: 'Nodes Online', value: online },
      { label: 'Total Nodes', value: machines.length },
      { label: 'Tasks Completed', value: completed },
      { label: 'Tasks Running', value: running },
    ]
  }, [machines, tasks])

  const mapped = machines.filter(m => m.latitude != null && m.longitude != null)
  const anyRunning = tasks.some(t => t.status === 'running')

  return (
    <div>
      <Navbar />
      <div className="page">
        <div style={{ marginBottom: 24 }}>
          <div className="live-bar" />
          <h1 style={{ fontSize: '1.5rem' }}>Network</h1>
        </div>

        <div style={s.stats}>
          {stats.map(st => (
            <div key={st.label} className="card" style={{ padding: '20px 24px' }}>
              <div className="label">{st.label}</div>
              <div style={{ fontSize: '2rem', fontWeight: 700, letterSpacing: '-0.04em', marginTop: 6 }}>{st.value}</div>
            </div>
          ))}
        </div>

        <div style={s.cols}>
          <div>
            <SectionHeader title="Node Map" live={anyRunning} />
            <div className="card" style={{ overflow: 'hidden', height: 380 }}>
              <MapContainer center={[20.59, 78.96]} zoom={4} style={{ height: '100%', width: '100%' }} scrollWheelZoom={false}>
                <TileLayer
                  url="https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png"
                  attribution="&copy; OpenStreetMap &copy; CARTO" />
                {mapped.map(m => (
                  <CircleMarker key={m.id}
                    center={[Number(m.latitude), Number(m.longitude)]}
                    radius={6}
                    pathOptions={{ color: COLOR[m.status] || COLOR.offline, fillColor: COLOR[m.status] || COLOR.offline, fillOpacity: 0.9, weight: 2 }}>
                    <Popup><strong>{m.display_name}</strong><br />{m.status} · {m.gpu_model || m.os}</Popup>
                  </CircleMarker>
                ))}
              </MapContainer>
            </div>
          </div>

          <div>
            <SectionHeader title="Task Feed" live={anyRunning} />
            <div className="card" style={{ maxHeight: 380, overflowY: 'auto' }}>
              {tasks.length === 0 && <p className="ter" style={{ padding: 16, fontSize: '0.8125rem' }}>No tasks yet.</p>}
              {tasks.slice(0, 30).map(t => (
                <Link key={t.id} to={`/tasks/${t.id}`} style={s.feedRow}>
                  <div className="between">
                    <span className="mono ter" style={{ fontSize: '0.6875rem' }}>node_{String(t.machine_id).slice(0, 4)}</span>
                    <RelTime value={t.created_at} />
                  </div>
                  <p className="sec" style={{ fontSize: '0.75rem', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.task_description}
                  </p>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

const s = {
  stats:   { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 32 },
  cols:    { display: 'grid', gridTemplateColumns: '1fr 320px', gap: 24, alignItems: 'start' },
  feedRow: { display: 'block', padding: 12, borderBottom: '1px solid var(--border-subtle)', color: 'inherit' },
}
