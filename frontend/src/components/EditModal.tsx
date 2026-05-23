import React, { useEffect, useState } from 'react'
import { fetchTags, applyTags } from '../api'

const TAG_COLUMNS = [
  'Domain', 'Subdomain', 'SubObject', 'DataElement',
  'Constraints', 'RefMasterData', 'DataClass', 'RetentionPeriod',
  'BronzeT', 'SilverT', 'GoldT',
]

interface Props {
  row: Record<string, string>
  onClose: () => void
  onSaved: () => void
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '7px 10px', border: '1px solid #d1d5db',
  borderRadius: 5, fontSize: 13, color: '#1B3139', outline: 'none',
}

const lockedStyle: React.CSSProperties = {
  ...inputStyle, background: '#f3f4f6', color: '#6b7280', cursor: 'not-allowed',
}

export default function EditModal({ row, onClose, onSaved }: Props) {
  const [desc,    setDesc]    = useState(row.description || '')
  const [tags,    setTags]    = useState<Record<string, string>>({})
  const [saving,  setSaving]  = useState(false)
  const [error,   setError]   = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchTags(row.catalog_name, row.schema_name, row.table_name)
      .then((d: { tags: Record<string, string>; description: string }) => {
        setTags(d.tags || {})
        setDesc(d.description || row.description || '')
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const handleApply = async () => {
    setSaving(true)
    setError('')
    try {
      await applyTags({
        catalog: row.catalog_name,
        schema:  row.schema_name,
        table:   row.table_name,
        description: desc,
        tags,
      })
      onSaved()
      onClose()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: '#fff', borderRadius: 10, width: 620, maxHeight: '90vh',
        overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
      }}>
        {/* Header */}
        <div style={{ padding: '18px 24px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#1B3139' }}>Edit Table Metadata</div>
            <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>
              {row.catalog_name}.{row.schema_name}.{row.table_name}
            </div>
          </div>
          <button onClick={onClose} style={{ border: 'none', background: 'none', fontSize: 20, cursor: 'pointer', color: '#6b7280' }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px 24px' }}>
          {loading && <div style={{ color: '#6b7280', fontSize: 13 }}>Loading current tags…</div>}
          {error   && <div style={{ color: '#FF3621', fontSize: 13, marginBottom: 12 }}>{error}</div>}

          {/* Locked fields */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
            {[
              { label: 'Catalog', val: row.catalog_name },
              { label: 'Schema',  val: row.schema_name },
              { label: 'Table',   val: row.table_name },
            ].map(f => (
              <div key={f.label}>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>{f.label}</label>
                <input value={f.val} readOnly style={lockedStyle} />
              </div>
            ))}
          </div>

          {/* Description */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Description</label>
            <textarea
              value={desc}
              onChange={e => setDesc(e.target.value)}
              rows={3}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </div>

          <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 10, paddingBottom: 6, borderBottom: '1px solid #e5e7eb' }}>
            Tags
          </div>

          {/* Tag fields — 2 columns */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {TAG_COLUMNS.map(col => (
              <div key={col}>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>{col}</label>
                <input
                  value={tags[col] || ''}
                  onChange={e => setTags(t => ({ ...t, [col]: e.target.value }))}
                  placeholder={`Enter ${col}…`}
                  style={inputStyle}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: '14px 24px', borderTop: '1px solid #e5e7eb', display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button onClick={onClose} style={{
            padding: '8px 20px', borderRadius: 5, border: '1px solid #d1d5db',
            background: '#fff', cursor: 'pointer', fontSize: 13, color: '#374151',
          }}>
            Cancel
          </button>
          <button
            onClick={handleApply}
            disabled={saving}
            style={{
              padding: '8px 20px', borderRadius: 5, border: 'none',
              background: saving ? '#ccc' : '#FF3621', color: '#fff',
              cursor: saving ? 'not-allowed' : 'pointer', fontSize: 13, fontWeight: 600,
            }}
          >
            {saving ? 'Applying…' : 'Apply Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
