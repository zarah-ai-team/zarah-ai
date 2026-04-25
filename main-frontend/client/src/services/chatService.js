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
