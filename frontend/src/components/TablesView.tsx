import React, { useEffect, useState, useCallback } from 'react'
import { fetchTables, fetchSchemas } from '../api'
import EditModal from './EditModal'

interface SchemaEntry { catalog: string; schema: string }
type Row = Record<string, string>

const cellStyle: React.CSSProperties = {
  padding: '10px 12px', fontSize: 12, color: '#374151',
  borderBottom: '1px solid #f3f4f6', maxWidth: 180,
  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
}

const headStyle: React.CSSProperties = {
  padding: '10px 12px', fontSize: 11, fontWeight: 600, color: '#6b7280',
  background: '#f9fafb', borderBottom: '1px solid #e5e7eb', textAlign: 'left',
  whiteSpace: 'nowrap',
}

const filterHeadStyle: React.CSSProperties = {
  padding: '4px 8px', background: '#f9fafb',
  borderBottom: '2px solid #e5e7eb',
}

const filterSelectStyle: React.CSSProperties = {
  width: '100%', padding: '4px 6px', fontSize: 11, borderRadius: 4,
  border: '1px solid #d1d5db', color: '#374151', background: '#fff',
}

export default function TablesView({ onOpenSettings }: { onOpenSettings: () => void }) {
  const [schemas,         setSchemas]         = useState<SchemaEntry[]>([])
  const [schemasLoaded,   setSchemasLoaded]   = useState(false)
  const [catalog,         setCatalog]         = useState('')
  const [schema,          setSchema]          = useState('')
  const [rows,            setRows]            = useState<Row[]>([])
  const [loading,         setLoading]         = useState(false)
  const [error,           setError]           = useState('')
  const [editRow,         setEditRow]         = useState<Row | null>(null)
  const [search,          setSearch]          = useState('')
  const [filterDomain,    setFilterDomain]    = useState('')
  const [filterSubdomain, setFilterSubdomain] = useState('')

  useEffect(() => {
    fetchSchemas().then((s: SchemaEntry[]) => {
      setSchemas(s)
      setSchemasLoaded(true)
      // Default is "All" — do not auto-select the first entry
    })
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    setFilterDomain('')
    setFilterSubdomain('')
    fetchTables(catalog || undefined, schema || undefined)
      .then(setRows)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [catalog, schema])

  useEffect(() => { if (schemasLoaded) load() }, [catalog, schema, schemasLoaded])

  if (schemasLoaded && schemas.length === 0) return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', minHeight: '65vh', gap: 20, padding: 40,
    }}>
      <div style={{ fontSize: 52, lineHeight: 1 }}>⚙</div>
      <div style={{ fontSize: 28, fontWeight: 800, color: '#1B3139', textAlign: 'center' }}>
        No schemas configured
      </div>
      <div style={{ fontSize: 15, color: '#6b7280', textAlign: 'center', maxWidth: 420, lineHeight: 1.6 }}>
        Add at least one catalog and schema in Configure settings to start browsing and governing your tables.
      </div>
      <button
        onClick={onOpenSettings}
        style={{
          marginTop: 8, padding: '12px 32px', borderRadius: 6, border: 'none',
          background: '#FF3621', color: '#fff', fontSize: 15, fontWeight: 700,
          cursor: 'pointer',
        }}
      >
        Open Configure
      </button>
    </div>
  )

  const catalogs         = [...new Set(schemas.map(s => s.catalog))]
  const schemaCandidates = schemas.filter(s => !catalog || s.catalog === catalog).map(s => s.schema)

  // Unique values for column header filters
  const domainOptions    = [...new Set(rows.map(r => r['Domain']).filter(Boolean))].sort()
  const subdomainOptions = [...new Set(rows.map(r => r['Subdomain']).filter(Boolean))].sort()

  const displayed = rows.filter(r => {
    if (filterDomain    && r['Domain']    !== filterDomain)    return false
    if (filterSubdomain && r['Subdomain'] !== filterSubdomain) return false
    if (search && !Object.values(r).some(v => v?.toLowerCase().includes(search.toLowerCase()))) return false
    return true
  })

  const VISIBLE_COLS: [string, string][] = [
    ['catalog_name',    'Catalog'],
    ['schema_name',     'Schema'],
    ['table_name',      'Table'],
    ['description',     'Description'],
    ['Domain',          'Domain'],
    ['Subdomain',       'Subdomain'],
    ['DataClass',       'DataClass'],
    ['RetentionPeriod', 'Retention'],
  ]

  return (
    <div style={{ padding: '24px 32px' }}>
      {/* Top filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          value={catalog}
          onChange={e => { setCatalog(e.target.value); setSchema('') }}
          style={{ padding: '7px 12px', borderRadius: 5, border: '1px solid #d1d5db', fontSize: 13, color: '#374151' }}
        >
          <option value="">All Catalogs</option>
          {catalogs.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          value={schema}
          onChange={e => setSchema(e.target.value)}
          style={{ padding: '7px 12px', borderRadius: 5, border: '1px solid #d1d5db', fontSize: 13, color: '#374151' }}
        >
          <option value="">All Schemas</option>
          {schemaCandidates.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search…"
          style={{ padding: '7px 12px', borderRadius: 5, border: '1px solid #d1d5db', fontSize: 13, color: '#374151', width: 200 }}
        />
        <span style={{ fontSize: 12, color: '#9ca3af', marginLeft: 'auto' }}>
          {displayed.length} table{displayed.length !== 1 ? 's' : ''}
        </span>
      </div>

      {error   && <div style={{ color: '#FF3621', fontSize: 13, marginBottom: 12 }}>{error}</div>}
      {loading && <div style={{ color: '#6b7280', fontSize: 13 }}>Loading tables…</div>}

      {!loading && (
        <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              {/* Column labels */}
              <tr>
                {VISIBLE_COLS.map(([, label]) => (
                  <th key={label} style={headStyle}>{label}</th>
                ))}
                <th style={{ ...headStyle, width: 70 }}>Action</th>
              </tr>
              {/* Column filters row — Domain and Subdomain only */}
              <tr>
                {VISIBLE_COLS.map(([key]) => (
                  <th key={key} style={filterHeadStyle}>
                    {key === 'Domain' && (
                      <select
                        value={filterDomain}
                        onChange={e => setFilterDomain(e.target.value)}
                        style={filterSelectStyle}
                      >
                        <option value="">All</option>
                        {domainOptions.map(d => <option key={d} value={d}>{d}</option>)}
                      </select>
                    )}
                    {key === 'Subdomain' && (
                      <select
                        value={filterSubdomain}
                        onChange={e => setFilterSubdomain(e.target.value)}
                        style={filterSelectStyle}
                      >
                        <option value="">All</option>
                        {subdomainOptions.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    )}
                  </th>
                ))}
                <th style={filterHeadStyle} />
              </tr>
            </thead>
            <tbody>
              {displayed.length === 0 && (
                <tr>
                  <td colSpan={VISIBLE_COLS.length + 1} style={{ ...cellStyle, textAlign: 'center', color: '#9ca3af' }}>
                    No tables found
                  </td>
                </tr>
              )}
              {displayed.map((row, i) => (
                <tr
                  key={i}
                  style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#fff7f5')}
                  onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? '#fff' : '#fafafa')}
                >
                  {VISIBLE_COLS.map(([key]) => (
                    <td key={key} style={cellStyle} title={row[key] || ''}>
                      {row[key] || <span style={{ color: '#d1d5db' }}>—</span>}
                    </td>
                  ))}
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    <button
                      onClick={() => setEditRow(row)}
                      style={{
                        padding: '4px 12px', borderRadius: 4, border: '1px solid #FF3621',
                        background: '#fff', color: '#FF3621', fontSize: 11, cursor: 'pointer',
                        fontWeight: 600,
                      }}
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editRow && (
        <EditModal
          row={editRow}
          onClose={() => setEditRow(null)}
          onSaved={load}
        />
      )}
    </div>
  )
}
