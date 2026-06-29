# React Frontend — Comprehensive Documentation

**Location:** `src/frontend/`  
**Technology:** React 18 + Vite + Axios  
**Build Tool:** Vite 5.0  
**Server Port:** 5173 (dev), served from backend (prod)  
**Architecture:** Single-Page Application (SPA)

---

## Overview

The React frontend is a modern, modular application that:
- Manages global application state (alerts, decisions, status, metrics)
- Provides interactive dashboards and data exploration
- Communicates with backend via centralized HTTP client
- Supports hot module reload (HMR) during development
- Builds to static files for production deployment

---

## Technology Stack

### Core Dependencies
```json
{
  "react": "^18.2.0",           // Component library
  "react-dom": "^18.2.0",       // DOM rendering
  "axios": "^1.6.0",            // HTTP client
  "chart.js": "^3.9.0",         // Charts (via vendor/)
  "cytoscape": "^3.20.0",       // Graph visualization (via vendor/)
  "recharts": "^2.0.0"          // Alternative charting
}
```

### Dev Dependencies
```json
{
  "vite": "^5.0.0",                    // Build tool
  "@vitejs/plugin-react": "^4.2.1",   // React plugin for Vite
  "eslint": "^8.50.0",                // Linting
  "@babel/plugin-proposal-class-properties": "^7.18.6"
}
```

### Build & Serve Scripts
```json
{
  "dev": "vite",                         // Dev server on :5173
  "build": "vite build",                 // Production build
  "preview": "vite preview",             // Preview production build
  "lint": "eslint src/"                  // Code linting
}
```

---

## Project Structure

```
src/frontend/
├── public/
│   ├── index.html              # React root (single div#root)
│   ├── style.css               # Global styles
│   ├── vendor/
│   │   ├── chart.min.js        # Chart.js library
│   │   ├── cytoscape.min.js    # Cytoscape library
│   │   └── cytoscape-cose.min.js
│   └── img/
│       └── logo.png            # App logo
├── src/
│   ├── index.jsx               # React entry point (ReactDOM.createRoot)
│   ├── App.jsx                 # Main app component (state management, routing)
│   ├── components/
│   │   ├── Navigation.jsx      # Header navigation & tabs
│   │   ├── Dashboard.jsx       # KPI cards, charts, summary
│   │   ├── Investigate.jsx     # Alert details, graph, timeline
│   │   ├── CaseManager.jsx     # Decisions table, CSV export
│   │   ├── Search.jsx          # Full-text search, quick filters
│   │   └── Whitelist.jsx       # Exemption management
│   └── utils/
│       └── api.js              # Centralized HTTP client
├── vite.config.js              # Vite configuration
├── package.json                # Dependencies & scripts
├── .gitignore                  # Node modules, dist, logs
└── dist/                        # Production build output (created by npm run build)
```

---

## Vite Configuration

**File:** `vite.config.js`

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api')
      },
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    minify: 'terser',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom']
        }
      }
    }
  }
})
```

**Key Features:**
- **Dev Server:** Runs on port 5173 with hot reload
- **API Proxy:** `/api` calls routed to `http://localhost:8000` during development
- **Production Build:** Tree-shaken, minified output to `dist/` folder
- **Vendor Splitting:** React/ReactDOM in separate chunk

---

## Entry Point & Bootstrap

### `src/index.jsx`
```javascript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

**Purpose:**
- Mounts React app to `<div id="root">` in `public/index.html`
- Enables hot module reload (HMR)
- Applies strict mode for development warnings

### `public/index.html`
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Argus — AML Detection</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/index.jsx"></script>
</body>
</html>
```

---

## Main Application Component

### `src/App.jsx`

**Responsibility:** Central state management, data fetching, view routing

```javascript
import React, { useEffect, useState } from 'react'
import * as api from './utils/api'
import Navigation from './components/Navigation'
import Dashboard from './components/Dashboard'
import Investigate from './components/Investigate'
import CaseManager from './components/CaseManager'
import Search from './components/Search'
import Whitelist from './components/Whitelist'

function App() {
  // ──── STATE ────
  const [currentView, setCurrentView] = useState('dashboard')
  const [alerts, setAlerts] = useState([])
  const [decisions, setDecisions] = useState({})
  const [status, setStatus] = useState({
    model_loaded: false,
    n_alerts_total: 0,
    n_alerts_after_whitelist: 0,
    pattern_breakdown: {},
    severity_breakdown: {},
    decision_summary: {}
  })
  const [mlMetrics, setMlMetrics] = useState({})
  const [loading, setLoading] = useState(true)
  const [darkMode, setDarkMode] = useState(false)

  // ──── EFFECTS ────
  useEffect(() => {
    // Initial load
    loadData()
    
    // Poll every 30 seconds
    const interval = setInterval(loadData, 30000)
    return () => clearInterval(interval)
  }, [])

  // ──── FUNCTIONS ────
  async function loadData() {
    try {
      setLoading(true)
      const [status, alerts, decisions, metrics] = await Promise.all([
        api.getStatus(),
        api.getAlerts(),
        api.getDecisions(),
        api.getMlMetrics()
      ])
      setStatus(status)
      setAlerts(alerts)
      setDecisions(decisions)
      setMlMetrics(metrics)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  async function handlePostDecision(alertId, decision, reason) {
    try {
      await api.postDecision(alertId, { decision, reason })
      await loadData()
    } catch (error) {
      console.error('Decision failed:', error)
    }
  }

  // ──── RENDER ────
  const renderView = () => {
    switch (currentView) {
      case 'dashboard': return <Dashboard status={status} alerts={alerts} />
      case 'investigate': return <Investigate alerts={alerts} decisions={decisions} onPostDecision={handlePostDecision} />
      case 'casemanager': return <CaseManager alerts={alerts} decisions={decisions} />
      case 'search': return <Search alerts={alerts} />
      case 'whitelist': return <Whitelist />
      default: return <Dashboard status={status} alerts={alerts} />
    }
  }

  return (
    <div className={`app ${darkMode ? 'dark' : ''}`}>
      <Navigation 
        currentView={currentView}
        onViewChange={setCurrentView}
        darkMode={darkMode}
        onDarkModeChange={setDarkMode}
      />
      <main>
        {loading && <div className="loader">Loading...</div>}
        {!loading && renderView()}
      </main>
    </div>
  )
}

export default App
```

**Global State:**
| Variable | Type | Purpose |
|----------|------|---------|
| `currentView` | string | Active tab (dashboard, investigate, casemanager, search, whitelist) |
| `alerts` | Array | All alerts from `/api/alerts` |
| `decisions` | Object | Map of alert_id → decision_type |
| `status` | Object | System status (counts, patterns, severities) |
| `mlMetrics` | Object | Model performance metrics |
| `loading` | Boolean | Loading state during fetch |
| `darkMode` | Boolean | Theme toggle |

**Key Functions:**
- `loadData()` — Fetch from all endpoints in parallel
- `handlePostDecision()` — Post decision, then refresh data
- `renderView()` — Switch component based on currentView

---

## Centralized HTTP Client

### `src/utils/api.js`

```javascript
const API_BASE = process.env.VITE_API_BASE || '/api'

async function request(method, endpoint, data = null) {
  const url = `${API_BASE}${endpoint}`
  const options = {
    method,
    headers: { 'Content-Type': 'application/json' }
  }
  if (data) {
    options.body = JSON.stringify(data)
  }
  
  const response = await fetch(url, options)
  if (!response.ok) {
    throw new Error(`${response.status}: ${response.statusText}`)
  }
  return response.json()
}

export const getHealth = () => request('GET', '/health')
export const getStatus = () => request('GET', '/status')
export const getAlerts = (filters = {}) => {
  const params = new URLSearchParams(filters)
  return request('GET', `/alerts?${params}`)
}
export const getAlert = (id) => request('GET', `/alerts/${id}`)
export const postDecision = (id, body) => request('POST', `/alerts/${id}/decision`, body)
export const getDecisionHistory = (id) => request('GET', `/alerts/${id}/decision/history`)
export const getDecisions = () => request('GET', '/decisions')
export const getMlMetrics = () => request('GET', '/ml-metrics')
export const getDrift = () => request('GET', '/drift')
export const getWhitelist = () => request('GET', '/whitelist')
export const addWhitelistAccount = (id, bank, reason) => 
  request('POST', '/whitelist/account', { account_id: id, bank, reason })
export const removeWhitelistAccount = (id) => 
  request('DELETE', `/whitelist/account/${id}`)
export const getSuppressed = () => request('GET', '/whitelist/suppressed')
export const scanPipeline = (maxRows = 600000) => 
  request('POST', '/scan', { max_rows: maxRows })
```

**Design Principles:**
- Centralized error handling
- Consistent request/response patterns
- Environment-based API base URL
- All endpoints documented as exports

---

## Components

### 1. Navigation Component
**File:** `src/components/Navigation.jsx`

```javascript
function Navigation({ currentView, onViewChange, darkMode, onDarkModeChange }) {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'investigate', label: 'Investigate', icon: '🔍' },
    { id: 'casemanager', label: 'Case Manager', icon: '📋' },
    { id: 'search', label: 'Search', icon: '🔎' },
    { id: 'whitelist', label: 'Whitelist', icon: '✅' }
  ]

  return (
    <header className="navigation">
      <div className="logo">
        <img src="/img/logo.png" alt="Argus" />
        <h1>Argus — AML Detection</h1>
      </div>
      <nav className="tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab ${currentView === tab.id ? 'active' : ''}`}
            onClick={() => onViewChange(tab.id)}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </nav>
      <div className="controls">
        <button 
          className="dark-mode-toggle"
          onClick={() => onDarkModeChange(!darkMode)}
        >
          {darkMode ? '☀️' : '🌙'}
        </button>
      </div>
    </header>
  )
}
```

**Props:**
- `currentView` — Active tab
- `onViewChange` — Tab change callback
- `darkMode` — Current theme
- `onDarkModeChange` — Theme toggle callback

**Rendered Elements:**
- Logo + app title
- Tab buttons (5 tabs)
- Dark mode toggle

---

### 2. Dashboard Component
**File:** `src/components/Dashboard.jsx`

```javascript
function Dashboard({ status, alerts }) {
  const stats = [
    { title: 'Total Alerts', value: status.n_alerts_after_whitelist, icon: '🚨' },
    { title: 'Money Flagged', value: `$${totalAmount(alerts)}M`, icon: '💰' },
    { title: 'High Severity', value: status.severity_breakdown?.HIGH || 0, icon: '⚠️' },
    { title: 'Decisions Made', value: Object.values(status.decision_summary || {}).reduce((a, b) => a + b, 0), icon: '✓' }
  ]

  return (
    <div className="dashboard">
      <div className="stat-cards">
        {stats.map(stat => (
          <div key={stat.title} className="stat-card">
            <div className="stat-value">{stat.value}</div>
            <div className="stat-title">{stat.title}</div>
          </div>
        ))}
      </div>
      
      <div className="charts">
        <PatternBreakdownChart patterns={status.pattern_breakdown} />
        <MostInvolvedBanksChart alerts={alerts} />
      </div>
      
      <div className="decision-summary">
        <h3>Decision Summary</h3>
        <div className="summary-grid">
          <div className="summary-item">Confirmed: {status.decision_summary?.confirmed || 0}</div>
          <div className="summary-item">Reviewed: {status.decision_summary?.reviewed || 0}</div>
          <div className="summary-item">Dismissed: {status.decision_summary?.dismissed || 0}</div>
          <div className="summary-item">Pending: {status.decision_summary?.pending || 0}</div>
        </div>
      </div>
    </div>
  )
}
```

**Features:**
- 4 stat cards (KPIs)
- Pattern breakdown doughnut chart (Chart.js)
- Most involved banks bar chart
- Decision summary grid

---

### 3. Investigate Component
**File:** `src/components/Investigate.jsx`

```javascript
function Investigate({ alerts, decisions, onPostDecision }) {
  const [selectedAlertId, setSelectedAlertId] = useState(null)
  const [filterSeverity, setFilterSeverity] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')

  const filtered = alerts.filter(a => {
    if (filterSeverity && a.severity !== filterSeverity) return false
    if (searchTerm && !a.id.toLowerCase().includes(searchTerm)) return false
    return true
  })

  const selectedAlert = alerts.find(a => a.id === selectedAlertId)

  return (
    <div className="investigate">
      <aside className="sidebar">
        <input
          type="text"
          placeholder="Search alerts..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
        />
        <div className="filters">
          <button 
            className={!filterSeverity ? 'active' : ''}
            onClick={() => setFilterSeverity(null)}
          >
            All
          </button>
          {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(sev => (
            <button
              key={sev}
              className={filterSeverity === sev ? 'active' : ''}
              onClick={() => setFilterSeverity(sev)}
            >
              {sev}
            </button>
          ))}
        </div>
        <div className="alert-list">
          {filtered.map(alert => (
            <div
              key={alert.id}
              className={`alert-item ${selectedAlertId === alert.id ? 'active' : ''}`}
              onClick={() => setSelectedAlertId(alert.id)}
            >
              <div className={`severity ${alert.severity}`}>{alert.severity}</div>
              <div className="pattern">{alert.pattern_type}</div>
              <div className="confidence">{(alert.confidence * 100).toFixed(0)}%</div>
            </div>
          ))}
        </div>
      </aside>

      <div className="details">
        {selectedAlert ? (
          <>
            <h3>{selectedAlert.id}</h3>
            <div className="alert-stats">
              <div>Total Moved: ${selectedAlert.total_amount}</div>
              <div>Time Span: {selectedAlert.time_span_seconds}s</div>
              <div>Hops: {selectedAlert.nodes.length}</div>
              <div>Confidence: {(selectedAlert.confidence * 100).toFixed(1)}%</div>
              <div>Pattern: {selectedAlert.pattern_type}</div>
            </div>
            <h4>Nodes (Accounts)</h4>
            <div className="nodes">
              {selectedAlert.nodes.map(node => (
                <div key={node.node_id} className="node">
                  {node.node_id} @ {node.bank} ({node.role})
                </div>
              ))}
            </div>
            <h4>Edges (Transactions)</h4>
            <div className="edges">
              {selectedAlert.edges.map((edge, i) => (
                <div key={i} className="edge">
                  {edge.src} → {edge.dst}: ${edge.amount} ({edge.timestamp})
                </div>
              ))}
            </div>
            <div id="cytoscape" style={{ height: '400px' }}></div>
          </>
        ) : (
          <p>Select an alert to view details</p>
        )}
      </div>

      <aside className="decisions">
        {selectedAlert && (
          <>
            <h3>Decision</h3>
            <div className="decision-buttons">
              {['confirm', 'review', 'dismiss'].map(decision => (
                <button
                  key={decision}
                  className={`decision-btn ${decisions[selectedAlertId] === decision ? 'active' : ''}`}
                  onClick={() => onPostDecision(selectedAlertId, decision, `Analyst decision: ${decision}`)}
                >
                  {decision.toUpperCase()}
                </button>
              ))}
            </div>
            {decisions[selectedAlertId] && (
              <div className="decision-status">
                Current: <strong>{decisions[selectedAlertId]}</strong>
              </div>
            )}
          </>
        )}
      </aside>
    </div>
  )
}
```

**Features:**
- Searchable alert sidebar
- Severity filter buttons
- Alert detail view (stats, nodes, edges)
- Cytoscape graph placeholder (to be wired up)
- Decision buttons (confirm, review, dismiss)
- Current decision status

---

### 4. CaseManager Component
**File:** `src/components/CaseManager.jsx`

```javascript
function CaseManager({ alerts, decisions }) {
  const [filterDecision, setFilterDecision] = useState('all')

  const filtered = alerts.filter(alert => {
    if (filterDecision === 'all') return true
    const decision = decisions[alert.id]
    return decision === filterDecision
  })

  function exportCSV() {
    const csv = [
      ['ID', 'Pattern', 'Severity', 'Confidence', 'Total Moved', 'Source', 'Decision'],
      ...filtered.map(alert => [
        alert.id,
        alert.pattern_type,
        alert.severity,
        alert.confidence.toFixed(3),
        alert.total_amount,
        alert.source,
        decisions[alert.id] || 'PENDING'
      ])
    ]
    const csvString = csv.map(row => row.join(',')).join('\n')
    const blob = new Blob([csvString], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `argus-cases-${new Date().toISOString()}.csv`
    a.click()
  }

  return (
    <div className="casemanager">
      <div className="controls">
        <button onClick={() => setFilterDecision('all')} className={filterDecision === 'all' ? 'active' : ''}>All</button>
        <button onClick={() => setFilterDecision('confirm')} className={filterDecision === 'confirm' ? 'active' : ''}>Confirmed</button>
        <button onClick={() => setFilterDecision('review')} className={filterDecision === 'review' ? 'active' : ''}>Reviewed</button>
        <button onClick={() => setFilterDecision('dismiss')} className={filterDecision === 'dismiss' ? 'active' : ''}>Dismissed</button>
        <button onClick={exportCSV} className="export-btn">📥 Export CSV</button>
      </div>
      
      <table className="cases-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Pattern</th>
            <th>Severity</th>
            <th>Confidence</th>
            <th>Total Moved</th>
            <th>Source</th>
            <th>Decision</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(alert => (
            <tr key={alert.id}>
              <td className="alert-id">{alert.id.slice(0, 8)}...</td>
              <td>{alert.pattern_type}</td>
              <td className={`severity ${alert.severity}`}>{alert.severity}</td>
              <td>{(alert.confidence * 100).toFixed(1)}%</td>
              <td>${alert.total_amount.toLocaleString()}</td>
              <td>{alert.source}</td>
              <td className="decision">{decisions[alert.id] || '⏳ Pending'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

**Features:**
- Filter by decision type (All, Confirmed, Reviewed, Dismissed)
- Data table with 7 columns
- CSV export functionality

---

### 5. Search Component
**File:** `src/components/Search.jsx`

```javascript
function Search({ alerts }) {
  const [searchTerm, setSearchTerm] = useState('')
  const [filterPattern, setFilterPattern] = useState(null)

  const filtered = alerts.filter(alert => {
    if (searchTerm && !alert.id.toLowerCase().includes(searchTerm.toLowerCase())) return false
    if (filterPattern && alert.pattern_type !== filterPattern) return false
    return true
  })

  return (
    <div className="search">
      <div className="search-controls">
        <input
          type="text"
          placeholder="Search by account, bank, or pattern..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className="search-input"
        />
      </div>
      
      <div className="quick-filters">
        {['FAN_OUT', 'FAN_IN', 'CYCLE', 'SCATTER_GATHER', 'BIPARTITE'].map(pattern => (
          <button
            key={pattern}
            className={`pattern-btn ${filterPattern === pattern ? 'active' : ''}`}
            onClick={() => setFilterPattern(filterPattern === pattern ? null : pattern)}
          >
            {pattern}
          </button>
        ))}
      </div>
      
      <div className="results-grid">
        {filtered.map(alert => (
          <div key={alert.id} className="result-card">
            <div className="result-header">
              <div className={`severity ${alert.severity}`}>{alert.severity}</div>
              <div className="pattern">{alert.pattern_type}</div>
            </div>
            <div className="result-body">
              <div className="stat">Confidence: <strong>{(alert.confidence * 100).toFixed(1)}%</strong></div>
              <div className="stat">Total Moved: <strong>${alert.total_amount}</strong></div>
              <div className="stat">Accounts: <strong>{alert.nodes.length}</strong></div>
              <div className="stat">Transactions: <strong>{alert.edges.length}</strong></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

**Features:**
- Text search across alerts
- Quick filter buttons (pattern types)
- Results grid display

---

### 6. Whitelist Component
**File:** `src/components/Whitelist.jsx`

```javascript
function Whitelist() {
  const [whitelist, setWhitelist] = useState({
    exempt_accounts: [],
    exempt_banks: []
  })
  const [newAccountId, setNewAccountId] = useState('')
  const [newBank, setNewBank] = useState('')
  const [suppressed, setSuppressed] = useState([])

  useEffect(() => {
    loadWhitelist()
  }, [])

  async function loadWhitelist() {
    const [wl, supp] = await Promise.all([
      api.getWhitelist(),
      api.getSuppressed()
    ])
    setWhitelist(wl)
    setSuppressed(supp)
  }

  async function handleAddAccount() {
    if (!newAccountId || !newBank) return
    await api.addWhitelistAccount(newAccountId, newBank, 'User added')
    setNewAccountId('')
    setNewBank('')
    await loadWhitelist()
  }

  async function handleRemoveAccount(id) {
    await api.removeWhitelistAccount(id)
    await loadWhitelist()
  }

  return (
    <div className="whitelist">
      <section className="form-section">
        <h3>Add Account to Whitelist</h3>
        <div className="form">
          <input
            type="text"
            placeholder="Account ID"
            value={newAccountId}
            onChange={e => setNewAccountId(e.target.value)}
          />
          <input
            type="text"
            placeholder="Bank Name"
            value={newBank}
            onChange={e => setNewBank(e.target.value)}
          />
          <button onClick={handleAddAccount}>Add to Whitelist</button>
        </div>
      </section>

      <section>
        <h3>Exempt Accounts ({whitelist.exempt_accounts.length})</h3>
        <div className="exempt-list">
          {whitelist.exempt_accounts.map(account => (
            <div key={account.id} className="exempt-item">
              <div>{account.id} @ {account.bank}</div>
              <button onClick={() => handleRemoveAccount(account.id)}>Remove</button>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3>Exempt Banks ({whitelist.exempt_banks.length})</h3>
        <div className="bank-list">
          {whitelist.exempt_banks.map(bank => (
            <div key={bank} className="bank-item">{bank}</div>
          ))}
        </div>
      </section>

      <section>
        <h3>Suppressed Alerts ({suppressed.length})</h3>
        <table className="suppressed-table">
          <thead>
            <tr><th>Alert ID</th><th>Reason</th></tr>
          </thead>
          <tbody>
            {suppressed.map(item => (
              <tr key={item.alert_id}>
                <td>{item.alert_id.slice(0, 8)}...</td>
                <td>{item.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
```

**Features:**
- Form to add accounts to whitelist
- Display exempt accounts/banks
- Show suppressed alerts and reasons
- Remove account from whitelist

---

## Styling

**File:** `public/style.css`

Global styles follow a consistent design:
- Color scheme: professional (dark navy, accent orange)
- Responsive layout (flexbox, grid)
- Dark mode support (CSS variables)
- Card-based UI for alerts, metrics
- Charts and visualizations with vendor libraries

```css
:root {
  --primary: #1e3a5f;
  --accent: #ff6b35;
  --text: #333;
  --light: #f5f5f5;
  --border: #ddd;
}

.dark {
  --primary: #0a1f3a;
  --accent: #ff8c42;
  --text: #f0f0f0;
  --light: #1a1a1a;
  --border: #444;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: var(--text);
  background: var(--light);
}

.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

main {
  flex: 1;
  overflow: auto;
  padding: 20px;
}
```

---

## Development Workflow

### Local Development with Hot Reload
```bash
# Terminal 1: Backend API
python scripts/serve.py  # Runs on :8000

# Terminal 2: Frontend dev server
cd src/frontend
npm install  # First time only
npm run dev  # Runs on :5173
```

Visit `http://localhost:5173` — changes to React files auto-reload

### Production Build
```bash
cd src/frontend
npm run build  # Creates dist/ folder
# Backend will serve dist/ when FRONTEND_DIST exists
```

---

## State Management Pattern

This frontend uses a simple **lifted state** pattern:
1. **App.jsx** owns global state (alerts, decisions, status, etc.)
2. Components accept state via **props**
3. Components call **prop callbacks** to update state
4. App calls **api.js** functions to persist changes

```
App (global state)
  ├─ Dashboard (read-only: status, alerts)
  ├─ Investigate (read: alerts, decisions; write: onPostDecision)
  ├─ CaseManager (read: alerts, decisions)
  ├─ Search (read: alerts)
  └─ Whitelist (write: onAddAccount, onRemoveAccount)
```

---

## Testing Example

```javascript
// src/components/__tests__/Dashboard.test.jsx
import { render, screen } from '@testing-library/react'
import Dashboard from '../Dashboard'

test('renders stat cards', () => {
  const status = {
    n_alerts_after_whitelist: 42,
    severity_breakdown: { HIGH: 18 },
    decision_summary: { confirmed: 10, reviewed: 8, dismissed: 5, pending: 19 }
  }
  render(<Dashboard status={status} alerts={[]} />)
  
  expect(screen.getByText('42')).toBeInTheDocument()
  expect(screen.getByText('Total Alerts')).toBeInTheDocument()
})
```

---

## Performance Optimization (Future)

- [ ] Memoize components: `React.memo(Dashboard)`
- [ ] Lazy load routes: `React.lazy(() => import('./Dashboard'))`
- [ ] Virtualize long lists (react-window)
- [ ] Debounce search input
- [ ] Cache API responses (stale-while-revalidate)

---

**End of React Frontend Documentation**
