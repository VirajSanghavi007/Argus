import React, { useState } from 'react';

export default function Investigate({ alerts, decisions, onPostDecision }) {
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [severityFilter, setSeverityFilter] = useState('all');

  const alertArray = Object.values(alerts);
  const filteredAlerts = alertArray.filter(a => {
    const matchesSearch =
      !searchTerm ||
      a.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      a.name?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSeverity = severityFilter === 'all' || a.severity === severityFilter;
    return matchesSearch && matchesSeverity;
  });

  const selectedAlert = selectedAlertId ? alerts[selectedAlertId] : null;

  return (
    <div className="view" id="view-investigate" role="tabpanel">
      <div className="inv-left">
        <div className="inv-left-head">
          <label htmlFor="inv-search" className="label-up" style={{ marginBottom: 'var(--sp-1)' }}>
            Search alerts
          </label>
          <input
            type="search"
            id="inv-search"
            placeholder="Search alerts…"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            aria-label="Filter alerts by name or ID"
          />
          <div className="inv-filter-row" id="sev-pills" role="group" aria-label="Severity filter">
            {['all', 'HIGH', 'MEDIUM', 'LOW'].map(sev => (
              <span
                key={sev}
                className={`filter-pill ${severityFilter === sev ? 'active' : ''}`}
                onClick={() => setSeverityFilter(sev)}
                role="button"
                tabIndex={0}
              >
                {sev === 'all' ? 'All' : sev}
              </span>
            ))}
          </div>
        </div>
        <div className="alert-list" id="alert-list" role="list" aria-label="Alert list">
          {filteredAlerts.length === 0 ? (
            <div style={{ padding: 'var(--sp-4)', color: 'var(--muted)' }}>No alerts match filters</div>
          ) : (
            filteredAlerts.map(alert => (
              <div
                key={alert.id}
                className={`alert-item ${selectedAlertId === alert.id ? 'active' : ''}`}
                onClick={() => setSelectedAlertId(alert.id)}
                role="option"
                aria-selected={selectedAlertId === alert.id}
                style={{
                  padding: 'var(--sp-3)',
                  borderBottom: '1px solid var(--border)',
                  cursor: 'pointer',
                  backgroundColor: selectedAlertId === alert.id ? 'var(--row-alt)' : 'transparent',
                }}
              >
                <div style={{ fontWeight: 500, marginBottom: 'var(--sp-1)' }}>{alert.name}</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)' }}>
                  {alert.patternType} • {alert.severity}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="inv-center">
        {selectedAlert ? (
          <>
            <div
              className="route-bar"
              aria-label="Transaction route"
              style={{ padding: 'var(--sp-3)', background: 'var(--surface)', borderRadius: 'var(--r)' }}
            >
              <span style={{ color: 'var(--light)', fontSize: 'var(--text-sm)', fontFamily: 'var(--mono)' }}>
                {selectedAlert.name}
              </span>
            </div>
            <div className="inv-stats-strip" aria-label="Alert statistics">
              <div className="inv-stat">
                <div className="is-label">Total Moved</div>
                <div className="is-val">{selectedAlert.totalMoved}</div>
              </div>
              <div className="inv-stat">
                <div className="is-label">Time Span</div>
                <div className="is-val">{selectedAlert.timeSpan}s</div>
              </div>
              <div className="inv-stat">
                <div className="is-label">Hops</div>
                <div className="is-val">{selectedAlert.hops}</div>
              </div>
              <div className="inv-stat">
                <div className="is-label">Confidence</div>
                <div className="is-val">{(selectedAlert.confidence * 100).toFixed(0)}%</div>
              </div>
              <div className="inv-stat">
                <div className="is-label">Pattern</div>
                <div className="is-val">{selectedAlert.patternType}</div>
              </div>
            </div>
            <div
              style={{
                padding: 'var(--sp-4)',
                background: 'var(--surface)',
                borderRadius: 'var(--r)',
                border: '1px solid var(--border)',
                minHeight: '300px',
              }}
            >
              <div style={{ color: 'var(--light)', fontSize: 'var(--text-sm)', fontFamily: 'var(--mono)' }}>
                Graph visualization would render here with Cytoscape
              </div>
            </div>
          </>
        ) : (
          <div
            style={{
              padding: 'var(--sp-5)',
              color: 'var(--light)',
              fontSize: 'var(--text-sm)',
              fontFamily: 'var(--mono)',
            }}
          >
            Select an alert to begin investigation
          </div>
        )}
      </div>

      <div className="inv-right">
        {selectedAlert && (
          <div className="ir-sec">
            <span className="label-up">Decision</span>
            <div className="dec-btns" role="group" aria-label="Decision actions">
              {['confirm', 'review', 'dismiss'].map(decision => (
                <button
                  key={decision}
                  className={`btn btn-${decision === 'confirm' ? 'green' : decision === 'review' ? 'amber' : 'red'}`}
                  onClick={() => onPostDecision(selectedAlert.id, decision, '')}
                  aria-label={`${decision === 'confirm' ? 'Confirm' : decision === 'review' ? 'Mark for review' : 'Dismiss'} alert`}
                >
                  {decision === 'confirm' ? '✓ Confirm' : decision === 'review' ? '⚠ Review' : '✗ Dismiss'}
                </button>
              ))}
            </div>
            {decisions[selectedAlert.id] && (
              <div style={{ marginTop: 'var(--sp-3)', padding: 'var(--sp-2)', background: 'var(--row-alt)', borderRadius: 'var(--r)', fontSize: 'var(--text-sm)' }}>
                <strong>Current Decision:</strong> {decisions[selectedAlert.id].decision}
                {decisions[selectedAlert.id].reason && (
                  <div style={{ color: 'var(--muted)', marginTop: 'var(--sp-1)' }}>
                    {decisions[selectedAlert.id].reason}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
