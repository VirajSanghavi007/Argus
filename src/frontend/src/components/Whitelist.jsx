import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

export default function Whitelist() {
  const [whitelist, setWhitelist] = useState(null);
  const [suppressed, setSuppressed] = useState([]);
  const [newAccount, setNewAccount] = useState('');
  const [newReason, setNewReason] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadWhitelistData();
  }, []);

  const loadWhitelistData = async () => {
    try {
      const [wlRes, supRes] = await Promise.all([api.getWhitelist(), api.getSuppressed()]);
      setWhitelist(wlRes);
      setSuppressed(supRes);
    } catch (error) {
      console.error('Failed to load whitelist data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddAccount = async () => {
    if (!newAccount.trim()) return;
    try {
      await api.addWhitelistAccount(newAccount, newReason);
      setNewAccount('');
      setNewReason('');
      await loadWhitelistData();
    } catch (error) {
      console.error('Failed to add account:', error);
    }
  };

  const handleRemoveAccount = async accountId => {
    try {
      await api.removeWhitelistAccount(accountId);
      await loadWhitelistData();
    } catch (error) {
      console.error('Failed to remove account:', error);
    }
  };

  if (loading) {
    return <div className="view">Loading...</div>;
  }

  return (
    <div className="view" id="view-whitelist" role="tabpanel">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        <h2 style={{ fontFamily: 'var(--sans)', fontWeight: 700, fontSize: 'var(--text-xl)' }}>
          Whitelist / Exemption System
        </h2>
      </div>

      <div className="verdict-banner">
        <div className="verdict-icon" aria-hidden="true">
          🛡️
        </div>
        <div>
          <div className="verdict-title">False Positive Reduction</div>
          <div className="verdict-desc">
            Business accounts and known financial institutions are exempt from certain detection patterns to
            reduce false positives. Fully-exempt clusters are suppressed (not deleted) and visible in the
            suppressed alerts table below.
          </div>
        </div>
      </div>

      <div className="wl-grid">
        <div className="wl-panel">
          <div className="wl-panel-title">Current Exempt Accounts</div>
          <div id="wl-accounts-list" role="list" aria-label="Exempt accounts">
            {whitelist?.accounts && whitelist.accounts.length > 0 ? (
              whitelist.accounts.map(accountId => (
                <div
                  key={accountId}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: 'var(--sp-2)',
                    background: 'var(--row-alt)',
                    borderRadius: 'var(--r)',
                    marginBottom: 'var(--sp-2)',
                    fontSize: 'var(--text-sm)',
                  }}
                >
                  <span>{accountId}</span>
                  <button
                    onClick={() => handleRemoveAccount(accountId)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--red)',
                      cursor: 'pointer',
                      fontSize: 'var(--text-xs)',
                    }}
                  >
                    Remove
                  </button>
                </div>
              ))
            ) : (
              <span style={{ color: 'var(--light)', fontSize: 'var(--text-sm)', fontFamily: 'var(--mono)' }}>
                No accounts explicitly whitelisted
              </span>
            )}
          </div>

          <div style={{ marginTop: 'var(--sp-4)' }}>
            <div className="wl-panel-title">Exempt Banks</div>
            <div className="wl-exempt-banks" id="wl-banks-list" role="list" aria-label="Exempt banks">
              {whitelist?.banks && whitelist.banks.length > 0 ? (
                whitelist.banks.map((bank, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: 'var(--sp-2)',
                      background: 'var(--row-alt)',
                      borderRadius: 'var(--r)',
                      marginBottom: 'var(--sp-2)',
                      fontSize: 'var(--text-sm)',
                    }}
                  >
                    {bank}
                  </div>
                ))
              ) : (
                <span style={{ color: 'var(--light)', fontSize: 'var(--text-sm)' }}>No exempt banks</span>
              )}
            </div>
          </div>
        </div>

        <div className="wl-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="wl-panel-title">Add Account to Whitelist</div>
          <div className="wl-form" style={{ flex: 1 }}>
            <div>
              <label htmlFor="wl-account-inp" className="label-up">
                Account ID
              </label>
              <input
                type="text"
                id="wl-account-inp"
                placeholder="e.g. 80012345"
                value={newAccount}
                onChange={e => setNewAccount(e.target.value)}
                style={{ marginTop: 'var(--sp-2)', width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ marginTop: 'var(--sp-3)' }}>
              <label htmlFor="wl-reason-inp" className="label-up">
                Reason
              </label>
              <input
                type="text"
                id="wl-reason-inp"
                placeholder="e.g. Verified payroll account"
                value={newReason}
                onChange={e => setNewReason(e.target.value)}
                style={{ marginTop: 'var(--sp-2)', width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <button className="btn btn-blue" onClick={handleAddAccount} style={{ marginTop: 'var(--sp-4)', width: '100%' }}>
              Add to Whitelist
            </button>
          </div>
        </div>
      </div>

      <div className="suppressed-section">
        <div className="suppressed-hdr">
          <span>Suppressed Alerts</span>
          <span id="suppressed-count" style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 'var(--text-sm)' }}>
            {suppressed.length} alerts
          </span>
        </div>
        {suppressed.length === 0 ? (
          <div className="cases-empty" id="suppressed-empty">
            No alerts suppressed — whitelist rules have not matched any detected clusters.
          </div>
        ) : (
          <table className="data-table" aria-label="Suppressed alerts">
            <thead>
              <tr>
                <th scope="col">Alert ID</th>
                <th scope="col">Pattern</th>
                <th scope="col">Severity</th>
                <th scope="col">Exempt Accounts</th>
              </tr>
            </thead>
            <tbody id="suppressed-tbody">
              {suppressed.map(alert => (
                <tr key={alert.id}>
                  <td>{alert.id}</td>
                  <td>{alert.patternType}</td>
                  <td>{alert.severity}</td>
                  <td>{alert.nodes?.map(n => n.id).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
