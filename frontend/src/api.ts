const BASE = ''

export async function fetchOverview(catalog?: string, schema?: string) {
  const params = new URLSearchParams()
  if (catalog) params.set('catalog', catalog)
  if (schema)  params.set('schema', schema)
  const qs = params.toString()
  const res = await fetch(`${BASE}/api/overview${qs ? '?' + qs : ''}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchTables(catalog?: string, schema?: string) {
  const params = new URLSearchParams()
  if (catalog) params.set('catalog', catalog)
  if (schema)  params.set('schema', schema)
  const res = await fetch(`${BASE}/api/tables?${params}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchTags(catalog: string, schema: string, table: string) {
  const res = await fetch(`${BASE}/api/tags/${catalog}/${schema}/${table}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function applyTags(payload: {
  catalog: string; schema: string; table: string
  description: string; tags: Record<string, string>
}) {
  const res = await fetch(`${BASE}/api/apply-tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchSchemas() {
  const res = await fetch(`${BASE}/api/schemas`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchConfig() {
  const res = await fetch(`${BASE}/api/config`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function saveConfig(payload: {
  schemas:     { catalog: string; schema: string }[]
  tag_columns: string[]
  exceptions:  { catalog: string; schema: string; table: string }[]
}): Promise<{ status: string; grants: {sql: string; status: string; error?: string}[]; grants_failed: boolean }> {
  const res = await fetch(`${BASE}/api/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
