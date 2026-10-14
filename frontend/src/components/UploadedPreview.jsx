import React from 'react';
import { FileText, Image as ImageIcon, ArrowRight, X, CheckCircle, Zap } from 'lucide-react';
import DocumentPreview from './DocumentPreview';

export default function UploadedPreview({
  uploadedData,
  onAnalyze,
  onReset,
  isUploading,
  isAnalyzing,
}) {
  if (!uploadedData) return null;

  const isPdf =
    uploadedData.file_type?.toLowerCase().includes('pdf') ||
    uploadedData.original_filename?.toLowerCase().endsWith('.pdf') ||
    uploadedData.filename?.toLowerCase().endsWith('.pdf');

  const pageCount = uploadedData.page_count || 1;

  const formatBytes = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="w-full space-y-6">
      {/* 1. Header Bar */}
      <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-4 sm:p-5 backdrop-blur-sm flex items-center justify-between">
        <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-400">
          <CheckCircle className="w-4 h-4" />
          <span>Document Uploaded & Stored Securely</span>
        </div>
        <button
          onClick={onReset}
          disabled={isAnalyzing}
          className="text-xs text-slate-400 hover:text-rose-400 transition-colors flex items-center space-x-1.5 disabled:opacity-50"
        >
          <X className="w-3.5 h-3.5" />
          <span>Upload Different File</span>
        </button>
      </div>

      {/* 2. Visual Document Preview */}
      <DocumentPreview
        fileId={uploadedData.file_id}
        metadata={uploadedData}
        title="Document Preview"
        showDetails={true}
        maxHeight="520px"
      />

      {/* 3. Document Summary & Analysis Action Card */}
      <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 backdrop-blur-sm flex flex-col sm:flex-row sm:items-center justify-between gap-5">
        <div className="flex items-center space-x-4">
          <div className="h-12 w-12 rounded-xl bg-slate-700/50 border border-slate-600/50 flex items-center justify-center text-indigo-400 flex-shrink-0">
            {isPdf ? <FileText className="w-6 h-6" /> : <ImageIcon className="w-6 h-6" />}
          </div>
          <div>
            <h3 className="text-sm sm:text-base font-semibold text-white break-all">
              {uploadedData.original_filename || uploadedData.filename}
            </h3>
            <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-slate-400">
              <span className="px-2 py-0.5 rounded bg-slate-700 text-slate-300 font-mono font-medium">
                {isPdf ? 'PDF' : 'IMAGE'}
              </span>
              {isPdf && pageCount > 1 && (
                <>
                  <span>•</span>
                  <span>{pageCount} pages</span>
                </>
              )}
              <span>•</span>
              <span>{formatBytes(uploadedData.file_size)}</span>
              <span>•</span>
              <span className="text-slate-500 font-mono">ID: {uploadedData.file_id?.slice(0, 8)}...</span>
            </div>
          </div>
        </div>

        <button
          onClick={onAnalyze}
          disabled={isAnalyzing}
          className="inline-flex items-center justify-center space-x-2 px-7 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white font-medium text-sm transition-all shadow-lg shadow-indigo-600/30 hover:shadow-indigo-500/40 disabled:opacity-50 disabled:cursor-not-allowed group flex-shrink-0"
        >
          <Zap className="w-4 h-4 text-indigo-200 group-hover:scale-110 transition-transform" />
          <span>{isAnalyzing ? 'Analyzing Document...' : 'Analyze Document'}</span>
          <ArrowRight className="w-4 h-4 ml-1 group-hover:translate-x-1 transition-transform" />
        </button>
      </div>
    </div>
  );
}
