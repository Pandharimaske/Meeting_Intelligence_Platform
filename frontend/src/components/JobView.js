import React from 'react';
import { ArrowLeft, FileText, MessageSquare, Play, Download } from 'lucide-react';

function JobView({ job, onBack }) {
  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={onBack}
          className="flex items-center text-slate-600 hover:text-slate-900 mb-4"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to meetings
        </button>

        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 mb-2">
              {job.filename || `Meeting ${job.job_id.slice(0, 8)}`}
            </h1>
            <p className="text-slate-600">
              Status: <span className="font-medium capitalize">{job.status}</span>
            </p>
          </div>

          <div className="flex space-x-2">
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
              <Download className="h-4 w-4 inline mr-2" />
              Export
            </button>
          </div>
        </div>
      </div>

      {/* Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Transcript */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
            <div className="flex items-center mb-4">
              <FileText className="h-5 w-5 text-blue-600 mr-2" />
              <h2 className="text-lg font-semibold text-slate-900">Transcript</h2>
            </div>

            {job.transcript_available && job.transcript ? (
              <div className="space-y-4 max-h-96 overflow-y-auto">
                {job.transcript.segments?.slice(0, 10).map((segment, index) => (
                  <div key={index} className="border-l-2 border-blue-200 pl-4">
                    <div className="text-sm text-slate-500 mb-1">
                      {segment.start?.toFixed(1)}s - {segment.end?.toFixed(1)}s
                      {segment.speaker && (
                        <span className="ml-2 font-medium text-blue-600">
                          {segment.speaker}
                        </span>
                      )}
                    </div>
                    <p className="text-slate-700">{segment.text}</p>
                  </div>
                )) || <p className="text-slate-600">Transcript available</p>}
              </div>
            ) : (
              <div className="text-center py-8 text-slate-500">
                {job.status === 'completed' ? 'Transcript not available' : 'Transcript will appear here when processing is complete'}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* MoM */}
          <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
            <div className="flex items-center mb-4">
              <FileText className="h-5 w-5 text-green-600 mr-2" />
              <h2 className="text-lg font-semibold text-slate-900">Minutes of Meeting</h2>
            </div>

            {job.mom_available && job.mom ? (
              <div className="space-y-3">
                {job.mom.agenda && (
                  <div>
                    <h3 className="font-medium text-slate-900">Agenda</h3>
                    <p className="text-sm text-slate-600">{job.mom.agenda}</p>
                  </div>
                )}

                {job.mom.key_points && job.mom.key_points.length > 0 && (
                  <div>
                    <h3 className="font-medium text-slate-900">Key Points</h3>
                    <ul className="text-sm text-slate-600 list-disc list-inside">
                      {job.mom.key_points.slice(0, 3).map((point, index) => (
                        <li key={index}>{point}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-4 text-slate-500">
                {job.status === 'completed' ? 'MoM not available' : 'MoM will appear here when processing is complete'}
              </div>
            )}
          </div>

          {/* Chat */}
          <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
            <div className="flex items-center mb-4">
              <MessageSquare className="h-5 w-5 text-purple-600 mr-2" />
              <h2 className="text-lg font-semibold text-slate-900">Ask Questions</h2>
            </div>

            <div className="text-center py-4 text-slate-500">
              <p className="mb-3">Ask questions about your meeting</p>
              <button className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors">
                Start Chat
              </button>
            </div>
          </div>

          {/* Video */}
          {job.video_path && (
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
              <div className="flex items-center mb-4">
                <Play className="h-5 w-5 text-red-600 mr-2" />
                <h2 className="text-lg font-semibold text-slate-900">Video</h2>
              </div>

              <div className="text-center py-4">
                <button className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors">
                  <Play className="h-4 w-4 inline mr-2" />
                  Play Video
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default JobView;