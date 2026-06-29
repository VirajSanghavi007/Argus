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
    return <div className="load-overlay">Loading...</div>;
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
