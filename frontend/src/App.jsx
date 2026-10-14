import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import FileUpload from './components/FileUpload';
import UploadedPreview from './components/UploadedPreview';
import ProgressStages from './components/ProgressStages';
import ResultsView from './components/ResultsView';
import ErrorAlert from './components/ErrorAlert';
import { checkHealth, uploadDocument, analyzeDocument } from './services/api';

export default function App() {
  const [backendStatus, setBackendStatus] = useState('checking');
  const [ocrAvailable, setOcrAvailable] = useState(null);
  const [error, setError] = useState(null);

  // Workflow states: 'idle' -> 'uploaded' -> 'analyzing' -> 'results'
  const [workflowState, setWorkflowState] = useState('idle');
  const [progressStep, setProgressStep] = useState(0);
  const [uploadedData, setUploadedData] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  // Check backend health on mount and periodically
  useEffect(() => {
    let isMounted = true;

    const fetchHealth = async () => {
      try {
        const data = await checkHealth();
        if (isMounted) {
          if (data && data.status === 'healthy') {
            setBackendStatus('online');
            setOcrAvailable(Boolean(data.ocr_available));
            // Dismiss connection error banner if backend is back online
            setError((prev) => (prev && prev.includes('Backend connection failed') ? null : prev));
          } else {
            setBackendStatus('offline');
            setOcrAvailable(false);
          }
        }
      } catch (err) {
        if (isMounted) {
          setBackendStatus('offline');
          setOcrAvailable(false);
          setError(
            'Backend connection failed. Make sure the FastAPI server is running on port 8000.'
          );
        }
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 10000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Handle file selection and immediate upload
  const handleFileSelect = async (file) => {
    setError(null);
    setIsUploading(true);

    try {
      const data = await uploadDocument(file);
      setUploadedData(data);
      setWorkflowState('uploaded');
    } catch (err) {
      setError(
        err.message || 'File upload failed. Make sure the FastAPI server is running on port 8000.'
      );
      setWorkflowState('idle');
    } finally {
      setIsUploading(false);
    }
  };

  // Handle analysis initiation
  const handleAnalyze = async () => {
    if (!uploadedData?.file_id) return;

    setError(null);
    setWorkflowState('analyzing');
    setProgressStep(0); // File uploaded

    // Multi-stage progress visual simulation while waiting for API
    const stageTimer1 = setTimeout(() => setProgressStep(1), 500); // Document processed
    const stageTimer2 = setTimeout(() => setProgressStep(2), 1100); // Extracting text
    const stageTimer3 = setTimeout(() => setProgressStep(3), 2000); // Identifying document
    const stageTimer4 = setTimeout(() => setProgressStep(4), 2800); // Analyzing document

    try {
      const result = await analyzeDocument(uploadedData.file_id);
      clearTimeout(stageTimer1);
      clearTimeout(stageTimer2);
      clearTimeout(stageTimer3);
      clearTimeout(stageTimer4);

      setProgressStep(5);
      setAnalysisResult(result);
      setWorkflowState('results');
    } catch (err) {
      clearTimeout(stageTimer1);
      clearTimeout(stageTimer2);
      clearTimeout(stageTimer3);
      clearTimeout(stageTimer4);
      setError(
        err.message || 'Analysis encountered an error. Make sure the FastAPI server is running on port 8000.'
      );
      setWorkflowState('uploaded');
    }
  };

  // Reset back to clean upload state
  const handleReset = () => {
    setWorkflowState('idle');
    setUploadedData(null);
    setAnalysisResult(null);
    setError(null);
    setProgressStep(0);
  };

  return (
    <div className="min-h-screen bg-[#0b0f19] flex flex-col font-sans">
      <Navbar backendStatus={backendStatus} ocrAvailable={ocrAvailable} />

      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14">
        {/* Error Alert Banner */}
        <ErrorAlert message={error} onDismiss={() => setError(null)} />

        {/* State 1: Idle (Upload Zone) */}
        {workflowState === 'idle' && (
          <div className="animate-fadeIn">
            <FileUpload
              onFileSelect={handleFileSelect}
              onError={(msg) => setError(msg)}
            />
            {isUploading && (
              <p className="text-center text-xs text-indigo-400 mt-4 animate-pulse">
                Uploading document to secure server...
              </p>
            )}
          </div>
        )}

        {/* State 2: File Uploaded & Stored (Ready for Analysis) */}
        {workflowState === 'uploaded' && (
          <div className="animate-fadeIn">
            <UploadedPreview
              uploadedData={uploadedData}
              onAnalyze={handleAnalyze}
              onReset={handleReset}
              isUploading={isUploading}
              isAnalyzing={false}
            />
          </div>
        )}

        {/* State 3: Analyzing (Multi-step Progress Tracker) */}
        {workflowState === 'analyzing' && (
          <div className="animate-fadeIn space-y-6">
            <UploadedPreview
              uploadedData={uploadedData}
              onAnalyze={() => {}}
              onReset={() => {}}
              isUploading={false}
              isAnalyzing={true}
            />
            <ProgressStages currentStepIndex={progressStep} />
          </div>
        )}

        {/* State 4: Results Dashboard */}
        {workflowState === 'results' && (
          <div className="animate-fadeIn">
            <ResultsView
              result={analysisResult}
              onReset={handleReset}
            />
          </div>
        )}
      </main>

      <footer className="border-t border-slate-800/80 py-6 text-center text-xs text-slate-500">
        AI Document Verification & Classification System
      </footer>
    </div>
  );
}
