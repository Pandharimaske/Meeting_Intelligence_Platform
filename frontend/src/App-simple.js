import React, { useState } from 'react';
import { Upload, CheckCircle, AlertCircle } from 'lucide-react';

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [message, setMessage] = useState('');
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleFileInput = (e) => {
    setSelectedFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setMessage('Please select a file first');
      return;
    }

    setLoading(true);
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch('/api/v1/upload', {
        method: 'POST',
        body: formData,
      });
      
      if (response.ok) {
        const data = await response.json();
        setJobs([...jobs, data]);
        setMessage('✅ Upload successful! Processing your meeting...');
        setSelectedFile(null);
        document.querySelector('input[type="file"]').value = '';
      } else {
        setMessage('❌ Upload failed');
      }
    } catch (error) {
      console.error('Upload error:', error);
      setMessage(`❌ Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-900 via-purple-900 to-slate-900">
      {/* Navigation */}
      <nav className="bg-slate-900/50 border-b border-slate-700 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Meeting Intelligence</h1>
            <p className="text-slate-400 text-sm">AI-Powered Analysis Platform</p>
          </div>
          <div className="text-green-400 flex items-center gap-2">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
            System Online
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl p-12 shadow-2xl">
          <div className="text-center mb-8">
            <h2 className="text-3xl font-bold text-white mb-2">Upload Meetings</h2>
            <p className="text-slate-300 text-lg">Upload Your Meeting</p>
            <p className="text-slate-400 mt-2">Upload a video, audio file, or transcript to get AI-powered insights</p>
          </div>

          {/* Upload Zone */}
          <div className="border-2 border-dashed border-slate-600 rounded-xl p-8 text-center hover:border-blue-400 transition cursor-pointer mb-6 bg-slate-700/20">
            <Upload className="w-12 h-12 mx-auto mb-4 text-blue-400" />
            <label className="block cursor-pointer">
              <span className="text-white font-semibold block mb-2">No file chosen</span>
              <span className="text-slate-400 text-sm block mb-4">Drop your file here, or click to browse</span>
              <input
                type="file"
                onChange={handleFileInput}
                className="hidden"
                accept=".mp4,.mov,.avi,.mp3,.wav,.srt,.vtt"
              />
            </label>
            {selectedFile && (
              <div className="mt-2 text-green-400 text-sm">
                ✓ {selectedFile.name}
              </div>
            )}
          </div>

          {/* File Info */}
          <div className="bg-slate-700/30 border border-slate-600 rounded-lg p-4 mb-6 text-sm text-slate-300">
            <p>Supports: MP4, MOV, AVI, MP3, WAV, SRT, VTT</p>
            <p className="text-slate-400 mt-2">Your files are processed securely and deleted after analysis. Average processing time: 2-5 minutes depending on file size.</p>
          </div>

          {/* Upload Button */}
          <button
            onClick={handleUpload}
            disabled={loading || !selectedFile}
            className="w-full bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600 disabled:from-slate-600 disabled:to-slate-600 text-white font-bold py-3 px-6 rounded-lg transition duration-300 transform hover:scale-105 disabled:cursor-not-allowed disabled:scale-100"
          >
            {loading ? 'Uploading...' : 'Upload Meeting'}
          </button>

          {/* Message */}
          {message && (
            <div className={`mt-4 p-4 rounded-lg flex items-center gap-2 ${
              message.startsWith('✅')
                ? 'bg-green-900/30 border border-green-700 text-green-300'
                : 'bg-red-900/30 border border-red-700 text-red-300'
            }`}>
              {message.startsWith('✅') ? (
                <CheckCircle className="w-5 h-5" />
              ) : (
                <AlertCircle className="w-5 h-5" />
              )}
              {message}
            </div>
          )}
        </div>

        {/* Recent Jobs */}
        {jobs.length > 0 && (
          <div className="mt-12">
            <h3 className="text-xl font-bold text-white mb-4">Recent Uploads</h3>
            <div className="space-y-2">
              {jobs.map((job, idx) => (
                <div key={idx} className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-slate-300">
                  Job {job.id || idx + 1} - {job.filename || 'Unknown'}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="text-center text-slate-400 py-8 mt-16 border-t border-slate-700">
        <p>© 2024 Meeting Intelligence Platform. Built with React & FastAPI.</p>
      </footer>
    </div>
  );
}

export default App;
