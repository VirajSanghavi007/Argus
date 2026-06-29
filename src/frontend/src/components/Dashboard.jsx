import React, { useEffect, useRef } from 'react';

export default function Dashboard({ alerts, decisions, status, mlMetrics }) {
  const chartDonutRef = useRef(null);
  const chartBanksRef = useRef(null);
  const chartTimelineRef = useRef(null);

  const alertArray = Object.values(alerts);
  const highSeverityCount = alertArray.filter(a => a.severity === 'HIGH').length;
  const decisionCount = Object.keys(decisions).length;
  const totalMoved = alertArray.reduce((sum, a) => {
    const val = parseFloat(a.totalMoved?.toString().replace(/[^0-9.-]/g, '') || 0);
    return sum + (isNaN(val) ? 0 : val);
  }, 0);

  // Pattern breakdown for donut chart
  const patternCounts = {};
  alertArray.forEach(a => {
    const pattern = a.patternType || 'Unknown';
    patternCounts[pattern] = (patternCounts[pattern] || 0) + 1;
  });

  // Bank involvement for bar chart
  const bankCounts = {};
  alertArray.forEach(a => {
    if (a.nodes) {
      a.nodes.forEach(node => {
        const bank = node.bank || 'Unknown';
        bankCounts[bank] = (bankCounts[bank] || 0) + 1;
      });
    }
  });
  const topBanks = Object.entries(bankCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  // Decision counts
  const decisionCounts = { confirm: 0, review: 0, dismiss: 0, pending: 0 };
  Object.entries(decisions).forEach(([alertId, dec]) => {
    if (dec.decision in decisionCounts) {
      decisionCounts[dec.decision]++;
    }
  });
  decisionCounts.pending = alertArray.length - decisionCount;

  useEffect(() => {
    if (chartDonutRef.current && window.Chart) {
      const ctx = chartDonutRef.current.getContext('2d');
      const colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];
      new window.Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: Object.keys(patternCounts),
          datasets: [
            {
              data: Object.values(patternCounts),
              backgroundColor: colors.slice(0, Object.keys(patternCounts).length),
              borderColor: 'var(--surface)',
              borderWidth: 2,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: { legend: { position: 'bottom' } },
        },
      });
    }
  }, [patternCounts]);

  useEffect(() => {
    if (chartBanksRef.current && window.Chart && topBanks.length > 0) {
      const ctx = chartBanksRef.current.getContext('2d');
      new window.Chart(ctx, {
        type: 'bar',
        data: {
          labels: topBanks.map(b => b[0]),
          datasets: [
            {
              label: 'Transactions',
              data: topBanks.map(b => b[1]),
              backgroundColor: '#3B82F6',
              borderRadius: 4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          indexAxis: 'y',
          plugins: { legend: { display: false } },
        },
      });
    }
  }, [topBanks]);

  return (
    <div className="view active" id="view-dashboard" role="tabpanel">
      <div className="db-grid-4">
        <div className="color-card blue">
          <span className="label-up">Total Alerts</span>
          <div className="card-num blue">{alertArray.length}</div>
          <div className="card-sub">Labelled + Unlabelled</div>
        </div>
        <div className="color-card green">
          <span className="label-up">Money Flagged</span>
          <div className="card-num green">${totalMoved.toFixed(0)}</div>
          <div className="card-sub">Across all alerts</div>
        </div>
        <div className="color-card red">
          <span className="label-up">High Severity</span>
          <div className="card-num red">{highSeverityCount}</div>
          <div className="card-sub">Requires immediate review</div>
        </div>
        <div className="color-card amber">
          <span className="label-up">Decisions Made</span>
          <div className="card-num amber">{decisionCount}</div>
          <div className="card-sub">Confirmed / reviewed / dismissed</div>
        </div>
      </div>

      <div className="db-grid-2">
        <div className="db-chart-card">
          <h3>Pattern Breakdown</h3>
          <div className="chart-wrap">
            <canvas
              ref={chartDonutRef}
              aria-label="Donut chart showing pattern type distribution"
            ></canvas>
          </div>
        </div>
        <div className="db-chart-card">
          <h3>Most Involved Banks</h3>
          <div className="chart-wrap">
            <canvas
              ref={chartBanksRef}
              aria-label="Bar chart showing most involved banks"
            ></canvas>
          </div>
        </div>
      </div>

      <div className="db-bottom">
        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r)',
            padding: 'var(--sp-5)',
          }}
        >
          <span className="label-up">Decision Summary</span>
          <table
            className="dec-summary-table"
            aria-label="Decision summary"
            style={{ marginTop: 'var(--sp-3)' }}
          >
            <tbody>
              <tr>
                <td>Confirmed</td>
                <td>
                  <span className="dec-num" style={{ color: 'var(--green)' }}>
                    {decisionCounts.confirm}
                  </span>
                </td>
              </tr>
              <tr>
                <td>Needs Review</td>
                <td>
                  <span className="dec-num" style={{ color: 'var(--amber)' }}>
                    {decisionCounts.review}
                  </span>
                </td>
              </tr>
              <tr>
                <td>Dismissed</td>
                <td>
                  <span className="dec-num" style={{ color: 'var(--red)' }}>
                    {decisionCounts.dismiss}
                  </span>
                </td>
              </tr>
              <tr>
                <td>Pending</td>
                <td>
                  <span className="dec-num" style={{ color: 'var(--muted)' }}>
                    {decisionCounts.pending}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
