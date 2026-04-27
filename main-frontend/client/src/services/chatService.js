import { api } from "./api";

/** Send a message to the /api/chat conversational endpoint.
 *  `meta` is an optional dict for sideband data (e.g. { currency: "USD" })
 *  that the backend can pick up without polluting the user-visible message text. */
export async function sendChatMessage(sessionId, message, meta) {
  const body = { session_id: sessionId, message };
  if (meta && typeof meta === "object" && Object.keys(meta).length > 0) body.meta = meta;
  return api.post("/api/chat", body);
}

/** Load an existing chat session (history + metadata). */
export async function getChatSession(sessionId) {
  return api.get(`/api/chats/${sessionId}`);
}

/** List all saved chat sessions for the logged-in user. */
export async function listChats() {
  return api.get("/api/chats");
}

/** Create a new chat session. When `clientId` is set, the backend links the
 *  chat to that client and seeds the planner with their stored preferences. */
export async function createChat(chatName = "", clientId = null) {
  const body = { chat_name: chatName };
  if (clientId) body.client_id = clientId;
  return api.post("/api/chats", body);
}

/** Delete a chat session. */
export async function deleteChat(sessionId) {
  return api.delete(`/api/chats/${sessionId}`);
}

/** Update chat metadata (name, status, etc.). */
export async function updateChatMetadata(sessionId, updates) {
  return api.put(`/api/chats/${sessionId}/metadata`, updates);
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
