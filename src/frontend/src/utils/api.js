const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export const api = {
  async request(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const error = new Error(`API error: ${response.status}`);
      error.status = response.status;
      throw error;
    }

    if (response.status === 204) return null;
    return response.json();
  },

  getStatus() {
    return this.request('/status');
  },

  getHealth() {
    return this.request('/health');
  },

  getAlerts(patternType, severity, source) {
    const params = new URLSearchParams();
    if (patternType) params.append('pattern_type', patternType);
    if (severity) params.append('severity', severity);
    if (source) params.append('source', source);

    const query = params.toString();
    return this.request(`/alerts${query ? `?${query}` : ''}`);
  },

  getAlert(alertId) {
    return this.request(`/alerts/${alertId}`);
  },

  postDecision(alertId, decision, reason = '', analyst = '') {
    return this.request(`/alerts/${alertId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, reason, analyst }),
    });
  },

  getDecisionHistory(alertId) {
    return this.request(`/alerts/${alertId}/decision/history`);
  },

  getDecisions() {
    return this.request('/decisions');
  },

  getSuppressed() {
    return this.request('/alerts/suppressed');
  },

  getWhitelist() {
    return this.request('/whitelist');
  },

  addWhitelistAccount(accountId, reason = '') {
    return this.request('/whitelist/account', {
      method: 'POST',
      body: JSON.stringify({ account_id: accountId, reason }),
    });
  },

  removeWhitelistAccount(accountId) {
    return this.request(`/whitelist/account/${accountId}`, {
      method: 'DELETE',
    });
  },

  getMlMetrics() {
    return this.request('/ml-metrics');
  },

  getDrift() {
    return this.request('/drift');
  },

  async scanPipeline(maxRows = 600000) {
    return this.request('/scan', {
      method: 'POST',
      body: JSON.stringify({ max_rows: maxRows }),
    });
  },
};
