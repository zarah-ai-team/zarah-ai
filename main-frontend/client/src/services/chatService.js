import { api } from "./api";

/** Send a message to the /api/chat conversational endpoint. */
export async function sendChatMessage(sessionId, message) {
  return api.post("/api/chat", { session_id: sessionId, message });
}

/** Load an existing chat session (history + metadata). */
export async function getChatSession(sessionId) {
  return api.get(`/api/chats/${sessionId}`);
}

/** List all saved chat sessions for the logged-in user. */
export async function listChats() {
  return api.get("/api/chats");
}

/** Create a new chat session. */
export async function createChat(chatName = "") {
  return api.post("/api/chats", { chat_name: chatName });
}

/** Delete a chat session. */
export async function deleteChat(sessionId) {
  return api.delete(`/api/chats/${sessionId}`);
}

/** Clear ALL chat history for the current user.
 *  By default keeps chats that have a saved itinerary so Itinerary Management
 *  isn't wiped accidentally. Pass keepSaved=false to wipe everything. */
export async function clearAllChats({ keepSaved = true } = {}) {
  return api.delete(`/api/chats?keep_saved=${keepSaved ? "true" : "false"}`);
}

/** Update chat metadata (name, status, etc.). */
export async function updateChatMetadata(sessionId, updates) {
  return api.put(`/api/chats/${sessionId}/metadata`, updates);
}

/** List every saved itinerary (uses the dedicated /api/itineraries endpoint). */
export async function listSavedItineraries() {
  // Cache-busting query param defeats any HTTP cache between save → list.
  return api.get(`/api/itineraries?t=${Date.now()}`);
}

/** Save an itinerary explicitly via the dedicated endpoint. */
export async function saveItinerary({ sessionId, itinerary, name, status = "saved" }) {
  return api.post("/api/itineraries", {
    session_id: sessionId,
    itinerary,
    name,
    status,
  });
}

/**
 * Trigger a Word (.docx) download of a saved itinerary. Streams the file from
 * the backend, gives it the suggested filename, and clicks an invisible link.
 */
export async function downloadItineraryDocx(sessionId, suggestedName = "itinerary") {
  const token = localStorage.getItem("auth_token");
  const baseUrl =
    (typeof process !== "undefined" && process.env && process.env.REACT_APP_API_BASE_URL) ||
    "http://localhost:8000";
  const res = await fetch(`${baseUrl}/api/itineraries/${sessionId}/download?format=docx`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  const safe = String(suggestedName).replace(/[^a-zA-Z0-9_-]+/g, "_").slice(0, 60) || "itinerary";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${safe}.docx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  return true;
}

/** Generate a full itinerary from a free-text message (v2 pipeline). */
export async function generateItinerary(params) {
  const { useBackup = false, ...body } = params;
  const endpoint = useBackup
    ? "/api/v2/itinerary/generate-backup"
    : "/api/v2/itinerary/generate";
  return api.post(endpoint, body);
}

/** Check Ollama / KB health. */
export async function fetchItineraryHealth() {
  return api.get("/api/v2/itinerary/health");
}
