import React, { useState, useEffect } from 'react';

interface MonitoringConfig {
  enabled: boolean;
  check_interval_minutes: number;
  patterns_to_monitor: string[];
  confidence_threshold: number;
  severity_threshold: string;
}

interface MonitoringStatus {
  enabled: boolean;
  running: boolean;
  config: MonitoringConfig;
}

const Monitoring: React.FC = () => {
  const [status, setStatus] = useState<MonitoringStatus | null>(null);
  const [config, setConfig] = useState<MonitoringConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStatus();
    fetchConfig();
  }, []);

  const fetchStatus = async () => {
    try {
      const response = await fetch('/api/monitoring/status');
      if (!response.ok) {
        throw new Error('Failed to fetch monitoring status');
      }
      const data = await response.json();
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    }
  };

  const fetchConfig = async () => {
    try {
      const response = await fetch('/api/monitoring/config');
      if (!response.ok) {
        throw new Error('Failed to fetch monitoring config');
      }
      const data = await response.json();
      setConfig(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const updateConfig = async (newConfig: MonitoringConfig) => {
    try {
      const response = await fetch('/api/monitoring/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newConfig),
      });
      if (!response.ok) {
        throw new Error('Failed to update monitoring config');
      }
      await fetchStatus();
      await fetchConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    }
  };

  const runSurveillanceCycle = async () => {
    try {
      const response = await fetch('/api/monitoring/run', {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Failed to run surveillance cycle');
      }
      const data = await response.json();
      alert(`Surveillance cycle completed. Found ${data.detected_patterns?.length || 0} patterns.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            Monitoring & Agents
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Configure and monitor the AI surveillance agents
          </p>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger">
          {error}
        </div>
      )}

      {/* Status Card */}
      <div className="card p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Agent Status</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="text-center">
            <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
              status?.enabled ? 'bg-success-100 text-success-800' : 'bg-gray-100 text-gray-800'
            }`}>
              <div className={`w-2 h-2 rounded-full mr-2 ${
                status?.enabled ? 'bg-success-500' : 'bg-gray-500'
              }`} />
              {status?.enabled ? 'Enabled' : 'Disabled'}
            </div>
            <p className="text-sm text-gray-500 mt-1">Configuration</p>
          </div>
          <div className="text-center">
            <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
              status?.running ? 'bg-success-100 text-success-800' : 'bg-gray-100 text-gray-800'
            }`}>
              <div className={`w-2 h-2 rounded-full mr-2 ${
                status?.running ? 'bg-success-500' : 'bg-gray-500'
              }`} />
              {status?.running ? 'Running' : 'Stopped'}
            </div>
            <p className="text-sm text-gray-500 mt-1">Agent Status</p>
          </div>
          <div className="text-center">
            <button
              onClick={runSurveillanceCycle}
              className="btn btn-primary"
            >
              Run Cycle
            </button>
            <p className="text-sm text-gray-500 mt-1">Manual Trigger</p>
          </div>
        </div>
      </div>

      {/* Configuration Card */}
      {config && (
        <div className="card p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Configuration</h3>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Check Interval (minutes)
                </label>
                <input
                  type="number"
                  value={config.check_interval_minutes}
                  onChange={(e) => setConfig({
                    ...config,
                    check_interval_minutes: parseInt(e.target.value) || 5
                  })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Confidence Threshold
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  value={config.confidence_threshold}
                  onChange={(e) => setConfig({
                    ...config,
                    confidence_threshold: parseFloat(e.target.value) || 0.7
                  })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                />
              </div>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                checked={config.enabled}
                onChange={(e) => setConfig({
                  ...config,
                  enabled: e.target.checked
                })}
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <label className="ml-2 block text-sm text-gray-900">
                Enable continuous monitoring
              </label>
            </div>
            <button
              onClick={() => updateConfig(config)}
              className="btn btn-primary"
            >
              Update Configuration
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Monitoring; 