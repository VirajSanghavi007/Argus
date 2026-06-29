import React, { useState } from 'react';

export default function Search({ alerts }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [patternFilter, setPatternFilter] = useState(null);

  const alertArray = Object.values(alerts);
  const filteredAlerts = alertArray.filter(a => {
    const matchesSearch =
      !searchTerm ||
      a.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      a.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      a.nodes?.some(n => n.id?.toLowerCase().includes(searchTerm.toLowerCase())) ||
      a.nodes?.some(n => n.bank?.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesPattern = !patternFilter || a.patternType === patternFilter;

    return matchesSearch && matchesPattern;
  });

  const patterns = ['FAN_OUT', 'FAN_IN', 'CYCLE', 'SCATTER_GATHER', 'BIPARTITE'];

  return (
    <div className="view" id="view-search" role="tabpanel">
      <div className="search-hdr">
        <h2>Search Alerts</h2>
      </div>

      <div className="search-box">
        <label htmlFor="search-inp" className="sr-only">
          Search alerts
        </label>
        <input
          type="text"
          id="search-inp"
          placeholder="Search by account ID, bank, or pattern…"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          aria-label="Search alerts by account, bank, or pattern"
        />
        <button className="btn btn-blue" aria-label="Search">
          Search
        </button>
      </div>

      <div className="quick-filters" role="group" aria-label="Quick pattern filters">
        {patterns.map(pattern => (
          <span
            key={pattern}
            className={`filter-pill blue-pill ${patternFilter === pattern ? 'active' : ''}`}
            onClick={() => setPatternFilter(patternFilter === pattern ? null : pattern)}
            role="button"
            tabIndex={0}
          >
            {pattern}
          </span>
        ))}
      </div>

      <div className="search-results-grid" id="search-results" aria-label="Search results">
        {filteredAlerts.length === 0 ? (
          <div className="search-empty">No alerts match your search criteria.</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 'var(--sp-4)' }}>
            {filteredAlerts.map(alert => (
              <div
                key={alert.id}
                style={{
                  padding: 'var(--sp-4)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--r)',
                  background: 'var(--surface)',
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 'var(--sp-2)' }}>{alert.name}</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--sp-2)' }}>
                  <div>{alert.patternType}</div>
                  <div>{alert.severity} severity</div>
                  <div>{(alert.confidence * 100).toFixed(0)}% confidence</div>
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--light)', marginBottom: 'var(--sp-2)' }}>
                  {alert.node_count} nodes • {alert.txn_count} transactions
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
                  ID: {alert.id}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
