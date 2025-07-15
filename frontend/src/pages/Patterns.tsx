import React, { useState, useEffect } from 'react';

interface SuspiciousActivity {
  activity_id: string;
  pattern_type: string;
  trader_id: string;
  account_id?: string;
  instrument: string;
  confidence_score: number;
  timestamp: string;
  description: string;
  severity: string;
  related_trades: string[];
  related_orders: string[];
}

interface PatternDetails {
  pattern_id: string;
  pattern_info: {
    pattern_type: string;
    trader_id: string;
    account_id?: string;
    instrument: string;
    confidence_score: number;
    severity: string;
    timestamp: string;
    description: string;
    related_trades: string[];
    related_orders: string[];
  };
  transaction_details: Array<{
    transaction_id: string;
    details: Record<string, any>;
  }>;
  trader_details: Record<string, any>;
  account_details: Record<string, any>;
  security_details: Record<string, any>;
  related_entities: Record<string, any>;
}

const Patterns: React.FC = () => {
  const [patterns, setPatterns] = useState<SuspiciousActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPatternType, setSelectedPatternType] = useState<string>('all');
  const [selectedTrader, setSelectedTrader] = useState<string>('all');
  const [selectedAccount, setSelectedAccount] = useState<string>('all');
  const [selectedInstrument, setSelectedInstrument] = useState<string>('all');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [selectedPattern, setSelectedPattern] = useState<PatternDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    fetchPatterns();
  }, []);

  const fetchPatterns = async () => {
    try {
      const response = await fetch('/api/patterns/detect');
      if (!response.ok) {
        throw new Error('Failed to fetch patterns');
      }
      const data = await response.json();
      setPatterns(data.detected_activities || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const fetchPatternDetails = async (patternId: string) => {
    setDetailsLoading(true);
    try {
      const response = await fetch(`/api/patterns/${patternId}/details`);
      if (!response.ok) {
        throw new Error('Failed to fetch pattern details');
      }
      const data = await response.json();
      setSelectedPattern(data);
      setShowModal(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pattern details');
    } finally {
      setDetailsLoading(false);
    }
  };

  const handlePatternClick = (pattern: SuspiciousActivity) => {
    fetchPatternDetails(pattern.activity_id);
  };

  const closeModal = () => {
    setShowModal(false);
    setSelectedPattern(null);
  };

  const filteredPatterns = patterns.filter(pattern => {
    const matchesPatternType = selectedPatternType === 'all' || pattern.pattern_type === selectedPatternType;
    const matchesTrader = selectedTrader === 'all' || pattern.trader_id === selectedTrader;
    const matchesAccount = selectedAccount === 'all' || pattern.account_id === selectedAccount;
    const matchesInstrument = selectedInstrument === 'all' || pattern.instrument === selectedInstrument;
    const matchesSeverity = selectedSeverity === 'all' || pattern.severity === selectedSeverity;
    
    return matchesPatternType && matchesTrader && matchesAccount && matchesInstrument && matchesSeverity;
  });

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical': return 'bg-red-100 text-red-800';
      case 'high': return 'bg-orange-100 text-orange-800';
      case 'medium': return 'bg-yellow-100 text-yellow-800';
      case 'low': return 'bg-green-100 text-green-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  // Get unique values for filter dropdowns
  const getUniqueTraders = () => {
    const traders = Array.from(new Set(patterns.map(p => p.trader_id))).sort();
    return traders;
  };

  const getUniqueAccounts = () => {
    const accounts = Array.from(new Set(patterns.map(p => p.account_id).filter(id => id !== undefined && id !== null))).sort();
    return accounts;
  };

  const getUniqueInstruments = () => {
    const instruments = Array.from(new Set(patterns.map(p => p.instrument))).sort();
    return instruments;
  };

  const getUniqueSeverities = () => {
    const severities = Array.from(new Set(patterns.map(p => p.severity))).sort();
    return severities;
  };

  // Helper function to check if two transactions are connected
  const areTransactionsConnected = (pattern: PatternDetails, fromTxId: string, toTxId: string) => {
    try {
      const relatedEntities = pattern.related_entities;
      if (relatedEntities[fromTxId]?.connected_transactions) {
        return relatedEntities[fromTxId].connected_transactions.some(
          (conn: any) => conn.id === toTxId
        );
      }
      return false;
    } catch (error) {
      return false;
    }
  };

  // Helper function to format values properly, especially dates
  const formatValue = (key: string, value: any): string => {
    if (value === null || value === undefined) {
      return 'N/A';
    }
    
    // Handle primitive types first
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
    
    // Handle Date objects
    if (value instanceof Date) {
      return value.toLocaleString();
    }
    
    // Handle complex objects (like Neo4j DateTime, Point, etc.)
    if (typeof value === 'object') {
      // First, check for Neo4j DateTime objects regardless of field name
      try {
        // Handle Neo4j DateTime objects with _DateTime__date and _DateTime__time properties
        if (value._DateTime__date && value._DateTime__time) {
          console.log('Processing Neo4j DateTime object:', value);
          const dateObj = value._DateTime__date;
          const timeObj = value._DateTime__time;
          
          // Extract date components using correct Neo4j property names
          const year = dateObj._Date__year ?? dateObj.year?.low ?? dateObj.year;
          const month = dateObj._Date__month ?? dateObj.month?.low ?? dateObj.month;
          const day = dateObj._Date__day ?? dateObj.day?.low ?? dateObj.day;
          
          // Extract time components using correct Neo4j property names
          const hour = timeObj._Time__hour ?? timeObj.hour?.low ?? timeObj.hour ?? 0;
          const minute = timeObj._Time__minute ?? timeObj.minute?.low ?? timeObj.minute ?? 0;
          const second = timeObj._Time__second ?? timeObj.second?.low ?? timeObj.second ?? 0;
          
          console.log('Extracted components:', {year, month, day, hour, minute, second});
          
          if (year !== undefined && month !== undefined && day !== undefined) {
            const formatted = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')} ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}`;
            console.log('Formatted DateTime:', formatted);
            return formatted;
          }
        }
      } catch (error) {
        console.warn('Error processing _DateTime object:', error, value);
      }
      
      // Check if this looks like a timestamp or date field for other formats
      if (key.toLowerCase().includes('timestamp') || 
          key.toLowerCase().includes('time') || 
          key.toLowerCase().includes('date')) {
        try {
          // Handle Neo4j DateTime objects - direct property access
          if (value.year && value.month && value.day) {
            const year = value.year?.low || value.year;
            const month = value.month?.low || value.month;
            const day = value.day?.low || value.day;
            const hour = value.hour?.low || value.hour || 0;
            const minute = value.minute?.low || value.minute || 0;
            const second = value.second?.low || value.second || 0;
            
            return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')} ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}`;
          }
          
          // Handle Neo4j Temporal objects with epochSecond
          if (value.epochSecond !== undefined) {
            const epochSeconds = value.epochSecond?.low || value.epochSecond;
            const nanoseconds = value.nanosecond?.low || value.nanosecond || 0;
            const milliseconds = epochSeconds * 1000 + Math.floor(nanoseconds / 1000000);
            return new Date(milliseconds).toLocaleString();
          }
          
          // Try to convert object to string representation
          if (value.toString && typeof value.toString === 'function' && value.toString() !== '[object Object]') {
            return value.toString();
          }
          
        } catch (error) {
          console.warn('Error formatting date object:', error, value);
        }
      }
      
      // For other objects, try to extract meaningful information
      try {
        // If it has a value property, use that
        if (value.hasOwnProperty('value')) {
          return formatValue(key, value.value);
        }
        
        // If it has low/high properties (Neo4j integers), use low
        if (value.hasOwnProperty('low')) {
          return String(value.low);
        }
        
        // Try JSON stringify as a last resort for complex objects
        const jsonStr = JSON.stringify(value);
        if (jsonStr && jsonStr !== '{}' && jsonStr.length < 100) {
          return jsonStr;
        }
        
        // If object has meaningful keys, show them
        const keys = Object.keys(value);
        if (keys.length > 0 && keys.length <= 5) {
          return `{${keys.join(', ')}}`;
        }
        
      } catch (error) {
        console.warn('Error processing object value:', error, value);
      }
      
      // Final fallback for objects
      return '[Complex Object]';
    }
    
    // Fallback for any other type
    return String(value);
  };

  const renderPatternDiagram = (pattern: PatternDetails) => {
    const traderId = pattern.pattern_info.trader_id;
    const accountId = pattern.pattern_info.account_id;
    const instrument = pattern.pattern_info.instrument;
    const transactions = pattern.pattern_info.related_trades;
    
    return (
      <div className="flex flex-col items-center space-y-6 py-6">
        {/* Top Row: Trader and Account */}
        <div className="flex items-center space-x-8">
          {/* Trader Node */}
          <div className="flex flex-col items-center">
            <div className="bg-blue-100 border-2 border-blue-600 rounded-lg px-4 py-2 font-semibold text-blue-800">
              🧑 Trader: {traderId}
            </div>
          </div>
          
          {/* Account Node (if available) */}
          {accountId && (
            <div className="flex flex-col items-center">
              <div className="bg-green-100 border-2 border-green-600 rounded-lg px-4 py-2 font-semibold text-green-800">
                🏦 Account: {accountId}
              </div>
            </div>
          )}
        </div>

        {/* Arrows pointing down to transactions */}
        <div className="flex items-center space-x-8">
          <div className="flex flex-col items-center">
            <div className="text-xs text-gray-500">PLACED_BY</div>
            <div className="w-0.5 h-8 bg-gray-400"></div>
          </div>
          {accountId && (
            <div className="flex flex-col items-center">
              <div className="text-xs text-gray-500">PLACED</div>
              <div className="w-0.5 h-8 bg-gray-400"></div>
            </div>
          )}
        </div>

        {/* Transaction Chain */}
        <div className="flex items-center space-x-4">
          {transactions.map((txId, index) => (
            <div key={txId} className="flex items-center">
              <div className="flex flex-col items-center">
                <div className="bg-orange-100 border-2 border-orange-600 rounded-lg px-3 py-2 font-semibold text-orange-800">
                  💼 {txId}
                </div>
                {/* Show INVOLVES arrow to security */}
                <div className="text-xs text-gray-500 mt-1">INVOLVES</div>
                <div className="w-0.5 h-8 bg-gray-400"></div>
              </div>
              {/* Show CONNECTED_TO arrow if transactions are actually connected */}
              {index < transactions.length - 1 && areTransactionsConnected(pattern, txId, transactions[index + 1]) && (
                <div className="flex flex-col items-center mx-2">
                  <div className="text-xs text-gray-500">CONNECTED_TO</div>
                  <div className="h-0.5 w-8 bg-gray-400"></div>
                  <div className="w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-400"></div>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Security Node */}
        <div className="bg-purple-100 border-2 border-purple-600 rounded-lg px-4 py-2 font-semibold text-purple-800">
          📈 Security: {instrument}
        </div>

        {/* Pattern Type Indicator */}
        <div className="mt-4 text-center">
          <div className={`inline-flex px-3 py-1 rounded-full text-sm font-semibold ${
            pattern.pattern_info.pattern_type === 'LAYERING' 
              ? 'bg-red-100 text-red-800' 
              : 'bg-yellow-100 text-yellow-800'
          }`}>
            {pattern.pattern_info.pattern_type} Pattern Detected
          </div>
        </div>
      </div>
    );
  };

  const PatternDetailsModal: React.FC<{ pattern: PatternDetails }> = ({ pattern }) => {
    return (
      <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
        <div className="relative top-20 mx-auto p-5 border w-11/12 max-w-4xl shadow-lg rounded-md bg-white">
          <div className="mt-3">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-2xl font-bold text-gray-900">Pattern Details</h3>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Network Diagram */}
            <div className="mb-6 card">
              <div className="px-4 py-3 border-b">
                <h4 className="text-lg font-semibold">Network Diagram</h4>
                <p className="text-sm text-gray-500 mt-1">Visual representation of entities and relationships in this pattern</p>
              </div>
              <div className="p-4">
                <div className="bg-gray-50 rounded-lg overflow-x-auto">
                  {renderPatternDiagram(pattern)}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Pattern Information */}
              <div className="card">
                <div className="px-4 py-3 border-b">
                  <h4 className="text-lg font-semibold">Pattern Information</h4>
                </div>
                <div className="p-4 space-y-3">
                  <div className="flex justify-between">
                    <span className="font-medium">Type:</span>
                    <span className="text-blue-600">{pattern.pattern_info.pattern_type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium">Trader ID:</span>
                    <span>{pattern.pattern_info.trader_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium">Account:</span>
                    <span>{pattern.pattern_info.account_id || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium">Instrument:</span>
                    <span>{pattern.pattern_info.instrument}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium">Confidence:</span>
                    <span>{(pattern.pattern_info.confidence_score * 100).toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium">Severity:</span>
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getSeverityColor(pattern.pattern_info.severity)}`}>
                      {pattern.pattern_info.severity}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium">Timestamp:</span>
                    <span>{new Date(pattern.pattern_info.timestamp).toLocaleString()}</span>
                  </div>
                  <div className="mt-4">
                    <span className="font-medium">Description:</span>
                    <p className="text-sm text-gray-600 mt-1">{pattern.pattern_info.description}</p>
                  </div>
                </div>
              </div>

              {/* Trader Details */}
              <div className="card">
                <div className="px-4 py-3 border-b">
                  <h4 className="text-lg font-semibold">Trader Details</h4>
                </div>
                <div className="p-4">
                  {pattern.trader_details.error ? (
                    <p className="text-red-600">{pattern.trader_details.error}</p>
                  ) : (
                    <div className="space-y-2">
                      {Object.entries(pattern.trader_details).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span className="font-medium capitalize">{key.replace('_', ' ')}:</span>
                          <span className="text-sm">{String(value)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Account Details */}
              <div className="card">
                <div className="px-4 py-3 border-b">
                  <h4 className="text-lg font-semibold">Account Details</h4>
                </div>
                <div className="p-4">
                  {pattern.account_details.error ? (
                    <p className="text-red-600">{pattern.account_details.error}</p>
                  ) : pattern.account_details.message ? (
                    <p className="text-gray-500 italic">{pattern.account_details.message}</p>
                  ) : (
                    <div className="space-y-2">
                      {Object.entries(pattern.account_details).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span className="font-medium capitalize">{key.replace('_', ' ')}:</span>
                          <span className="text-sm">{String(value)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Security Details */}
              <div className="card">
                <div className="px-4 py-3 border-b">
                  <h4 className="text-lg font-semibold">Security Details</h4>
                </div>
                <div className="p-4">
                  {pattern.security_details.error ? (
                    <p className="text-red-600">{pattern.security_details.error}</p>
                  ) : (
                    <div className="space-y-2">
                      {Object.entries(pattern.security_details).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span className="font-medium capitalize">{key.replace('_', ' ')}:</span>
                          <span className="text-sm">{String(value)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Transaction Details */}
              <div className="card">
                <div className="px-4 py-3 border-b">
                  <h4 className="text-lg font-semibold">Transaction Details</h4>
                </div>
                <div className="p-4 max-h-80 overflow-y-auto">
                  {pattern.transaction_details.map((transaction, index) => (
                    <div key={index} className="mb-4 p-3 bg-gray-50 rounded">
                      <h5 className="font-semibold text-blue-600 mb-2">
                        {transaction.transaction_id}
                      </h5>
                      {transaction.details.error ? (
                        <p className="text-red-600 text-sm">{transaction.details.error}</p>
                      ) : (
                        <div className="grid grid-cols-1 gap-1">
                          {Object.entries(transaction.details).map(([key, value]) => (
                            <div key={key} className="flex justify-between text-sm">
                              <span className="font-medium">{key.replace('_', ' ')}:</span>
                              <span className="text-gray-600">{formatValue(key, value)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Transaction IDs Summary */}
            <div className="mt-6 card">
              <div className="px-4 py-3 border-b">
                <h4 className="text-lg font-semibold">Related Transaction IDs</h4>
              </div>
              <div className="p-4">
                <div className="flex flex-wrap gap-2">
                  {pattern.pattern_info.related_trades.map((transactionId, index) => (
                    <span key={index} className="inline-flex px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">
                      {transactionId}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
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
        Error loading patterns: {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            Suspicious Patterns
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Detected patterns of suspicious trading activity
          </p>
        </div>
      </div>

      {/* Filters Section */}
      <div className="card p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pattern Type</label>
            <select
              value={selectedPatternType}
              onChange={(e) => setSelectedPatternType(e.target.value)}
              className="input w-full"
            >
              <option value="all">All Patterns</option>
              <option value="SPOOFING">Spoofing</option>
              <option value="LAYERING">Layering</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Trader</label>
            <select
              value={selectedTrader}
              onChange={(e) => setSelectedTrader(e.target.value)}
              className="input w-full"
            >
              <option value="all">All Traders</option>
              {getUniqueTraders().map(trader => (
                <option key={trader} value={trader}>{trader}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Account</label>
            <select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="input w-full"
            >
              <option value="all">All Accounts</option>
              {getUniqueAccounts().map(account => (
                <option key={account} value={account}>{account}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Instrument</label>
            <select
              value={selectedInstrument}
              onChange={(e) => setSelectedInstrument(e.target.value)}
              className="input w-full"
            >
              <option value="all">All Instruments</option>
              {getUniqueInstruments().map(instrument => (
                <option key={instrument} value={instrument}>{instrument}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Severity</label>
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="input w-full"
            >
              <option value="all">All Severities</option>
              {getUniqueSeverities().map(severity => (
                <option key={severity} value={severity}>{severity}</option>
              ))}
            </select>
          </div>
        </div>
        
        {/* Clear Filters Button */}
        <div className="mt-4 flex justify-end">
          <button
            onClick={() => {
              setSelectedPatternType('all');
              setSelectedTrader('all');
              setSelectedAccount('all');
              setSelectedInstrument('all');
              setSelectedSeverity('all');
            }}
            className="btn btn-secondary text-sm"
          >
            Clear Filters
          </button>
        </div>
      </div>

      <div className="card">
        <div className="px-4 py-5 sm:p-6">
                      <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-medium text-gray-900">
                  Detected Patterns ({filteredPatterns.length})
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Click on any pattern to view detailed information
                </p>
              </div>
              <button
                onClick={fetchPatterns}
                className="btn btn-primary"
              >
                Refresh
              </button>
            </div>
          
          {filteredPatterns.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-500">No patterns detected</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Pattern Type
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Trader ID
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Account
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Instrument
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Confidence
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Severity
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Timestamp
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {filteredPatterns.map((pattern) => (
                    <tr 
                      key={pattern.activity_id} 
                      className="hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => handlePatternClick(pattern)}
                    >
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {pattern.pattern_type}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {pattern.trader_id}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {pattern.account_id || 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {pattern.instrument}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        <div className="flex items-center">
                          <div className="w-full bg-gray-200 rounded-full h-2">
                            <div 
                              className="bg-primary-600 h-2 rounded-full" 
                              style={{ width: `${pattern.confidence_score * 100}%` }}
                            ></div>
                          </div>
                          <span className="ml-2 text-xs">{(pattern.confidence_score * 100).toFixed(1)}%</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getSeverityColor(pattern.severity)}`}>
                          {pattern.severity}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {new Date(pattern.timestamp).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handlePatternClick(pattern);
                          }}
                          className="text-blue-600 hover:text-blue-900 font-medium"
                        >
                          View Details
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Loading indicator for pattern details */}
      {detailsLoading && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
            <div className="flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
              <span className="ml-3 text-lg">Loading pattern details...</span>
            </div>
          </div>
        </div>
      )}

      {/* Pattern Details Modal */}
      {showModal && selectedPattern && (
        <PatternDetailsModal pattern={selectedPattern} />
      )}
    </div>
  );
};

export default Patterns; 