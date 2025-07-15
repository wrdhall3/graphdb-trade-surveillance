// Health check utility to wait for backend to be ready

const API_BASE_URL = 'http://localhost:8000';

export const waitForBackend = async (maxRetries = 30, retryDelay = 1000) => {
  console.log('🔍 Waiting for backend to be ready...');
  
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(`${API_BASE_URL}/ready`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Backend is ready:', data.message);
        return true;
      }
    } catch (error) {
      console.log(`⏳ Backend not ready yet (attempt ${i + 1}/${maxRetries})...`);
    }
    
    // Wait before retrying
    await new Promise(resolve => setTimeout(resolve, retryDelay));
  }
  
  console.error('❌ Backend failed to start within timeout period');
  return false;
};

export const checkBackendHealth = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    if (response.ok) {
      const data = await response.json();
      return { healthy: true, data };
    }
  } catch (error) {
    console.error('Health check failed:', error);
  }
  return { healthy: false };
}; 