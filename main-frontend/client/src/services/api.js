/**
 * Base API client — all service files import from here.
 *
 * Uses the native fetch API so no extra dependency is needed.
 * Set REACT_APP_API_BASE_URL in .env (defaults to http://localhost:8000).
 */

export const API_BASE = process.env.REACT_APP_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(status, message, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function request(method, path, body, opts = {}) {
  const headers = { ...opts.headers };
  let fetchBody;

  if (body instanceof FormData) {
    // Let the browser set Content-Type with boundary
    fetchBody = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    fetchBody = JSON.stringify(body);
  }

  const token = localStorage.getItem("auth_token");
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: fetchBody,
    signal: opts.signal,
  });

  if (!res.ok) {
    let errorData;
    try { errorData = await res.json(); } catch { errorData = {}; }
    throw new ApiError(res.status, errorData.detail || `HTTP ${res.status}`, errorData);
  }

  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

export const api = {
  get:    (path, opts)        => request("GET",    path, undefined, opts),
  post:   (path, body, opts)  => request("POST",   path, body, opts),
  put:    (path, body, opts)  => request("PUT",    path, body, opts),
  delete: (path, opts)        => request("DELETE", path, undefined, opts),
  patch:  (path, body, opts)  => request("PATCH",  path, body, opts),
};

export { ApiError };
