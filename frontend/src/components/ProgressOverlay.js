import React from 'react';
import { Brain, X } from 'lucide-react';

function ProgressOverlay({ isVisible, status, onCancel }) {
  if (!isVisible) return null;

  const getStatusColor = (status) => {
    switch (status) {
      case 'uploading': return 'text-blue-600';
      case 'transcribing': return 'text-purple-600';
      case 'chunking': return 'text-orange-600';
      case 'indexing': return 'text-green-600';
      case 'generating_mom': return 'text-indigo-600';
      case 'completed': return 'text-green-600';
      case 'failed': return 'text-red-600';
      default: return 'text-slate-600';
    }
  };

  const getStatusMessage = (status) => {
    switch (status) {
      case 'uploading': return 'Uploading your file...';
      case 'transcribing': return 'Transcribing audio with AI...';
      case 'chunking': return 'Analyzing content structure...';
      case 'indexing': return 'Building search index...';
      case 'generating_mom': return 'Generating meeting summary...';
      case 'completed': return 'Processing complete!';
      case 'failed': return 'Processing failed';
      default: return 'Processing...';
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 p-8">
        <div className="text-center">
          {/* Animated Brain Icon */}
          <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-100 mb-6 ${status !== 'completed' && status !== 'failed' ? 'animate-pulse' : ''}`}>
            <Brain className={`h-8 w-8 ${getStatusColor(status)}`} />
          </div>

          {/* Status Title */}
          <h3 className="text-xl font-semibold text-slate-900 mb-2">
            {status?.step || getStatusMessage(status?.status)}
          </h3>

          {/* Progress Bar */}
          <div className="w-full bg-slate-200 rounded-full h-2 mb-4">
            <div
              className={`h-2 rounded-full transition-all duration-500 ${getStatusColor(status?.status)}`}
              style={{
                width: `${status?.progress || 0}%`,
                backgroundColor: status?.status === 'failed' ? '#ef4444' :
                               status?.status === 'completed' ? '#10b981' : '#3b82f6'
              }}
            ></div>
          </div>

          {/* Progress Percentage */}
          <p className="text-sm text-slate-600 mb-6">
            {status?.progress || 0}% complete
          </p>

          {/* Status-specific messages */}
          {status?.status === 'transcribing' && (
            <p className="text-xs text-slate-500 mb-4">
              This may take 2-5 minutes depending on file length
            </p>
          )}

          {status?.status === 'completed' && (
            <div className="text-green-600 font-medium">
              ✅ Your meeting analysis is ready!
            </div>
          )}

          {status?.status === 'failed' && (
            <div className="text-red-600 font-medium">
              ❌ Processing failed. Please try again.
            </div>
          )}

          {/* Cancel Button (only show if not completed/failed) */}
          {status?.status !== 'completed' && status?.status !== 'failed' && (
            <button
              onClick={onCancel}
              className="mt-4 px-4 py-2 text-sm text-slate-600 hover:text-slate-900 border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default ProgressOverlay;