import React from 'react';

export default function Navigation({
  currentView,
  onViewChange,
  status,
  darkMode,
  onToggleDarkMode,
}) {
  const statusDot = status?.status === 'ready' ? 'active' : 'loading';
  const statusLabel = status?.status === 'ready' ? 'Ready' : 'Loading...';

  return (
    <nav aria-label="Main navigation">
      <div className="nav-brand">
        <div className="nav-title">AML Intelligence Platform</div>
        <div className="nav-sub">FUND FLOW TRACKING SYSTEM</div>
      </div>

      <div className="nav-tabs" role="tablist" aria-label="Platform views">
        {[
          { id: 'dashboard', label: 'Dashboard' },
          { id: 'investigate', label: 'Investigate' },
          { id: 'cases', label: 'Case Manager' },
          { id: 'search', label: 'Search' },
          { id: 'whitelist', label: 'Whitelist' },
        ].map(tab => (
          <button
            key={tab.id}
            className={`nav-tab ${currentView === tab.id ? 'active' : ''}`}
            onClick={() => onViewChange(tab.id)}
            role="tab"
            aria-selected={currentView === tab.id}
            aria-controls={`view-${tab.id}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="nav-status">
        <div className={`status-dot ${statusDot}`} aria-hidden="true"></div>
        <span className="status-label" role="status">
          {statusLabel}
        </span>
        <button
          id="dark-toggle"
          onClick={onToggleDarkMode}
          title="Toggle dark mode"
          aria-label="Toggle dark mode"
          style={{
            marginLeft: 'var(--sp-2)',
            background: 'none',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r)',
            padding: 'var(--sp-1) var(--sp-2)',
            cursor: 'pointer',
            fontSize: 'var(--text-base)',
            color: 'var(--muted)',
            lineHeight: 1,
            transition: 'all .15s ease',
            flexShrink: 0,
          }}
        >
          {darkMode ? '☀️' : '🌙'}
        </button>
      </div>
    </nav>
  );
}
