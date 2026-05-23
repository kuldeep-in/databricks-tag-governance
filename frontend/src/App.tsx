import React, { useState, useCallback } from 'react'
import Overview   from './components/Overview'
import TablesView from './components/TablesView'
import Settings   from './components/Settings'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'tables',   label: 'Tables'   },
]

const GearIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
)

export default function App() {
  const [activeTab,    setActiveTab]    = useState('overview')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [configVer,    setConfigVer]    = useState(0)   // bumped after config save → children re-fetch

  const handleConfigSaved = useCallback(() => {
    setConfigVer(v => v + 1)
    setSettingsOpen(false)
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: '#f5f6f7' }}>
      {/* Top nav */}
      <div style={{ background: '#1B3139', padding: '0 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 0' }}>
            <div style={{ width: 28, height: 28, background: '#FF3621', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: '#fff', fontWeight: 900, fontSize: 14 }}>D</span>
            </div>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 15 }}>UC Tag Governance</span>
          </div>

          {/* Main tabs */}
          <div style={{ display: 'flex', gap: 4 }}>
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); setSettingsOpen(false) }}
                style={{
                  padding: '18px 20px', border: 'none', background: 'none', cursor: 'pointer',
                  fontSize: 13, fontWeight: 500,
                  color: (!settingsOpen && activeTab === tab.id) ? '#FF3621' : '#9ca3af',
                  borderBottom: (!settingsOpen && activeTab === tab.id) ? '3px solid #FF3621' : '3px solid transparent',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Gear button */}
        <button
          onClick={() => setSettingsOpen(s => !s)}
          title="Configuration"
          style={{
            background: settingsOpen ? 'rgba(255,255,255,0.12)' : 'none',
            border: settingsOpen ? '1px solid rgba(255,255,255,0.25)' : '1px solid transparent',
            borderRadius: 6, color: settingsOpen ? '#fff' : '#9ca3af',
            cursor: 'pointer', padding: '7px 10px', display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          <GearIcon />
          <span style={{ fontSize: 12, fontWeight: 500 }}>Configure</span>
        </button>
      </div>

      {/* Sub-header */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e5e7eb', padding: '10px 32px' }}>
        <div style={{ fontSize: 12, color: '#6b7280' }}>
          {settingsOpen
            ? 'Configure scanned schemas, tag names, and table exceptions'
            : 'Unity Catalog · Tag Governance'}
        </div>
      </div>

      {/* Content */}
      {settingsOpen
        ? <Settings onSaved={handleConfigSaved} />
        : activeTab === 'overview'
          ? <Overview   key={`ov-${configVer}`} onOpenSettings={() => setSettingsOpen(true)} />
          : <TablesView key={`tv-${configVer}`} onOpenSettings={() => setSettingsOpen(true)} />
      }
    </div>
  )
}
