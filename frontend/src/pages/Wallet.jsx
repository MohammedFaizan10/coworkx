/**
 * Wallet — large balance, clean transaction table, proof verifier. Dark premium.
 */

import { useEffect, useState } from 'react'
import Navbar from '../components/Navbar'
import { SectionHeader, RelTime } from '../components/ui'

const API = 'http://localhost:8000'
const TX_PILL = { lock: 'type', release: 'click', refund: 'navigate', reward: 'click' }
const DEBIT = new Set(['lock'])   // money leaving the user

export default function Wallet() {
  const [balance, setBalance] = useState(null)
  const [txs, setTxs] = useState([])
  const [proofId, setProofId] = useState('')
  const [proof, setProof] = useState(null)
  const [proofErr, setProofErr] = useState('')

  useEffect(() => {
    load(); const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  async function load() {
    try {
      const [b, t] = await Promise.all([
        fetch(`${API}/wallet/balance`).then(r => r.json()),
        fetch(`${API}/wallet/transactions`).then(r => r.json()),
      ])
      setBalance(b.balance); setTxs(Array.isArray(t) ? t : [])
    } catch (e) { console.error(e) }
  }

  async function verify(idArg) {
    const tid = (idArg ?? proofId).trim()
    if (!tid) { setProofErr('Paste a task ID first.'); return }
    setProofId(tid); setProofErr(''); setProof(null)
    try {
      const res = await fetch(`${API}/tasks/${tid}/proof`)
      const data = await res.json()
      if (!res.ok) { setProofErr(data.detail || 'Could not verify'); return }
      setProof(data)
    } catch { setProofErr('Network error.') }
  }

  return (
    <div>
      <Navbar />
      <div className="page">
        {/* BALANCE */}
        <div style={{ textAlign: 'center', margin: '40px 0' }}>
          <div className="label" style={{ marginBottom: 8 }}>CWX Balance</div>
          <div style={{ fontSize: '3.5rem', fontWeight: 700, letterSpacing: '-0.04em', lineHeight: 1 }}>
            {balance == null ? '—' : balance.toFixed(2)}
          </div>
          <p className="sec" style={{ fontSize: '0.8125rem', marginTop: 8 }}>CoWorkX Network Credits</p>
        </div>

        <div style={s.cols}>
          {/* TRANSACTIONS */}
          <div>
            <SectionHeader title="Transactions" />
            <div className="card" style={{ overflow: 'hidden' }}>
              <table style={s.table}>
                <thead>
                  <tr>{['Type', 'Amount', 'Task', 'Hash', 'Time'].map(h =>
                    <th key={h} className="label" style={s.th}>{h}</th>)}</tr>
                </thead>
                <tbody>
                  {txs.length === 0 && (
                    <tr><td colSpan={5} className="ter" style={{ padding: 24, textAlign: 'center', fontSize: '0.8125rem' }}>No transactions yet.</td></tr>
                  )}
                  {txs.map(tx => {
                    const debit = DEBIT.has(tx.type)
                    return (
                      <tr key={tx.id} style={s.tr}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-elevated)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                        <td style={s.td}><span className={`pill ${TX_PILL[tx.type] || 'default'}`}>{tx.type}</span></td>
                        <td style={s.td}>
                          <span className="mono" style={{ fontSize: '0.75rem', color: debit ? 'var(--danger)' : 'var(--success)' }}>
                            {debit ? '-' : '+'}{tx.amount.toFixed(2)}
                          </span>
                        </td>
                        <td style={s.td}>
                          {tx.task_id
                            ? <button className="mono" onClick={() => verify(tx.task_id)} title={tx.task_id}
                                style={{ background: 'none', border: 'none', padding: 0, color: 'var(--accent)', cursor: 'pointer', fontSize: '0.6875rem' }}>
                                {tx.task_id.slice(0, 8)}…</button>
                            : <span className="ter">—</span>}
                        </td>
                        <td style={s.td}><span className="mono ter" style={{ fontSize: '0.6875rem' }} title={tx.tx_hash}>{tx.tx_hash.slice(0, 10)}…</span></td>
                        <td style={s.td}><RelTime value={tx.created_at} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* PROOF */}
          <div>
            <SectionHeader title="Proof of Execution" />
            <div className="card" style={{ padding: 20 }}>
              <div className="row" style={{ gap: 8 }}>
                <input className="input mono" style={{ fontSize: '0.75rem' }} placeholder="Paste a task ID…"
                  value={proofId} onChange={e => setProofId(e.target.value)} />
                <button className="btn-primary" onClick={() => verify()}>Verify</button>
              </div>
              {proofErr && <p style={{ color: 'var(--danger)', fontSize: '0.8125rem', marginTop: 8 }}>{proofErr}</p>}
              {proof && (
                <div style={{ marginTop: 16 }}>
                  <div className="live-bar" />
                  <div className="label" style={{ color: proof.verified ? 'var(--success)' : 'var(--warning)', marginBottom: 12 }}>
                    {proof.verified ? 'Verified ✓' : 'No steps'}
                  </div>
                  <div className="between" style={{ marginBottom: 8 }}>
                    <span className="ter" style={{ fontSize: '0.75rem' }}>Steps</span>
                    <span style={{ fontWeight: 700 }}>{proof.steps_count}</span>
                  </div>
                  <div className="ter" style={{ fontSize: '0.6875rem', marginBottom: 4 }}>Execution hash</div>
                  <p className="mono" style={{ fontSize: '0.625rem', color: 'var(--accent)', wordBreak: 'break-all' }}>{proof.execution_hash}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

const s = {
  cols:  { display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 24, alignItems: 'start' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th:    { textAlign: 'left', padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' },
  tr:    { borderBottom: '1px solid var(--border-subtle)', transition: 'background 0.1s' },
  td:    { padding: '12px 16px', fontSize: '0.8125rem' },
}
