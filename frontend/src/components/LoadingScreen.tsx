import React, { useState, useEffect } from 'react';
import { waitForBackend } from '../utils/healthCheck';

interface LoadingScreenProps {
  onBackendReady: () => void;
}

const LoadingScreen: React.FC<LoadingScreenProps> = ({ onBackendReady }) => {
  const [status, setStatus] = useState('Initializing...');
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const initializeBackend = async () => {
      setStatus('🔍 Checking backend connection...');
      setProgress(10);
      
      // Wait for backend to be ready
      const isReady = await waitForBackend(30, 1000);
      
      if (isReady) {
        setStatus('✅ Backend is ready!');
        setProgress(100);
        setTimeout(() => {
          onBackendReady();
        }, 1000);
      } else {
        setStatus('❌ Backend failed to start. Please check the logs.');
        setProgress(0);
      }
    };

    initializeBackend();
  }, [onBackendReady]);

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center">
      <div className="text-center">
        <div className="mb-8">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        </div>
        
        <h1 className="text-2xl font-bold text-white mb-4">
          GraphDB Trade Surveillance
        </h1>
        
        <p className="text-gray-300 mb-6">
          {status}
        </p>
        
        <div className="w-64 bg-gray-700 rounded-full h-2 mx-auto">
          <div 
            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          ></div>
        </div>
        
        <p className="text-sm text-gray-400 mt-4">
          Please wait while the backend initializes...
        </p>
      </div>
    </div>
  );
};

export default LoadingScreen; 