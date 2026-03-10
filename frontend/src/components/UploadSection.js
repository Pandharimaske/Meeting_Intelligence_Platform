import React, { useState, useRef } from 'react';
import { Upload, File, X, CheckCircle } from 'lucide-react';

function UploadSection({ onUpload }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFile = (file) => {
    // Validate file type
    const allowedTypes = ['video/mp4', 'video/mov', 'video/avi', 'audio/mp3', 'audio/wav', 'text/plain'];
    const allowedExtensions = ['.mp4', '.mov', '.avi', '.mp3', '.wav', '.srt', '.vtt'];

    const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));

    if (!allowedTypes.includes(file.type) && !allowedExtensions.includes(fileExtension)) {
      alert('Please select a valid file type: MP4, MOV, AVI, MP3, WAV, SRT, or VTT');
      return;
    }

    setSelectedFile(file);
  };

  const handleSubmit = async () => {
    if (!selectedFile) return;

    setUploading(true);
    try {
      await onUpload(selectedFile);
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Upload failed. Please try again.');
    } finally {
      setUploading(false);
      setSelectedFile(null);
    }
  };

  const clearFile = () => {
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-bold text-slate-900 mb-4">
          Upload Your Meeting
        </h2>
        <p className="text-lg text-slate-600">
          Upload a video, audio file, or transcript to get AI-powered insights
        </p>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8">
        {/* Upload Area */}
        <div
          className={`relative border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
            dragActive
              ? 'border-blue-500 bg-blue-50'
              : selectedFile
              ? 'border-green-500 bg-green-50'
              : 'border-slate-300 hover:border-slate-400'
          }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            accept="video/*,audio/*,.srt,.vtt"
            onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
            disabled={uploading}
          />

          {selectedFile ? (
            <div className="flex flex-col items-center">
              <CheckCircle className="h-12 w-12 text-green-500 mb-4" />
              <p className="text-lg font-medium text-slate-900 mb-2">
                {selectedFile.name}
              </p>
              <p className="text-sm text-slate-500 mb-4">
                {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
              </p>
              <button
                onClick={clearFile}
                className="flex items-center px-3 py-1 text-sm text-slate-600 hover:text-slate-900"
              >
                <X className="h-4 w-4 mr-1" />
                Remove
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center">
              <Upload className="h-12 w-12 text-slate-400 mb-4" />
              <p className="text-lg font-medium text-slate-900 mb-2">
                Drop your file here, or click to browse
              </p>
              <p className="text-sm text-slate-500">
                Supports: MP4, MOV, AVI, MP3, WAV, SRT, VTT
              </p>
            </div>
          )}
        </div>

        {/* Upload Button */}
        {selectedFile && (
          <div className="mt-6 text-center">
            <button
              onClick={handleSubmit}
              disabled={uploading}
              className={`px-8 py-3 rounded-lg font-medium transition-colors ${
                uploading
                  ? 'bg-slate-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 text-white'
              }`}
            >
              {uploading ? (
                <div className="flex items-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Processing...
                </div>
              ) : (
                'Start Processing'
              )}
            </button>
          </div>
        )}

        {/* Help Text */}
        <div className="mt-6 text-center text-sm text-slate-500">
          <p>
            Your files are processed securely and deleted after analysis.
            Average processing time: 2-5 minutes depending on file size.
          </p>
        </div>
      </div>
    </div>
  );
}

export default UploadSection;