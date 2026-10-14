/**
 * API communication service for Document Verification System.
 * Connects to FastAPI backend via relative /api proxy or direct URL.
 */

/**
 * Normalizes the API base URL.
 * Defaults to '/api' for local Vite proxy development.
 * In production (e.g. Vercel), users set VITE_API_URL to the Render backend root
 * (e.g. 'https://my-backend.onrender.com' or 'https://my-backend.onrender.com/api').
 * This ensures the URL always ends with '/api' without double slashes.
 */
function resolveApiBase() {
  const envUrl = import.meta.env.VITE_API_URL;
  if (!envUrl || typeof envUrl !== 'string' || envUrl.trim() === '') {
    return '/api';
  }
  let cleaned = envUrl.trim().replace(/\/+$/, '');
  if (!cleaned.endsWith('/api')) {
    cleaned += '/api';
  }
  return cleaned;
}

const API_BASE = resolveApiBase();

/**
 * Safely extracts response text and parses JSON if present.
 * Prevents "Unexpected end of JSON input" errors on empty/HTML responses.
 */
async function parseResponsePayload(res) {
  const contentType = res.headers.get('content-type') || '';
  const text = await res.text();

  if (!text || text.trim() === '') {
    return { data: null, isJson: false, raw: '' };
  }

  if (contentType.includes('application/json')) {
    try {
      const data = JSON.parse(text);
      return { data, isJson: true, raw: text };
    } catch {
      return { data: null, isJson: false, raw: text };
    }
  }

  // Fallback: try parsing JSON in case content-type header was omitted
  try {
    const data = JSON.parse(text);
    return { data, isJson: true, raw: text };
  } catch {
    return { data: null, isJson: false, raw: text };
  }
}

/**
 * Safely executes HTTP requests with robust handling for:
 * - Network/connection errors
 * - Non-200 HTTP status codes
 * - Empty response bodies
 * - Unexpected HTML (e.g. proxy errors or SPA fallbacks)
 */
async function safeFetch(url, options = {}) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (netErr) {
    console.error(`Network request failed for ${url}:`, netErr);
    throw new Error('Backend connection failed. Make sure the FastAPI server is running on port 8000.');
  }

  const { data, isJson, raw } = await parseResponsePayload(res);

  // Handle non-2xx HTTP responses
  if (!res.ok) {
    if (isJson && data && data.detail) {
      const detailMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      throw new Error(detailMsg);
    }

    if (raw && (raw.includes('<!doctype') || raw.includes('<html'))) {
      throw new Error(
        `Server returned an HTML error (status ${res.status}). Make sure the FastAPI server is running on port 8000.`
      );
    }

    if (raw && raw.trim().length > 0 && raw.trim().length < 200) {
      throw new Error(`Request failed (${res.status}): ${raw.trim()}`);
    }

    throw new Error(`Request failed with status ${res.status} (${res.statusText || 'Server Error'}).`);
  }

  // Handle 2xx responses that returned unexpected HTML (e.g. SPA fallback)
  if (raw && (raw.includes('<!doctype') || raw.includes('<html'))) {
    throw new Error(
      'API endpoint returned HTML instead of JSON. Ensure the FastAPI backend is running on port 8000 and the proxy is configured.'
    );
  }

  // If response has no data
  if (!data && (!raw || raw.trim() === '')) {
    throw new Error('Server returned an empty response. Make sure the FastAPI backend is running on port 8000.');
  }

  if (!isJson) {
    throw new Error('Server response was not valid JSON.');
  }

  return data;
}

export async function checkHealth() {
  return await safeFetch(`${API_BASE}/health`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });
}

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append('file', file);

  return await safeFetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });
}

export async function analyzeDocument(fileId) {
  return await safeFetch(`${API_BASE}/analyze/${fileId}`, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
    },
  });
}

export async function getDocumentMetadata(fileId) {
  return await safeFetch(`${API_BASE}/documents/${fileId}/metadata`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });
}

export function getDocumentPreviewUrl(fileId, page = 1, thumbnail = false) {
  return `${API_BASE}/documents/${fileId}/preview?page=${page}${thumbnail ? '&thumbnail=true' : ''}`;
}

export async function fetchDocumentPreviewBlob(fileId, page = 1, thumbnail = false) {
  const url = getDocumentPreviewUrl(fileId, page, thumbnail);
  try {
    const res = await fetch(url);
    if (!res.ok) {
      const errText = await res.text();
      let msg = `Preview generation failed (${res.status})`;
      try {
        const json = JSON.parse(errText);
        if (json.detail) msg = json.detail;
      } catch {
        // fallback
      }
      throw new Error(msg);
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  } catch (err) {
    console.error('Failed to fetch document preview blob:', err);
    throw err;
  }
}
