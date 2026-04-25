/**
 * Document management service
 *
 * Wraps the /api/v2/documents endpoints (S3 + KB pipeline).
 */
import { api, API_BASE } from "./api";

/**
 * Upload a file.
 *
 * @param {File}   file
 * @param {string} [description]
 * @param {boolean} [processForKb=true]  - Index the document for the KB
 * @param {function} [onProgress]        - Progress callback (0–100)
 */
export async function uploadDocument(file, description = "", processForKb = true, onProgress) {
  const form = new FormData();
  form.append("file", file);
  form.append("description", description);
  form.append("process_for_kb", String(processForKb));

  // Use XMLHttpRequest for upload progress tracking
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/v2/documents/upload`);

    const token = localStorage.getItem("auth_token");
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); }
        catch { resolve(xhr.responseText); }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Upload failed: HTTP ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed: HTTP ${xhr.status}`));
        }
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(form);
  });
}

/**
 * List all uploaded documents.
 *
 * @param {Object} [opts]
 * @param {number} [opts.page=1]
 * @param {number} [opts.pageSize=20]
 * @param {boolean} [opts.kbOnly=false]
 */
export async function listDocuments({ page = 1, pageSize = 20, kbOnly = false } = {}) {
  const qs = new URLSearchParams({ page, page_size: pageSize, kb_only: kbOnly });
  return api.get(`/api/v2/documents?${qs}`);
}

/**
 * Get KB processing status for a document.
 */
export async function getDocumentStatus(docId) {
  return api.get(`/api/v2/documents/${docId}/status`);
}

/**
 * Get a download URL for a document.
 */
export async function getDocumentUrl(docId) {
  return api.get(`/api/v2/documents/${docId}`);
}

/**
 * Delete a document.
 */
export async function deleteDocument(docId) {
  return api.delete(`/api/v2/documents/${docId}`);
}

/**
 * Re-run KB extraction on a stored document.
 */
export async function reprocessDocument(docId) {
  return api.post(`/api/v2/documents/${docId}/reprocess`);
}

/**
 * Storage + KB health summary.
 */
export async function fetchDocumentsHealth() {
  return api.get("/api/v2/documents/health");
}
