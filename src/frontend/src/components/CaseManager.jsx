import React, { useState } from 'react';

export default function CaseManager({ alerts, decisions }) {
  const [caseFilter, setCaseFilter] = useState('all');

  const alertArray = Object.values(alerts);
  const casesWithDecisions = alertArray.filter(a => decisions[a.id]).map(a => ({
    ...a,
    decision: decisions[a.id],
  }));

  const filteredCases = casesWithDecisions.filter(c => {
    if (caseFilter === 'all') return true;
    return c.decision.decision === caseFilter;
  });

  const exportCSV = () => {
    const headers = ['Alert ID', 'Pattern', 'Severity', 'Confidence', 'Total Moved', 'Source', 'Decision', 'Reason'];
    const rows = filteredCases.map(c => [
      c.id,
      c.patternType,
      c.severity,
      (c.confidence * 100).toFixed(1),
      c.totalMoved,
      c.source || 'labelled',
      c.decision.decision,
      c.decision.reason || '',
    ]);

    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cases.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="view" id="view-cases" role="tabpanel">
      <div className="cases-hdr">
        <h2>Case Manager</h2>
        <div style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
          <div className="cases-filters" id="case-filters" role="group" aria-label="Case decision filter">
            {['all', 'confirm', 'review', 'dismiss'].map(filter => (
              <span
                key={filter}
                className={`filter-pill ${caseFilter === filter ? 'active' : ''}`}
                onClick={() => setCaseFilter(filter)}
                role="button"
                tabIndex={0}
              >
                {filter === 'all' ? 'All' : filter.charAt(0).toUpperCase() + filter.slice(1)}
              </span>
            ))}
          </div>
          <button className="btn btn-ghost" onClick={exportCSV} aria-label="Export cases as CSV">
            Export CSV
          </button>
        </div>
      </div>

      <div className="table-wrap">
        {filteredCases.length === 0 ? (
          <div className="cases-empty" id="cases-empty">
            No decisions made yet. Go to Investigate to review alerts.
          </div>
        ) : (
          <table className="data-table" aria-label="Case decisions">
            <thead>
              <tr>
                <th scope="col">Alert ID</th>
                <th scope="col">Pattern</th>
                <th scope="col">Severity</th>
                <th scope="col">Confidence</th>
                <th scope="col">Total Moved</th>
                <th scope="col">Source</th>
                <th scope="col">Decision</th>
                <th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody id="cases-tbody">
              {filteredCases.map(c => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{c.patternType}</td>
                  <td>{c.severity}</td>
                  <td>{(c.confidence * 100).toFixed(1)}%</td>
                  <td>{c.totalMoved}</td>
                  <td>{c.source || 'labelled'}</td>
                  <td style={{ color: c.decision.decision === 'confirm' ? 'var(--green)' : c.decision.decision === 'review' ? 'var(--amber)' : 'var(--red)' }}>
                    {c.decision.decision.toUpperCase()}
                  </td>
                  <td>{c.decision.reason || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
