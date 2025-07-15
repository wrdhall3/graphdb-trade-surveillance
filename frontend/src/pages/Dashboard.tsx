import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { ExclamationTriangleIcon, ShieldCheckIcon, ClockIcon } from '@heroicons/react/24/outline';

interface DashboardSummary {
  total_patterns: number;
  spoofing_patterns: number;
  layering_patterns: number;
  high_confidence_patterns: number;
  critical_patterns: number;
  unique_traders: number;
  unique_instruments: number;
  monitoring_status: boolean;
  last_updated: string;
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Reset state on mount
    setLoading(true);
    setError(null);
    setSummary(null);
    
    fetchDashboardSummary();
    const interval = setInterval(() => {
      // Only refresh if not currently loading
      if (!loading) {
        fetchDashboardSummary();
      }
    }, 30000); // Refresh every 30 seconds
    
    return () => clearInterval(interval);
  }, []);

  const fetchDashboardSummary = async (retryCount = 0) => {
    const maxRetries = 3;
    const retryDelay = Math.min(1000 * Math.pow(2, retryCount), 5000); // Exponential backoff, max 5 seconds
    
    try {
      console.log(`Dashboard fetch attempt ${retryCount + 1}`);
      
      // Add timeout to prevent hanging
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
      
      const response = await fetch('/api/dashboard/summary', {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('Dashboard data received:', data);
      setSummary(data);
      setError(null);
      setLoading(false); // Success - stop loading
      
    } catch (err) {
      console.warn(`Dashboard fetch attempt ${retryCount + 1} failed:`, err);
      
      const error = err as Error;
      if (retryCount < maxRetries && error.name !== 'AbortError') {
        // Show a different message for retries
        setError(`Backend starting up... (attempt ${retryCount + 1}/${maxRetries + 1})`);
        setTimeout(() => fetchDashboardSummary(retryCount + 1), retryDelay);
        return; // Don't set loading to false yet
      } else {
        const errorMessage = error.name === 'AbortError' ? 
          'Request timed out - backend may be slow to respond' : 
          (error instanceof Error ? error.message : 'An error occurred');
        setError(errorMessage);
        setLoading(false); // Failed after all retries - stop loading
      }
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-danger">
        <ExclamationTriangleIcon className="h-5 w-5 mr-2" />
        Error loading dashboard: {error}
        <button 
          onClick={() => {
            console.log('Manual retry clicked');
            setError(null);
            setLoading(true);
            setSummary(null);
            fetchDashboardSummary(0); // Start fresh with retry count 0
          }}
          className="btn btn-secondary ml-4"
        >
          Retry
        </button>
      </div>
    );
  }

  const patternData = [
    { name: 'Spoofing', value: summary?.spoofing_patterns || 0 },
    { name: 'Layering', value: summary?.layering_patterns || 0 },
  ];

  const confidenceData = [
    { name: 'High Confidence', value: summary?.high_confidence_patterns || 0 },
    { name: 'Total Patterns', value: summary?.total_patterns || 0 },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            Trade Surveillance Dashboard
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Last updated: {summary?.last_updated ? new Date(summary.last_updated).toLocaleString() : 'Unknown'}
          </p>
        </div>
        <div className="mt-4 flex md:mt-0 md:ml-4">
          <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
            summary?.monitoring_status 
              ? 'bg-success-100 text-success-800' 
              : 'bg-gray-100 text-gray-800'
          }`}>
            <div className={`w-2 h-2 rounded-full mr-2 ${
              summary?.monitoring_status ? 'bg-success-500' : 'bg-gray-500'
            }`} />
            {summary?.monitoring_status ? 'Active' : 'Inactive'}
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <div 
          className="card p-6 cursor-pointer hover:bg-gray-50 transition-colors"
          onClick={() => navigate('/patterns')}
        >
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <ExclamationTriangleIcon className="h-8 w-8 text-danger-500" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Total Patterns</dt>
                <dd className="text-lg font-medium text-gray-900">{summary?.total_patterns || 0}</dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="card p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <ShieldCheckIcon className="h-8 w-8 text-warning-500" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">High Confidence</dt>
                <dd className="text-lg font-medium text-gray-900">{summary?.high_confidence_patterns || 0}</dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="card p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <ClockIcon className="h-8 w-8 text-primary-500" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Unique Traders</dt>
                <dd className="text-lg font-medium text-gray-900">{summary?.unique_traders || 0}</dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="card p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="h-8 w-8 bg-success-500 rounded-full flex items-center justify-center">
                <span className="text-white text-sm font-medium">I</span>
              </div>
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Instruments</dt>
                <dd className="text-lg font-medium text-gray-900">{summary?.unique_instruments || 0}</dd>
              </dl>
            </div>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Pattern Types</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={patternData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#3b82f6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Confidence Analysis</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={confidenceData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#10b981" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="card p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Recent Activity</h3>
        <div className="text-sm text-gray-500">
          {summary?.total_patterns === 0 ? (
            <p>No suspicious patterns detected recently.</p>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span>Spoofing patterns detected</span>
                <span className="font-medium text-gray-900">{summary?.spoofing_patterns || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Layering patterns detected</span>
                <span className="font-medium text-gray-900">{summary?.layering_patterns || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Critical severity patterns</span>
                <span className="font-medium text-danger-600">{summary?.critical_patterns || 0}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard; 