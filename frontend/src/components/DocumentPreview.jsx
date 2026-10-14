import React, { useState, useEffect } from 'react';
import {
  FileText,
  Image as ImageIcon,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Eye,
  Loader2,
  Layers,
} from 'lucide-react';
import { getDocumentMetadata, getDocumentPreviewUrl } from '../services/api';

export default function DocumentPreview({
  fileId,
  metadata: initialMetadata,
  title = 'Document Preview',
  showDetails = true,
  maxHeight = '520px',
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [metadata, setMetadata] = useState(initialMetadata || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(100);
  const [isImageLoading, setIsImageLoading] = useState(true);

  // Fetch or refresh metadata if not fully provided
  useEffect(() => {
    let isMounted = true;

    async function loadMetadata() {
      if (!fileId) return;

      // If page_count is already present in initialMetadata, use it directly
      if (initialMetadata?.page_count !== undefined && initialMetadata?.file_type) {
        setMetadata(initialMetadata);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const data = await getDocumentMetadata(fileId);
        if (isMounted) {
          setMetadata(data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          console.warn('Metadata fetch failed, falling back to default preview:', err);
          // Fallback metadata so preview can still attempt loading
          setMetadata({
            file_id: fileId,
            file_type: 'pdf',
            page_count: 1,
            preview_available: true,
          });
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadMetadata();
    return () => {
      isMounted = false;
    };
  }, [fileId, initialMetadata]);

  // Reset zoom on page change
  const handlePageChange = (newPage) => {
    if (newPage < 1 || (metadata?.page_count && newPage > metadata.page_count)) return;
    setCurrentPage(newPage);
    setIsImageLoading(true);
  };

  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 25, 250));
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 25, 50));
  const handleResetZoom = () => setZoom(100);
  const handleFitScreen = () => setZoom(90);

  const isPdf =
    metadata?.file_type === 'pdf' ||
    metadata?.mime_type?.includes('pdf') ||
    metadata?.original_filename?.toLowerCase().endsWith('.pdf');

  const pageCount = metadata?.page_count || 1;
  const previewUrl = fileId ? getDocumentPreviewUrl(fileId, currentPage) : null;

  const formatFileSize = (bytes) => {
    if (!bytes) return '';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="w-full bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden backdrop-blur-md shadow-xl transition-all">
      {/* 1. Preview Header & Control Bar */}
      <div className="px-5 py-3.5 bg-slate-950/60 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            {isPdf ? <FileText className="w-4 h-4" /> : <ImageIcon className="w-4 h-4" />}
          </div>
          <div>
            <h4 className="text-xs font-semibold text-white tracking-wide uppercase flex items-center space-x-1.5">
              <span>{title}</span>
            </h4>
            {showDetails && metadata && (
              <p className="text-[11px] text-slate-400 flex items-center space-x-1.5 font-mono">
                <span>{isPdf ? 'PDF' : 'IMAGE'}</span>
                {isPdf && pageCount > 1 && <span>• {pageCount} pages</span>}
                {metadata.file_size && <span>• {formatFileSize(metadata.file_size)}</span>}
                {metadata.original_filename && (
                  <span className="truncate max-w-[140px] sm:max-w-xs text-slate-300">
                    • {metadata.original_filename}
                  </span>
                )}
              </p>
            )}
          </div>
        </div>

        {/* Zoom & Page Navigation Controls */}
        <div className="flex items-center space-x-2">
          {/* Zoom controls */}
          <div className="flex items-center bg-slate-800/80 border border-slate-700/80 rounded-xl px-1.5 py-1 text-slate-300 space-x-1">
            <button
              onClick={handleZoomOut}
              disabled={zoom <= 50}
              title="Zoom Out"
              className="p-1 hover:text-white hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-30 disabled:hover:bg-transparent"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[11px] font-mono px-1.5 min-w-[3rem] text-center font-medium">
              {zoom}%
            </span>
            <button
              onClick={handleZoomIn}
              disabled={zoom >= 250}
              title="Zoom In"
              className="p-1 hover:text-white hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-30 disabled:hover:bg-transparent"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <div className="w-[1px] h-3.5 bg-slate-700 mx-0.5" />
            <button
              onClick={handleFitScreen}
              title="Fit to Screen"
              className="p-1 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleResetZoom}
              title="Reset Zoom"
              className="p-1 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Quick Page Prev / Next for Multi-page PDF */}
          {isPdf && pageCount > 1 && (
            <div className="flex items-center bg-slate-800/80 border border-slate-700/80 rounded-xl px-2 py-1 text-xs text-slate-300 space-x-1">
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage <= 1}
                className="p-0.5 hover:text-white disabled:opacity-30"
                title="Previous Page"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-[11px] font-mono font-medium px-1">
                {currentPage} / {pageCount}
              </span>
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage >= pageCount}
                className="p-0.5 hover:text-white disabled:opacity-30"
                title="Next Page"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 2. Main Preview Viewport */}
      <div
        className="relative w-full bg-[#070b13] flex items-center justify-center overflow-auto p-4 sm:p-6"
        style={{ minHeight: '360px', maxHeight }}
      >
        {/* Loading Spinner */}
        {(loading || isImageLoading) && !error && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-950/70 backdrop-blur-sm">
            <Loader2 className="w-7 h-7 text-indigo-400 animate-spin" />
            <p className="text-xs text-slate-400 mt-2 font-mono">
              Rendering document preview...
            </p>
          </div>
        )}

        {/* Error Fallback */}
        {error ? (
          <div className="flex flex-col items-center justify-center p-8 text-center max-w-sm">
            <div className="h-12 w-12 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 mb-3">
              <AlertCircle className="w-6 h-6" />
            </div>
            <h5 className="text-sm font-semibold text-white">Preview unavailable</h5>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              Visual preview could not be generated for this document. The document will still be processed normally during analysis.
            </p>
          </div>
        ) : previewUrl ? (
          <div
            className="transition-transform duration-150 ease-out flex items-center justify-center select-none"
            style={{
              transform: `scale(${zoom / 100})`,
              transformOrigin: 'center center',
            }}
          >
            <img
              src={previewUrl}
              alt={`Document preview page ${currentPage}`}
              onLoad={() => setIsImageLoading(false)}
              onError={() => {
                setIsImageLoading(false);
                setError('Failed to load image preview');
              }}
              className="max-w-full max-h-[460px] object-contain rounded-lg shadow-2xl border border-slate-700/60 bg-white"
            />
          </div>
        ) : (
          <div className="text-xs text-slate-500">No document available to preview</div>
        )}
      </div>

      {/* 3. Multi-page PDF Page Strip & Selector */}
      {isPdf && pageCount > 1 && (
        <div className="px-5 py-3 bg-slate-950/80 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-1.5 text-xs text-slate-400 font-medium">
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
            <span>Document Pages:</span>
          </div>

          <div className="flex items-center flex-wrap gap-1.5">
            {Array.from({ length: pageCount }, (_, i) => i + 1).map((pageNum) => {
              const isActive = currentPage === pageNum;
              return (
                <button
                  key={pageNum}
                  onClick={() => handlePageChange(pageNum)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all ${
                    isActive
                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30 border border-indigo-400/30'
                      : 'bg-slate-800/80 hover:bg-slate-700 text-slate-300 border border-slate-700/60'
                  }`}
                >
                  Page {pageNum}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
