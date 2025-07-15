import React from 'react';

const Settings: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            Settings
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Configure system settings
          </p>
        </div>
      </div>

      <div className="card p-6">
        <div className="text-center py-8">
          <p className="text-gray-500">Settings coming soon</p>
        </div>
      </div>
    </div>
  );
};

export default Settings; 