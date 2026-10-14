import React from 'react';
import { Shield, Cpu } from 'lucide-react';

export default function Navbar({ backendStatus, ocrAvailable }) {
  const isOnline = backendStatus === 'online';
  const isChecking = backendStatus === 'checking';

  return (
    <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white tracking-tight">DocVerify AI</h1>
            <p className="text-xs text-slate-400">Classification & Verification Engine</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Backend Status */}
          <div className="flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-800 border border-slate-700/60">
            <span
              className={`w-2 h-2 rounded-full ${
                isOnline
                  ? 'bg-emerald-400 animate-pulse'
                  : isChecking
                  ? 'bg-amber-400 animate-pulse'
                  : 'bg-rose-400'
              }`}
            />
            <span className="text-slate-300">
              {isOnline ? 'Backend Ready' : isChecking ? 'Connecting...' : 'Offline'}
            </span>
          </div>

          {/* OCR Engine Status */}
          <div className="hidden sm:flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-800/80 border border-slate-700/60 text-slate-300">
            <Cpu className="w-3.5 h-3.5 text-indigo-400" />
            <span>
              OCR: {ocrAvailable === true ? 'Active' : ocrAvailable === false ? 'Unavailable' : 'Checking...'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
