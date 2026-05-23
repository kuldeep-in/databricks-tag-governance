import React, { useEffect, useState, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { fetchOverview, fetchSchemas } from '../api'

const COLORS = ['#FF3621', '#00A972', '#FFAB00', '#1B3139', '#8BCAE7', '#AB4057', '#99DDB4', '#FCA4A1']

interface SchemaEntry { catalog: string; schema: string }

interface OverviewData {
  total_catalogs: number
  total_schemas:  number
  total_tables:   number
  fully_tagged:   number
  no_domain:      number
  no_subdomain:   number
  by_domain:    { domain:    string; count: number }[]
  by_subdomain: { subdomain: string; count: number }[]
  by_dataclass: { data_class: string; count: number }[]
}

const KpiCard = ({
  title, value, sub, accent,
}: {
  title: string; value: number | string; sub?: string; accent?: string
}) => (
  <div style={{
    background: '#fff', borderRadius: 8, padding: '18px 22px',
    boxShadow: '0 1px 4px rgba(0,0,0,0.08)', flex: 1, minWidth: 150,
    borderTop: `3px solid ${accent || '#1B3139'}`,
  }}>
    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>{title}</div>
    <div style={{ fontSize: 30, fontWeight: 700, color: '#1B3139' }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 3 }}>{sub}</div>}
  </div>
)

const selectStyle: React.CSSProperties = {
  padding: '7px 12px', borderRadius: 5, border: '1px solid #d1d5db',
  fontSize: 13, color: '#374151', background: '#fff',
}

export default function Overview({ onOpenSettings }: { onOpenSettings: () => void }) {
  const [schemas,       setSchemas]       = useState<SchemaEntry[]>([])
  const [schemasLoaded, setSchemasLoaded] = useState(false)
  const [catalog,       setCatalog]       = useState('')
  const [schema,        setSchema]        = useState('')
  const [data,          setData]          = useState<OverviewData | null>(null)
  const [loading,       setLoading]       = useState(true)
  const [error,         setError]         = useState('')

  useEffect(() => {
    fetchSchemas().then(s => { setSchemas(s); setSchemasLoaded(true) })
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    fetchOverview(catalog || undefined, schema || undefined)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [catalog, schema])

  useEffect(() => { load() }, [catalog, schema])

  const catalogs          = [...new Set(schemas.map(s => s.catalog))]
  const schemaCandidates  = schemas.filter(s => !catalog || s.catalog === catalog).map(s => s.schema)

  // Use backend's not_configured flag — don't check schemas.length here because
  // schemas loads asynchronously and may be empty before fetchSchemas() resolves,
  // causing a false "not configured" flash on first render.
  const notConfigured = !loading && schemasLoaded && (data as any)?.not_configured

  if (notConfigured) return (
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
          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
        }}
      >
        Open Configure
      </button>
    </div>
  )

  if (error) return <div style={{ padding: 40, color: '#FF3621' }}>Error: {error}</div>

  const tagged_pct = data && data.total_tables
    ? Math.round((data.fully_tagged / data.total_tables) * 100)
    : 0

  return (
    <div style={{ padding: '24px 32px' }}>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: '#6b7280', fontWeight: 500 }}>Filter:</span>
        <select
          value={catalog}
          onChange={e => { setCatalog(e.target.value); setSchema('') }}
          style={selectStyle}
        >
          <option value="">All Catalogs</option>
          {catalogs.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          value={schema}
          onChange={e => setSchema(e.target.value)}
          style={selectStyle}
        >
          <option value="">All Schemas</option>
          {schemaCandidates.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        {(catalog || schema) && (
          <button
            onClick={() => { setCatalog(''); setSchema('') }}
            style={{ ...selectStyle, border: '1px solid #FF3621', color: '#FF3621', cursor: 'pointer' }}
          >
            Clear
          </button>
        )}
        {loading && <span style={{ fontSize: 12, color: '#9ca3af' }}>Loading…</span>}
      </div>

      {data && (
        <>
          {/* KPI Row — 6 cards */}
          <div style={{ display: 'flex', gap: 14, marginBottom: 28, flexWrap: 'wrap' }}>
            <KpiCard title="Total Catalogs"    value={data.total_catalogs}  accent="#1B3139" />
            <KpiCard title="Total Schemas"     value={data.total_schemas}   accent="#1B3139" />
            <KpiCard title="Total Tables"      value={data.total_tables}    accent="#1B3139" />
            <KpiCard title="Fully Tagged"      value={data.fully_tagged}    sub={`${tagged_pct}% of total`} accent="#00A972" />
            <KpiCard title="Missing Domain"    value={data.no_domain}       sub="tables without Domain tag"    accent="#FF3621" />
            <KpiCard title="Missing Subdomain" value={data.no_subdomain}    sub="tables without Subdomain tag" accent="#FFAB00" />
          </div>

          {/* Charts */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 22 }}>
            {/* By Domain */}
            <div style={{ background: '#fff', borderRadius: 8, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
              <h3 style={{ fontSize: 13, fontWeight: 600, color: '#1B3139', marginBottom: 14 }}>Tables by Domain</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data.by_domain} layout="vertical" margin={{ left: 10, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                  <YAxis dataKey="domain" type="category" tick={{ fontSize: 11 }} width={75} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#FF3621" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* By Subdomain */}
            <div style={{ background: '#fff', borderRadius: 8, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
              <h3 style={{ fontSize: 13, fontWeight: 600, color: '#1B3139', marginBottom: 14 }}>Tables by Subdomain</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data.by_subdomain} layout="vertical" margin={{ left: 10, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                  <YAxis dataKey="subdomain" type="category" tick={{ fontSize: 11 }} width={90} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#00A972" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* DataClass Pie */}
            <div style={{ background: '#fff', borderRadius: 8, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
              <h3 style={{ fontSize: 13, fontWeight: 600, color: '#1B3139', marginBottom: 14 }}>DataClass Distribution</h3>
              {data.by_dataclass.length === 0 ? (
                <div style={{
                  height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#9ca3af', fontSize: 13,
                }}>
                  No DataClass tags applied yet
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={data.by_dataclass}
                      dataKey="count"
                      nameKey="data_class"
                      cx="50%" cy="45%"
                      outerRadius={72}
                      label={({ percent }) =>
                        percent > 0.06 ? `${(percent * 100).toFixed(0)}%` : ''
                      }
                      labelLine={false}
                    >
                      {data.by_dataclass.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Legend
                      wrapperStyle={{ fontSize: 11 }}
                      formatter={(_value, entry: any) =>
                        `${entry.payload.data_class} (${entry.payload.count})`
                      }
                    />
                    <Tooltip formatter={(val, _name, props) => [val, props.payload.data_class]} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
