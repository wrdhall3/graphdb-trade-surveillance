import React, { useState } from 'react';

interface QueryResult {
  natural_language_query: string;
  translation: {
    cypher_query: string;
    explanation: string;
    confidence: number;
  };
  results: any[];
  count: number;
  error?: string;
}

const QueryInterface: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/nlp/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          natural_language_query: query,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to process query');
      }

      const data = await response.json();
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            Query Interface
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Ask questions in natural language and get Cypher queries
          </p>
        </div>
      </div>

      <div className="card p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="query" className="block text-sm font-medium text-gray-700">
              Natural Language Query
            </label>
            <textarea
              id="query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g., Show me all traders who placed more than 100 transactions today"
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              rows={3}
            />
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="btn btn-primary"
          >
            {loading ? 'Processing...' : 'Execute Query'}
          </button>
        </form>

        {error && (
          <div className="mt-4 alert alert-danger">
            {error}
          </div>
        )}

        {results && (
          <div className="mt-6 space-y-4">
            <div className="card p-4">
              <h3 className="text-lg font-medium text-gray-900 mb-2">Generated Cypher Query</h3>
              <pre className="bg-gray-100 p-3 rounded-md text-sm overflow-x-auto">
                {results.translation.cypher_query}
              </pre>
              <p className="mt-2 text-sm text-gray-600">
                Confidence: {(results.translation.confidence * 100).toFixed(1)}%
              </p>
              <p className="mt-1 text-sm text-gray-600">
                {results.translation.explanation}
              </p>
            </div>

            <div className="card p-4">
              <h3 className="text-lg font-medium text-gray-900 mb-2">
                Results ({results.count})
              </h3>
              {results.error ? (
                <div className="alert alert-danger">
                  Query execution error: {results.error}
                </div>
              ) : results.results.length === 0 ? (
                <p className="text-gray-500">No results found</p>
              ) : (
                <div className="overflow-x-auto">
                  <pre className="bg-gray-100 p-3 rounded-md text-sm">
                    {JSON.stringify(results.results, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default QueryInterface; 