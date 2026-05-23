import React, { useEffect, useState, useRef } from 'react'
import { fetchConfig, saveConfig } from '../api'

interface Schema    { catalog: string; schema: string }
interface Exception { catalog: string; schema: string; table: string }
interface Grant     { sql: string; status: string; error?: string }

interface Config {
  schemas:     Schema[]
  tag_columns: string[]
  exceptions:  Exception[]
}

interface Diff {
  added_schemas:     Schema[]
  removed_schemas:   Schema[]
  added_tags:        string[]
  removed_tags:      string[]
  added_exceptions:  Exception[]
  removed_exceptions: Exception[]
}

const inp: React.CSSProperties = {
  padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 5,
  fontSize: 13, color: '#374151', outline: 'none', width: '100%',
}
const btn = (color = '#FF3621'): React.CSSProperties => ({
  padding: '6px 14px', borderRadius: 5, border: 'none',
  background: color, color: '#fff', fontSize: 12,
  cursor: 'pointer', fontWeight: 600, whiteSpace: 'nowrap',
})
const ghost: React.CSSProperties = {
  padding: '5px 12px', borderRadius: 5, border: '1px solid #d1d5db',
  background: '#fff', fontSize: 12, color: '#374151', cursor: 'pointer',
}

const Section = ({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) => (
  <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', marginBottom: 24 }}>
    <div style={{ padding: '16px 24px', borderBottom: '1px solid #f3f4f6' }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: '#1B3139' }}>{title}</div>
      <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>{subtitle}</div>
    </div>
    <div style={{ padding: '20px 24px' }}>{children}</div>
  </div>
)

const Tag = ({ label, onRemove }: { label: string; onRemove: () => void }) => (
  <div style={{
    display: 'inline-flex', alignItems: 'center', gap: 6,
    background: '#f3f4f6', borderRadius: 20, padding: '4px 12px',
    fontSize: 12, color: '#374151',
  }}>
    {label}
    <span onClick={onRemove} style={{ cursor: 'pointer', color: '#9ca3af', fontSize: 14, lineHeight: 1 }}>×</span>
  </div>
)

function computeDiff(original: Config, current: Config): Diff {
  return {
    added_schemas:      current.schemas.filter(s => !original.schemas.some(o => o.catalog === s.catalog && o.schema === s.schema)),
    removed_schemas:    original.schemas.filter(s => !current.schemas.some(c => c.catalog === s.catalog && c.schema === s.schema)),
    added_tags:         current.tag_columns.filter(t => !original.tag_columns.includes(t)),
    removed_tags:       original.tag_columns.filter(t => !current.tag_columns.includes(t)),
    added_exceptions:   current.exceptions.filter(e => !original.exceptions.some(o => o.catalog === e.catalog && o.schema === e.schema && o.table === e.table)),
    removed_exceptions: original.exceptions.filter(e => !current.exceptions.some(c => c.catalog === e.catalog && c.schema === e.schema && c.table === e.table)),
  }
}

function hasDiff(d: Diff) {
  return d.added_schemas.length || d.removed_schemas.length ||
    d.added_tags.length || d.removed_tags.length ||
    d.added_exceptions.length || d.removed_exceptions.length
}

function ConfirmModal({ diff, onConfirm, onCancel }: {
  diff: Diff; onConfirm: () => void; onCancel: () => void
}) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: '#fff', borderRadius: 10, padding: 28, maxWidth: 520, width: '100%',
        boxShadow: '0 8px 32px rgba(0,0,0,0.18)', maxHeight: '80vh', overflowY: 'auto',
      }}>
        <h2 style={{ margin: '0 0 6px', fontSize: 17, color: '#1B3139' }}>Confirm Configuration Changes</h2>
        <p style={{ margin: '0 0 18px', fontSize: 13, color: '#6b7280' }}>
          The following changes will be applied, and required permissions will be granted to the app service principal.
        </p>

        {diff.added_schemas.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#00A972', marginBottom: 4 }}>+ Schemas added</div>
            {diff.added_schemas.map((s, i) => (
              <div key={i} style={{ fontSize: 12, color: '#374151', padding: '2px 8px' }}>
                {s.catalog} · {s.schema}
              </div>
            ))}
          </div>
        )}
        {diff.removed_schemas.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#FF3621', marginBottom: 4 }}>− Schemas removed</div>
            {diff.removed_schemas.map((s, i) => (
              <div key={i} style={{ fontSize: 12, color: '#374151', padding: '2px 8px' }}>
                {s.catalog} · {s.schema}
              </div>
            ))}
          </div>
        )}
        {diff.added_tags.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#00A972', marginBottom: 4 }}>+ Tags added</div>
            <div style={{ fontSize: 12, color: '#374151', padding: '2px 8px' }}>{diff.added_tags.join(', ')}</div>
          </div>
        )}
        {diff.removed_tags.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#FF3621', marginBottom: 4 }}>− Tags removed</div>
            <div style={{ fontSize: 12, color: '#374151', padding: '2px 8px' }}>{diff.removed_tags.join(', ')}</div>
          </div>
        )}
        {diff.added_exceptions.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#00A972', marginBottom: 4 }}>+ Exceptions added</div>
            {diff.added_exceptions.map((e, i) => (
              <div key={i} style={{ fontSize: 12, color: '#374151', padding: '2px 8px' }}>
                {e.catalog}.{e.schema}.{e.table}
              </div>
            ))}
          </div>
        )}
        {diff.removed_exceptions.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#FF3621', marginBottom: 4 }}>− Exceptions removed</div>
            {diff.removed_exceptions.map((e, i) => (
              <div key={i} style={{ fontSize: 12, color: '#374151', padding: '2px 8px' }}>
                {e.catalog}.{e.schema}.{e.table}
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, marginTop: 22, justifyContent: 'flex-end' }}>
          <button style={ghost} onClick={onCancel}>Cancel</button>
          <button style={{ ...btn('#FF3621'), padding: '8px 22px' }} onClick={onConfirm}>
            Confirm & Save
          </button>
        </div>
      </div>
    </div>
  )
}

function GrantResults({ grants }: { grants: Grant[] }) {
  const [open, setOpen] = useState(false)
  const failed = grants.filter(g => g.status === 'failed')
  const failedSql = failed.map(g => `-- ${g.error || 'failed'}\n${g.sql}`).join('\n\n')

  return (
    <div style={{
      marginBottom: 16, borderRadius: 8, border: `1px solid ${failed.length ? '#fca5a5' : '#86efac'}`,
      background: failed.length ? '#fff5f5' : '#f0fdf4',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', textAlign: 'left', padding: '12px 16px',
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 13, fontWeight: 600,
          color: failed.length ? '#FF3621' : '#00A972',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}
      >
        <span>
          {failed.length
            ? `⚠ ${failed.length} grant(s) failed — run manually`
            : `✓ All ${grants.length} grants applied successfully`}
        </span>
        <span style={{ fontSize: 11 }}>{open ? '▲' : '▼'} details</span>
      </button>

      {open && (
        <div style={{ padding: '0 16px 16px' }}>
          {grants.map((g, i) => (
            <div key={i} style={{
              display: 'flex', gap: 8, alignItems: 'flex-start',
              padding: '4px 0', borderTop: i === 0 ? 'none' : '1px solid #f3f4f6',
            }}>
              <span style={{ fontSize: 12, width: 14, flexShrink: 0, marginTop: 1 }}>
                {g.status === 'ok' ? '✓' : g.status === 'skipped' ? '–' : '✗'}
              </span>
              <div style={{ flex: 1 }}>
                <code style={{ fontSize: 11, wordBreak: 'break-all', color: g.status === 'failed' ? '#FF3621' : '#374151' }}>
                  {g.sql}
                </code>
                {g.error && <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{g.error}</div>}
              </div>
            </div>
          ))}

          {failed.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                Run these statements as a metastore admin:
              </div>
              <textarea
                readOnly
                value={failedSql}
                rows={Math.min(failed.length * 3, 10)}
                style={{
                  width: '100%', fontSize: 11, fontFamily: 'monospace',
                  border: '1px solid #fca5a5', borderRadius: 4, padding: 8,
                  background: '#fff', color: '#374151', resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
              <button
                style={{ ...btn('#374151'), marginTop: 6, fontSize: 11 }}
                onClick={() => navigator.clipboard.writeText(failedSql)}
              >
                Copy SQL
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Settings({ onSaved }: { onSaved: () => void }) {
  const [schemas,        setSchemas]        = useState<Schema[]>([])
  const [tagCols,        setTagCols]        = useState<string[]>([])
  const [exceptions,     setExceptions]     = useState<Exception[]>([])
  const [originalConfig, setOriginalConfig] = useState<Config | null>(null)
  const [loading,      setLoading]      = useState(true)
  const [saveStatus,   setSaveStatus]   = useState<'idle' | 'saving' | 'done' | 'error'>('idle')
  const [saveMessage,  setSaveMessage]  = useState('')
  const [noChanges,    setNoChanges]    = useState(false)
  const [pendingDiff,  setPendingDiff]  = useState<Diff | null>(null)
  const [grantResults, setGrantResults] = useState<Grant[] | null>(null)

  const [newSchema, setNewSchema] = useState({ catalog: '', schema: '' })
  const [newTag,    setNewTag]    = useState('')
  const [newExc,    setNewExc]    = useState({ catalog: '', schema: '', table: '' })

  useEffect(() => {
    fetchConfig()
      .then(d => {
        const cfg: Config = {
          schemas:     d.schemas     || [],
          tag_columns: d.tag_columns || [],
          exceptions:  d.exceptions  || [],
        }
        setSchemas(cfg.schemas)
        setTagCols(cfg.tag_columns)
        setExceptions(cfg.exceptions)
        setOriginalConfig(cfg)
      })
      .catch(e => { setSaveStatus('error'); setSaveMessage(e.message) })
      .finally(() => setLoading(false))
  }, [])

  const handleSaveClick = () => {
    setNoChanges(false)
    setGrantResults(null)
    const current: Config = { schemas, tag_columns: tagCols, exceptions }
    if (!originalConfig) {
      // First-time setup — skip diff
      setPendingDiff({ added_schemas: schemas, removed_schemas: [], added_tags: tagCols, removed_tags: [], added_exceptions: exceptions, removed_exceptions: [] })
      return
    }
    const diff = computeDiff(originalConfig, current)
    if (!hasDiff(diff)) {
      setNoChanges(true)
      return
    }
    setPendingDiff(diff)
  }

  const confirmSave = () => {
    const newCfg: Config = { schemas, tag_columns: tagCols, exceptions }

    // Optimistic: apply locally and show success immediately
    setPendingDiff(null)
    setGrantResults(null)
    setNoChanges(false)
    setOriginalConfig(newCfg)
    setSaveStatus('done')
    setSaveMessage('Changes saved. Syncing to database…')

    // Background: persist to Delta table, then refresh data views
    saveConfig({ schemas, tag_columns: tagCols, exceptions })
      .then(result => {
        setGrantResults(result.grants || [])
        setSaveMessage('Configuration saved successfully.')
        onSaved()
      })
      .catch((e: any) => {
        setSaveStatus('error')
        setSaveMessage(`Local changes applied but sync failed: ${e.message}`)
      })
  }

  const addSchema = () => {
    if (!newSchema.catalog.trim() || !newSchema.schema.trim()) return
    if (schemas.some(s => s.catalog === newSchema.catalog && s.schema === newSchema.schema)) return
    setSchemas(p => [...p, { ...newSchema }])
    setNewSchema({ catalog: '', schema: '' })
  }

  const addTag = () => {
    const t = newTag.trim()
    if (!t || tagCols.includes(t)) return
    setTagCols(p => [...p, t])
    setNewTag('')
  }

  const addException = () => {
    const e = newExc
    if (!e.catalog.trim() || !e.schema.trim() || !e.table.trim()) return
    if (exceptions.some(x => x.catalog === e.catalog && x.schema === e.schema && x.table === e.table)) return
    setExceptions(p => [...p, { ...e }])
    setNewExc({ catalog: '', schema: '', table: '' })
  }

  if (loading) return <div style={{ padding: 40, color: '#6b7280' }}>Loading configuration…</div>

  return (
    <div style={{ padding: '24px 32px', maxWidth: 820 }}>

      {pendingDiff && (
        <ConfirmModal
          diff={pendingDiff}
          onConfirm={confirmSave}
          onCancel={() => setPendingDiff(null)}
        />
      )}

      {/* ── Save status banner ───────────────────────────────────── */}
      {saveStatus !== 'idle' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px', borderRadius: 8, marginBottom: 20,
          background: saveStatus === 'done' ? '#f0fdf4' : '#fff5f5',
          border: `1px solid ${saveStatus === 'done' ? '#86efac' : '#fca5a5'}`,
        }}>
          <span style={{ fontSize: 16, flexShrink: 0 }}>
            {saveStatus === 'done' ? '✓' : '✗'}
          </span>
          <span style={{
            fontSize: 13, fontWeight: 500, flex: 1,
            color: saveStatus === 'done' ? '#00A972' : '#FF3621',
          }}>
            {saveMessage}
          </span>
          <button
            onClick={() => { setSaveStatus('idle'); setGrantResults(null) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 16, lineHeight: 1 }}
          >×</button>
        </div>
      )}

      {grantResults && <GrantResults grants={grantResults} />}

      {/* ── Schemas ─────────────────────────────────────────────── */}
      <Section title="Scanned Schemas" subtitle="Catalog + schema pairs the app will scan for tables and tags.">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          {schemas.map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#f9fafb', borderRadius: 6, padding: '8px 12px' }}>
              <span style={{ fontSize: 13, color: '#374151', flex: 1 }}>
                <strong>{s.catalog}</strong> · {s.schema}
              </span>
              <button style={ghost} onClick={() => setSchemas(p => p.filter((_, j) => j !== i))}>Remove</button>
            </div>
          ))}
          {schemas.length === 0 && <div style={{ fontSize: 12, color: '#9ca3af' }}>No schemas configured.</div>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={newSchema.catalog} onChange={e => setNewSchema(p => ({ ...p, catalog: e.target.value }))}
            placeholder="catalog_name" style={{ ...inp, maxWidth: 240 }} />
          <input value={newSchema.schema} onChange={e => setNewSchema(p => ({ ...p, schema: e.target.value }))}
            placeholder="schema_name" style={{ ...inp, maxWidth: 200 }}
            onKeyDown={e => e.key === 'Enter' && addSchema()} />
          <button style={btn('#00A972')} onClick={addSchema}>+ Add</button>
        </div>
      </Section>

      {/* ── Tag Columns ─────────────────────────────────────────── */}
      <Section title="Tag Names" subtitle="Tag keys that will be displayed, edited, and applied to tables.">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {tagCols.map((t, i) => (
            <Tag key={i} label={t} onRemove={() => setTagCols(p => p.filter((_, j) => j !== i))} />
          ))}
          {tagCols.length === 0 && <span style={{ fontSize: 12, color: '#9ca3af' }}>No tags configured.</span>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={newTag} onChange={e => setNewTag(e.target.value)}
            placeholder="TagName" style={{ ...inp, maxWidth: 220 }}
            onKeyDown={e => e.key === 'Enter' && addTag()} />
          <button style={btn('#00A972')} onClick={addTag}>+ Add</button>
        </div>
      </Section>

      {/* ── Exceptions ──────────────────────────────────────────── */}
      <Section title="Table Exceptions" subtitle="Tables excluded from all scans, counts, and the table list.">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          {exceptions.map((e, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#fff7f5', borderRadius: 6, padding: '8px 12px', border: '1px solid #fee2da' }}>
              <span style={{ fontSize: 13, color: '#374151', flex: 1 }}>
                {e.catalog}.<strong>{e.schema}</strong>.{e.table}
              </span>
              <button style={ghost} onClick={() => setExceptions(p => p.filter((_, j) => j !== i))}>Remove</button>
            </div>
          ))}
          {exceptions.length === 0 && <div style={{ fontSize: 12, color: '#9ca3af' }}>No exceptions — all tables in scanned schemas are included.</div>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={newExc.catalog} onChange={e => setNewExc(p => ({ ...p, catalog: e.target.value }))}
            placeholder="catalog" style={{ ...inp, maxWidth: 180 }} />
          <input value={newExc.schema} onChange={e => setNewExc(p => ({ ...p, schema: e.target.value }))}
            placeholder="schema" style={{ ...inp, maxWidth: 150 }} />
          <input value={newExc.table} onChange={e => setNewExc(p => ({ ...p, table: e.target.value }))}
            placeholder="table_name" style={{ ...inp, maxWidth: 180 }}
            onKeyDown={e => e.key === 'Enter' && addException()} />
          <button style={btn('#FF3621')} onClick={addException}>+ Add</button>
        </div>
      </Section>

      {/* ── Footer ──────────────────────────────────────────────── */}
      {noChanges && <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 12 }}>No changes to save.</div>}

      <div style={{ display: 'flex', gap: 10 }}>
        <button
          onClick={handleSaveClick}
          disabled={saveStatus === 'saving'}
          style={{ ...btn(saveStatus === 'saving' ? '#9ca3af' : '#FF3621'), padding: '10px 28px', fontSize: 14 }}
        >
          Save Configuration
        </button>
      </div>
    </div>
  )
}
