import React from 'react';

const Alerts: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            Alerts
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage and review generated alerts
          </p>
        </div>
      </div>

      <div className="card p-6">
        <div className="text-center py-8">
          <p className="text-gray-500">No alerts at this time</p>
        </div>
      </div>
    </div>
  );
};

export default Alerts; 