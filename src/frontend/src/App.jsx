import React, { useState, useEffect } from 'react';
import { api } from './utils/api';
import Dashboard from './components/Dashboard';
import Investigate from './components/Investigate';
import CaseManager from './components/CaseManager';
import Search from './components/Search';
import Whitelist from './components/Whitelist';
import Navigation from './components/Navigation';

export default function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [alerts, setAlerts] = useState({});
  const [decisions, setDecisions] = useState({});
  const [status, setStatus] = useState(null);
  const [mlMetrics, setMlMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    loadInitialData();
    const timer = setInterval(loadInitialData, 30000);
    return () => clearInterval(timer);
  }, []);

  const loadInitialData = async () => {
    try {
      const [statusRes, alertsRes, decisionsRes, metricsRes] = await Promise.all([
        api.getStatus(),
        api.getAlerts(),
        api.getDecisions(),
        api.getMlMetrics(),
      ]);

      setStatus(statusRes);
      setAlerts(Object.fromEntries(alertsRes.map(a => [a.id, a])));
      setDecisions(decisionsRes);
      setMlMetrics(metricsRes);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePostDecision = async (alertId, decision, reason) => {
    try {
      await api.postDecision(alertId, decision, reason);
      const updated = await api.getDecisions();
      setDecisions(updated);
    } catch (error) {
      console.error('Failed to post decision:', error);
    }
  };

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.style.colorScheme = darkMode ? 'light' : 'dark';
  };

  if (loading) {
    return (
      <div id="loading-overlay">
        <div className="load-inner">
          <svg className="load-logo" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="M9 12l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div className="load-title">AML Intelligence Platform</div>
          <div className="load-sub">Initializing detection engine...</div>
          <div className="load-bar-wrap" style={{width: '100%', marginTop: '16px'}}>
            <div className="load-bar" style={{width: '75%'}}></div>
          </div>
          <div className="load-stages" style={{marginTop: '16px', width: '100%'}}>
            <div className="load-stage done">
              <div className="load-stage-dot done"></div>
              <span className="load-stage-label">Establishing secure connection...</span>
            </div>
            <div className="load-stage done">
              <div className="load-stage-dot done"></div>
              <span className="load-stage-label">Loading transaction graph...</span>
            </div>
            <div className="load-stage done">
              <div className="load-stage-dot done"></div>
              <span className="load-stage-label">Running pattern detection engine...</span>
            </div>
            <div className="load-stage active">
              <div className="load-stage-dot active"></div>
              <span className="load-stage-label">Building alert index...</span>
            </div>
          </div>
          <div className="load-session-info">SESSION ubu · UBI · {new Date().toISOString().replace('T', ' ').slice(0, -5)} UTC</div>
        </div>
      </div>
    );
  }

  const viewProps = {
    alerts,
    decisions,
    status,
    mlMetrics,
    onPostDecision: handlePostDecision,
    onRefresh: loadInitialData,
  };

  return (
    <div className={darkMode ? 'dark-mode' : ''}>
      <Navigation
        currentView={currentView}
        onViewChange={setCurrentView}
        status={status}
        darkMode={darkMode}
        onToggleDarkMode={toggleDarkMode}
      />
      <main>
        {currentView === 'dashboard' && <Dashboard {...viewProps} />}
        {currentView === 'investigate' && <Investigate {...viewProps} />}
        {currentView === 'cases' && <CaseManager {...viewProps} />}
        {currentView === 'search' && <Search {...viewProps} />}
        {currentView === 'whitelist' && <Whitelist {...viewProps} />}
      </main>
    </div>
  );
}
