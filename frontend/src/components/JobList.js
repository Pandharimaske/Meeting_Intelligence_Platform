import React from 'react';
import { FileText, Clock, CheckCircle, XCircle, Loader } from 'lucide-react';

function JobList({ jobs, onJobSelect }) {
  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'failed': return <XCircle className="h-5 w-5 text-red-500" />;
      case 'processing': return <Loader className="h-5 w-5 text-blue-500 animate-spin" />;
      default: return <Clock className="h-5 w-5 text-slate-400" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'border-green-200 bg-green-50';
      case 'failed': return 'border-red-200 bg-red-50';
      case 'processing': return 'border-blue-200 bg-blue-50';
      default: return 'border-slate-200 bg-white';
    }
  };

  if (jobs.length === 0) {
    return (
      <div className="text-center py-12">
        <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-slate-900 mb-2">No meetings yet</h3>
        <p className="text-slate-600">Upload your first meeting to get started</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-900">Your Meetings</h2>
        <p className="text-slate-600">Select a meeting to view analysis and insights</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {jobs.map((job) => (
          <div
            key={job.job_id}
            onClick={() => onJobSelect(job.job_id)}
            className={`p-6 rounded-lg border cursor-pointer transition-all hover:shadow-md ${getStatusColor(job.status)}`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center">
                {getStatusIcon(job.status)}
                <span className="ml-2 font-medium text-slate-900 capitalize">
                  {job.status}
                </span>
              </div>
              <span className="text-xs text-slate-500">
                {new Date(job.created_at).toLocaleDateString()}
              </span>
            </div>

            <h3 className="font-medium text-slate-900 mb-2 truncate">
              {job.filename || `Meeting ${job.job_id.slice(0, 8)}`}
            </h3>

            <p className="text-sm text-slate-600 mb-3">
              {job.step || 'Ready for analysis'}
            </p>

            {job.progress !== undefined && (
              <div className="w-full bg-slate-200 rounded-full h-1.5">
                <div
                  className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${job.progress}%` }}
                ></div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default JobList;