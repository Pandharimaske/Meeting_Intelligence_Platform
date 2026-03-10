import React, { useState, useEffect } from 'react';
import { Brain, Upload, FileText, MessageSquare, Play, Settings } from 'lucide-react';
import UploadSection from './components/UploadSection';
import JobList from './components/JobList';
import JobView from './components/JobView';
import ProgressOverlay from './components/ProgressOverlay';
import { useWebSocket } from './hooks/useWebSocket';
import { api } from './utils/api';

function App() {
  const [currentView, setCurrentView] = useState('upload'); // 'upload', 'jobs', 'job'
  const [currentJobId, setCurrentJobId] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [currentJob, setCurrentJob] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState({});

  // WebSocket for real-time updates
  const { connect, disconnect } = useWebSocket((data) => {
    if (data.type === 'progress') {
      setProcessingStatus({
        status: data.status,
        step: data.step,
        progress: data.progress
      });

      // Update job in list
      setJobs(prevJobs =>
        prevJobs.map(job =>
          job.job_id === data.job_id
            ? { ...job, status: data.status, step: data.step, progress: data.progress }
            : job
        )
      );

      // Update current job if it's the active one
      if (currentJobId === data.job_id) {
        setCurrentJob(prev => prev ? {
          ...prev,
          status: data.status,
          step: data.step,
          progress: data.progress
        } : null);
      }

      // Handle completion
      if (data.status === 'completed') {
        setIsProcessing(false);
        loadJob(data.job_id);
      } else if (data.status === 'failed') {
        setIsProcessing(false);
      }
    }
  });

  // Load jobs on mount
  useEffect(() => {
    loadJobs();
  }, []);

  const loadJobs = async () => {
    try {
      const { jobs: jobsList } = await api.jobs();
      setJobs(jobsList);
    } catch (error) {
      console.error('Failed to load jobs:', error);
    }
  };

  const loadJob = async (jobId) => {
    try {
      const job = await api.job(jobId);
      setCurrentJob(job);
      setCurrentJobId(jobId);
      setCurrentView('job');
      connect(jobId); // Connect WebSocket for this job
    } catch (error) {
      console.error('Failed to load job:', error);
    }
  };

  const handleUpload = async (file) => {
    setIsProcessing(true);
    setProcessingStatus({ status: 'uploading', step: 'Uploading file...', progress: 5 });

    try {
      const result = await api.upload(file);
      setCurrentJobId(result.job_id);
      connect(result.job_id); // Connect WebSocket immediately
      setCurrentView('job');
      loadJob(result.job_id);
    } catch (error) {
      console.error('Upload failed:', error);
      setIsProcessing(false);
    }
  };

  const handleJobSelect = (jobId) => {
    loadJob(jobId);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-blue-600 rounded-lg">
                <Brain className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900">Meeting Intelligence</h1>
                <p className="text-sm text-slate-500">AI-Powered Analysis Platform</p>
              </div>
            </div>

            <nav className="flex space-x-1">
              <button
                onClick={() => setCurrentView('upload')}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  currentView === 'upload'
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <Upload className="h-4 w-4 inline mr-2" />
                Upload
              </button>
              <button
                onClick={() => setCurrentView('jobs')}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  currentView === 'jobs'
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <FileText className="h-4 w-4 inline mr-2" />
                Meetings
              </button>
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {currentView === 'upload' && (
          <UploadSection onUpload={handleUpload} />
        )}

        {currentView === 'jobs' && (
          <JobList jobs={jobs} onJobSelect={handleJobSelect} />
        )}

        {currentView === 'job' && currentJob && (
          <JobView job={currentJob} onBack={() => setCurrentView('jobs')} />
        )}
      </main>

      {/* Progress Overlay */}
      <ProgressOverlay
        isVisible={isProcessing}
        status={processingStatus}
        onCancel={() => setIsProcessing(false)}
      />

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 mt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between text-sm text-slate-500">
            <p>© 2024 Meeting Intelligence Platform. Built with React & FastAPI.</p>
            <div className="flex items-center space-x-4">
              <span className="flex items-center">
                <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
                System Online
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;