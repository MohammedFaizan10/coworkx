/**
 * Navbar — 56px, sticky, blurred, dark. CoWork[X] wordmark + mono balance pill.
 */

import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { API } from '../config'
const LINKS = [
  { to: '/',        label: 'Marketplace' },
  { to: '/tasks',   label: 'Tasks' },
  { to: '/wallet',  label: 'Wallet' },
  { to: '/network', label: 'Network' },
]

export default function Navbar() {
  const { pathname } = useLocation()
  const [balance, setBalance] = useState(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const [b, m] = await Promise.all([
          fetch(`${API}/wallet/balance`).then(r => r.json()),
          fetch(`${API}/machines`).then(r => r.json()),
        ])
        if (!alive) return
        setBalance(b.balance)
        setConnected(Array.isArray(m) && m.some(x => x.status === 'online'))
      } catch { /* ignore */ }
    }
    load(); const id = setInterval(load, 30000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const active = (to) => to === '/' ? pathname === '/' : pathname.startsWith(to)

  return (
    <nav style={s.nav}>
      <div style={s.brand}>
        <span style={{ fontWeight: 700, fontSize: '1rem', letterSpacing: '-0.03em' }}>CoWork</span>
        <span style={{ fontWeight: 700, fontSize: '1rem', letterSpacing: '-0.03em', color: 'var(--accent)' }}>X</span>
      </div>

      <div style={s.center}>
        {LINKS.map(l => (
          <Link key={l.to} to={l.to} style={{
            ...s.link,
            color: active(l.to) ? 'var(--accent)' : 'var(--text-tertiary)',
            borderBottom: active(l.to) ? '2px solid var(--accent)' : '2px solid transparent',
          }}>{l.label}</Link>
        ))}
      </div>

      <div style={s.pill}>
        {connected && <span style={s.pulse} />}
        <span className="mono" style={{ fontSize: '0.75rem' }}>
          {balance == null ? '—' : `${balance.toFixed(2)} CWX`}
        </span>
      </div>
    </nav>
  )
}

const s = {
  nav:    { position: 'sticky', top: 0, zIndex: 100, height: 56, background: 'var(--bg-surface)',
            borderBottom: '1px solid var(--border-subtle)', backdropFilter: 'blur(12px)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' },
  brand:  { display: 'flex', alignItems: 'center' },
  center: { display: 'flex', alignItems: 'center', gap: 32, height: '100%' },
  link:   { fontSize: '0.8125rem', fontWeight: 500, height: '100%', display: 'flex', alignItems: 'center', paddingTop: 2 },
  pill:   { display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg-elevated)',
            border: '1px solid var(--border-normal)', borderRadius: 'var(--radius-pill)', padding: '6px 14px' },
  pulse:  { width: 7, height: 7, borderRadius: '50%', background: 'var(--success)', animation: 'pulseBar 1.6s ease-in-out infinite' },
}
