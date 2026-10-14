import React from 'react';
import { AlertCircle, X } from 'lucide-react';

export default function ErrorAlert({ message, onDismiss }) {
  if (!message) return null;

  return (
    <div className="mb-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 flex items-start justify-between backdrop-blur-sm animate-fadeIn">
      <div className="flex items-start space-x-3">
        <AlertCircle className="w-5 h-5 text-rose-400 mt-0.5 flex-shrink-0" />
        <div>
          <h4 className="text-sm font-semibold text-rose-200">Processing Error</h4>
          <p className="text-xs text-rose-300/90 mt-0.5 whitespace-pre-wrap">{message}</p>
        </div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="text-rose-400 hover:text-rose-200 transition-colors p-1 rounded-lg hover:bg-rose-500/20"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
