import React from 'react';
import { CheckCircle2, Loader2, Circle } from 'lucide-react';

export default function ProgressStages({ currentStepIndex }) {
  // Stages matching project specification
  const stages = [
    { title: 'File uploaded', description: 'Saved securely to server disk' },
    { title: 'Document processed', description: 'Format and integrity verified' },
    { title: 'Extracting text', description: 'Extracting digital text and running OCR' },
    { title: 'Identifying document', description: 'Matching layout and structural patterns' },
    { title: 'Analyzing document', description: 'Synthesizing verification findings' },
  ];

  return (
    <div className="w-full bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
      <div className="max-w-md mx-auto">
        <h4 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-6 text-center">
          Analysis in Progress
        </h4>

        <div className="space-y-6">
          {stages.map((stage, idx) => {
            const isCompleted = idx < currentStepIndex;
            const isCurrent = idx === currentStepIndex;
            const isPending = idx > currentStepIndex;

            return (
              <div key={stage.title} className="flex items-start space-x-4">
                <div className="flex-shrink-0 mt-0.5">
                  {isCompleted && (
                    <CheckCircle2 className="w-5 h-5 text-emerald-400 animate-fadeIn" />
                  )}
                  {isCurrent && (
                    <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />
                  )}
                  {isPending && (
                    <Circle className="w-5 h-5 text-slate-600" />
                  )}
                </div>

                <div className="flex-1">
                  <div className="flex items-center space-x-2">
                    <span
                      className={`text-sm font-medium ${
                        isCompleted
                          ? 'text-slate-200'
                          : isCurrent
                          ? 'text-indigo-300 font-semibold'
                          : 'text-slate-500'
                      }`}
                    >
                      {stage.title}
                    </span>
                    {isCurrent && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/20 text-indigo-300">
                        Active
                      </span>
                    )}
                  </div>
                  <p
                    className={`text-xs mt-0.5 ${
                      isCompleted || isCurrent ? 'text-slate-400' : 'text-slate-600'
                    }`}
                  >
                    {stage.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
