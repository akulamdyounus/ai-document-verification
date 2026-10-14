import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, Image, ShieldCheck, AlertCircle } from 'lucide-react';

const ALLOWED_EXTS = ['.pdf', '.jpg', '.jpeg', '.png'];
const MAX_SIZE_MB = 10;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

export default function FileUpload({ onFileSelect, onError }) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  const validateAndSelect = (file) => {
    if (!file) return;

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTS.includes(ext)) {
      onError(`Invalid file format '${ext}'. Allowed types: PDF, JPG, JPEG, PNG.`);
      return;
    }

    if (file.size === 0) {
      onError('The selected file is empty (0 bytes).');
      return;
    }

    if (file.size > MAX_SIZE_BYTES) {
      onError(`File is too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum allowed limit is ${MAX_SIZE_MB}MB.`);
      return;
    }

    onError(null);
    onFileSelect(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSelect(e.dataTransfer.files[0]);
    }
  };

  const handleBrowseClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  return (
    <div className="w-full">
      <div className="text-center mb-8">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Automated Document Intelligence</span>
        </div>
        <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
          AI Document Verification
        </h2>
        <p className="mt-2 text-base text-slate-400 max-w-xl mx-auto">
          Upload a document to identify, analyze and verify it.
        </p>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleBrowseClick}
        className={`relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-200 group ${
          isDragging
            ? 'border-indigo-500 bg-indigo-500/10 scale-[1.01]'
            : 'border-slate-700/80 hover:border-indigo-500/60 bg-slate-800/30 hover:bg-slate-800/50'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              validateAndSelect(e.target.files[0]);
            }
          }}
        />

        <div className="flex flex-col items-center justify-center space-y-4">
          <div className="h-16 w-16 rounded-2xl bg-indigo-600/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 group-hover:scale-110 group-hover:text-indigo-300 transition-all">
            <UploadCloud className="w-8 h-8" />
          </div>

          <div>
            <p className="text-base font-medium text-slate-200">
              Drag and drop your document here, or{' '}
              <span className="text-indigo-400 underline decoration-indigo-500/40 underline-offset-4 font-semibold group-hover:text-indigo-300">
                browse files
              </span>
            </p>
            <p className="text-xs text-slate-400 mt-2">
              Supports <span className="font-semibold text-slate-300">PDF, JPG, JPEG, PNG</span>
            </p>
          </div>

          <div className="flex items-center space-x-4 pt-2 text-xs text-slate-500">
            <span className="flex items-center space-x-1">
              <FileText className="w-3.5 h-3.5" />
              <span>Digital / Scanned PDFs</span>
            </span>
            <span>•</span>
            <span className="flex items-center space-x-1">
              <Image className="w-3.5 h-3.5" />
              <span>Identity & Financial Images</span>
            </span>
            <span>•</span>
            <span>Max limit: 10MB</span>
          </div>
        </div>
      </div>
    </div>
  );
}
