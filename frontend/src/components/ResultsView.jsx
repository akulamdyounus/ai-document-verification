import React from 'react';
import DocumentPreview from './DocumentPreview';

export default function ResultsView({ result, onReset }) {
  if (!result) return null;

  const {
    file_id,
    document_type,
    classification_confidence,
    document_classification_confidence,
    classification_method,
    classification_status,
    matched_signals = [],
    alternative_types = [],
    verification_status,
    authenticity_evidence_score = 0.0,
    manipulation_evidence_score = 0.0,
    authoritative_verification_status = 'NOT_AVAILABLE',
    authenticity_findings = [],
    manipulation_findings = [],
    risk_score,
    risk_level,
    forensic_report,
    fields,
    findings,
    decision_reasons = [],
  } = result;

  const getStatusBadge = (status) => {
    switch (status) {
      case 'Verified Authentic':
        return (
          <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
            <span>Verified Authentic</span>
          </span>
        );
      case 'Likely Genuine':
        return (
          <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
            <span>Likely Genuine</span>
          </span>
        );
      case 'Suspicious':
        return (
          <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
            <span>Suspicious</span>
          </span>
        );
      case 'Likely Fake':
        return (
          <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <span className="w-2 h-2 rounded-full bg-rose-400 inline-block" />
            <span>Likely Fake</span>
          </span>
        );
      case 'Verified Invalid':
        return (
          <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <span className="w-2 h-2 rounded-full bg-rose-400 inline-block" />
            <span>Verified Invalid</span>
          </span>
        );
      case 'Unable to Verify':
      default:
        return (
          <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <span className="w-2 h-2 rounded-full bg-sky-400 inline-block" />
            <span>Unable to Verify</span>
          </span>
        );
    }
  };

  const getRiskBadge = (level, score) => {
    const scoreText = score !== undefined && score !== null ? `(${Math.round(score * 100)}%)` : '';
    switch (level) {
      case 'High':
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400 inline-block" />
            <span>High Risk {scoreText}</span>
          </span>
        );
      case 'Medium':
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
            <span>Medium Risk {scoreText}</span>
          </span>
        );
      case 'Low':
      default:
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
            <span>Low Risk {scoreText}</span>
          </span>
        );
    }
  };

  const formatCheckTitle = (checkKey) => {
    return checkKey
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  };

  const isClassified = classification_status === 'classified';
  const confidencePercent = Math.round((classification_confidence || 0) * 100);
  const checksList = forensic_report?.checks || [];

  return (
    <div className="w-full space-y-6">
      {/* Header bar with Reset CTA */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h3 className="text-xl font-bold text-white tracking-tight">Document Analysis & Forensic Report</h3>
          <p className="text-xs text-slate-400 mt-1">
            Reference File ID: <span className="font-mono text-slate-300">{file_id}</span>
          </p>
        </div>
        <button
          onClick={onReset}
          className="inline-flex items-center justify-center space-x-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-colors"
        >
          <span>↻ Verify Another Document</span>
        </button>
      </div>

      {/* Decoupled Scoring Policy Banner */}
      <div className="p-3.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-200 flex items-start space-x-2.5">
        <span className="w-2 h-2 rounded-full bg-indigo-400 flex-shrink-0 mt-1" />
        <span>
          <strong>Operational Policy:</strong> Classification confidence indicates document format recognition only ({confidencePercent}%). Authenticity is evaluated independently from positive evidence and forensic tamper indicators.
        </span>
      </div>

      {/* Primary KPI Cards (4 Columns: Decoupled Metric Architecture) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Document Classification */}
        <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-5 backdrop-blur-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Classification
            </p>
            <div className="mt-2">
              <h4 className="text-lg font-bold text-white truncate">{document_type || 'Unknown'}</h4>
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-xl font-black text-white">{confidencePercent}%</span>
              <span className="text-xs text-slate-400">format match</span>
            </div>
          </div>
          <div className="mt-3">
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${
                isClassified
                  ? 'bg-indigo-500/10 text-indigo-300 border border-indigo-500/20'
                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
              }`}
            >
              {isClassified ? 'Format Recognized' : 'Insufficient Format Evidence'}
            </span>
            <p className="text-[10px] text-slate-500 mt-1">Not authenticity proof</p>
          </div>
        </div>

        {/* 2. Authenticity Evidence Score */}
        <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-5 backdrop-blur-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Authenticity Evidence
            </p>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-2xl font-black text-emerald-400">
                {Math.round((authenticity_evidence_score || 0) * 100)}%
              </span>
              <span className="text-xs text-slate-400">positive score</span>
            </div>
            <div className="mt-2 w-full bg-slate-700/60 rounded-full h-1.5 overflow-hidden">
              <div
                className="h-1.5 rounded-full transition-all duration-500 bg-emerald-500"
                style={{ width: `${Math.round((authenticity_evidence_score || 0) * 100)}%` }}
              />
            </div>
          </div>
          <div className="mt-3">
            <p className="text-[11px] text-slate-400">
              Corroborated credentials, legal chronology & ledger math
            </p>
          </div>
        </div>

        {/* 3. Manipulation Evidence Score */}
        <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-5 backdrop-blur-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Manipulation Evidence
            </p>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className={`text-2xl font-black ${
                (manipulation_evidence_score || 0) >= 0.40
                  ? 'text-rose-400'
                  : (manipulation_evidence_score || 0) >= 0.15
                  ? 'text-amber-400'
                  : 'text-slate-300'
              }`}>
                {Math.round((manipulation_evidence_score || 0) * 100)}%
              </span>
              <span className="text-xs text-slate-400">tamper score</span>
            </div>
            <div className="mt-2 w-full bg-slate-700/60 rounded-full h-1.5 overflow-hidden">
              <div
                className={`h-1.5 rounded-full transition-all duration-500 ${
                  (manipulation_evidence_score || 0) >= 0.40
                    ? 'bg-rose-500'
                    : (manipulation_evidence_score || 0) >= 0.15
                    ? 'bg-amber-500'
                    : 'bg-slate-500'
                }`}
                style={{ width: `${Math.round((manipulation_evidence_score || 0) * 100)}%` }}
              />
            </div>
          </div>
          <div className="mt-3">
            {getRiskBadge(risk_level || forensic_report?.risk_level || 'Low', risk_score ?? forensic_report?.risk_score ?? 0)}
          </div>
        </div>

        {/* 4. Final Verification Assessment */}
        <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-5 backdrop-blur-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Verification Assessment
            </p>
            <div className="mt-2">{getStatusBadge(verification_status)}</div>
            <div className="mt-2">
              <span className="text-[11px] text-slate-400 font-mono">
                Registry: {authoritative_verification_status || 'NOT_AVAILABLE'}
              </span>
            </div>
          </div>
          <div className="mt-3">
            <p className="text-[11px] text-slate-500">
              Conservative multi-signal evidence verdict
            </p>
          </div>
        </div>
      </div>

      {/* Verification Verdict & Evidence Breakdown Card */}
      <div
        className={`rounded-2xl p-6 border backdrop-blur-sm transition-all ${
          verification_status === 'Verified Authentic'
            ? 'bg-emerald-500/5 border-emerald-500/30'
            : verification_status === 'Likely Genuine'
            ? 'bg-emerald-500/5 border-emerald-500/30'
            : verification_status === 'Suspicious'
            ? 'bg-amber-500/5 border-amber-500/30'
            : verification_status === 'Likely Fake'
            ? 'bg-rose-500/5 border-rose-500/30'
            : verification_status === 'Verified Invalid'
            ? 'bg-rose-500/5 border-rose-500/30'
            : 'bg-slate-800/40 border-slate-700/80'
        }`}
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-700/60">
          <div>
            <h4 className="text-sm font-bold text-white uppercase tracking-wider">
              Verification: <span className="normal-case text-indigo-300">{verification_status}</span>
            </h4>
            <p className="text-xs text-slate-300 mt-1 leading-relaxed">
              {verification_status === 'Verified Authentic'
                ? 'Authoritative registry or cryptographic digital signature confirmed document authenticity.'
                : verification_status === 'Verified Invalid'
                ? 'Authoritative registry confirmed this document is invalid or revoked.'
                : verification_status === 'Likely Genuine'
                ? 'Strong positive authenticity evidence corroborates genuine origin (valid syntax, legal chronology, or reconciled ledger math) with no material tampering.'
                : verification_status === 'Suspicious'
                ? 'The document exhibits suspicious characteristics or arithmetic anomalies warranting manual review.'
                : verification_status === 'Likely Fake'
                ? 'Multiple concurring forensic anomalies and structural contradictions were detected.'
                : 'Automated forensic analysis did not detect high-severity tampering, but insufficient positive proof exists to establish authenticity.'}
            </p>
          </div>
          <div className="flex items-center space-x-2 self-start sm:self-center">
            {getStatusBadge(verification_status)}
          </div>
        </div>

        {/* Positive Authenticity Findings (if any) */}
        {authenticity_findings && authenticity_findings.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-emerald-400">
              Positive Authenticity Corroborations:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {authenticity_findings.map((f, idx) => (
                <div
                  key={idx}
                  className="flex items-start space-x-2 p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-200"
                >
                  <span className="text-emerald-400 font-bold mt-0.5 flex-shrink-0">✓</span>
                  <span>{f}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Manipulation & Forensic Anomalies (if any) */}
        {manipulation_findings && manipulation_findings.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-rose-400">
              Forensic & Tamper Anomalies:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {manipulation_findings.map((m, idx) => (
                <div
                  key={idx}
                  className="flex items-start space-x-2 p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-xs text-rose-200"
                >
                  <span className="text-rose-400 font-bold mt-0.5 flex-shrink-0">⚠</span>
                  <span>{m}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Operational Decision Reasons List */}
        {decision_reasons && decision_reasons.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className={`text-xs font-semibold uppercase tracking-wider ${
              verification_status === 'Suspicious' ? 'text-amber-300' : 'text-slate-300'
            }`}>
              Decision Basis & Operational Reasoning:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {decision_reasons.map((reason, idx) => (
                <div
                  key={idx}
                  className="flex items-start space-x-2 p-2.5 rounded-lg bg-slate-900/60 border border-slate-800/80 text-xs text-slate-300"
                >
                  <span className="text-indigo-400 font-bold mt-0.5 flex-shrink-0">•</span>
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Visual Document Preview Section */}
      <DocumentPreview
        fileId={file_id}
        title="Document Preview"
        showDetails={true}
        maxHeight="520px"
      />

      {/* Forensic Checks & Tamper Analysis Section (Phase 2B) */}
      <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 backdrop-blur-sm space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-700/60">
          <h4 className="text-sm font-semibold text-white uppercase tracking-wider">
            Forensic & Tamper Analysis
          </h4>
          <span className="text-xs text-slate-400 font-mono">
            {checksList.length} check{checksList.length === 1 ? '' : 's'} performed
          </span>
        </div>

        {checksList.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {checksList.map((checkItem, idx) => {
              const isWarning = checkItem.status === 'warning';
              const isPass = checkItem.status === 'pass';

              return (
                <div
                  key={idx}
                  className={`p-3.5 rounded-xl border transition-all ${
                    isWarning
                      ? 'bg-amber-500/5 border-amber-500/30'
                      : isPass
                      ? 'bg-slate-900/60 border-slate-800'
                      : 'bg-slate-900/40 border-slate-800/70'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`w-2 h-2 rounded-full flex-shrink-0 ${
                          isPass
                            ? 'bg-emerald-400'
                            : isWarning
                            ? 'bg-amber-400'
                            : 'bg-sky-400'
                        }`}
                      />
                      <span className="text-xs font-semibold text-white">
                        {formatCheckTitle(checkItem.check)}
                      </span>
                    </div>

                    {isWarning && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-amber-500/20 text-amber-300">
                        {checkItem.severity} Anomaly
                      </span>
                    )}
                  </div>
                  <p className="mt-1.5 text-xs text-slate-300 pl-4 leading-relaxed">
                    {checkItem.message}
                  </p>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-xs text-slate-400">Forensic analysis not available for this file.</p>
        )}

        {/* Limitations Notice */}
        <div className="mt-3 p-4 rounded-xl bg-slate-900/70 border border-slate-800 text-xs text-slate-400 space-y-1">
          <p className="font-semibold text-slate-300">
            Forensic Notice & Operational Limitations:
          </p>
          <ul className="list-disc list-inside text-[11px] text-slate-400 space-y-1 pl-1">
            <li>
              Automated forensic analysis cannot establish legal authenticity without authoritative registry verification.
            </li>
            <li>
              Compression artifacts (ELA) and metadata editing signatures are <strong>indicators only</strong> and may occur naturally via camera re-saving or messaging apps.
            </li>
            <li>
              <strong>Absence of detected anomalies is not proof of authentic origin.</strong>
            </li>
          </ul>
        </div>
      </div>

      {/* Matched Evidence Signals Section */}
      <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 backdrop-blur-sm">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-sm font-semibold text-white uppercase tracking-wider">
            Classification Evidence Signals
          </h4>
          <span className="text-xs text-slate-400 font-mono">
            {matched_signals.length} signal{matched_signals.length === 1 ? '' : 's'} verified
          </span>
        </div>

        {matched_signals && matched_signals.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {matched_signals.map((sig, idx) => (
              <span
                key={idx}
                className="inline-flex items-center px-3 py-1.5 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-xs font-medium text-indigo-200 capitalize"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-2 inline-block flex-shrink-0" />
                <span>{sig}</span>
              </span>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 text-center">
            <p className="text-xs text-slate-400">
              No distinct primary or secondary signature signals were detected for standard categories.
            </p>
          </div>
        )}

        {/* Alternative Categories when Ambiguous or Competing */}
        {alternative_types && alternative_types.length > 0 && (
          <div className="mt-4 pt-4 border-t border-slate-700/60 flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">
              Alternative candidates:
            </span>
            {alternative_types.map((alt, idx) => (
              <span
                key={idx}
                className="px-2.5 py-1 rounded-lg bg-slate-900/80 border border-slate-700 text-xs text-slate-300 font-mono"
              >
                {alt.document_type} ({Math.round(alt.confidence * 100)}%)
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Extracted Information Section */}
      <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 backdrop-blur-sm">
        <h4 className="text-sm font-semibold text-white uppercase tracking-wider mb-4">
          Extracted Document Information
        </h4>

        {fields && Object.keys(fields).length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {Object.entries(fields).map(([key, value]) => (
              <div
                key={key}
                className="bg-slate-900/60 border border-slate-800 rounded-xl p-3.5"
              >
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  {key.replace(/_/g, ' ')}
                </p>
                <p className="mt-1 text-sm font-medium text-slate-100 font-mono break-all">
                  {value === null || value === undefined ? (
                    <span className="text-slate-500 italic text-xs">Not detected</span>
                  ) : Array.isArray(value) ? (
                    value.join(', ')
                  ) : (
                    String(value)
                  )}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 text-center">
            <p className="text-xs text-slate-400">
              No specific structured fields were extracted from this document.
            </p>
          </div>
        )}
      </div>

      {/* Analysis Findings */}
      <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 backdrop-blur-sm">
        <h4 className="text-sm font-semibold text-white uppercase tracking-wider mb-4">
          Analysis Findings & Evidence Summary
        </h4>
        {findings && findings.length > 0 ? (
          <ul className="space-y-2.5">
            {findings.map((finding, idx) => (
              <li
                key={idx}
                className="text-xs sm:text-sm text-slate-300 flex items-start space-x-2.5 bg-slate-900/40 p-3 rounded-xl border border-slate-800/60"
              >
                <span className="text-indigo-400 font-bold">•</span>
                <span>{finding}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-400">No findings recorded.</p>
        )}
      </div>
    </div>
  );
}
