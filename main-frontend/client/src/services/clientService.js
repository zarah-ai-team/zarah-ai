/**
 * Client management service
 * Wraps /api/clients endpoints.
 */
import { api } from "./api";

export async function listClients() {
  return api.get("/api/clients");
}

export async function createClient(data) {
  return api.post("/api/clients", data);
}

export async function updateClient(clientId, data) {
  return api.put(`/api/clients/${clientId}`, data);
}

export async function deleteClient(clientId) {
  return api.delete(`/api/clients/${clientId}`);
}

export async function searchClients(query) {
  return api.get(`/api/clients/search?q=${encodeURIComponent(query)}`);
}

export async function getClientItineraries(clientId) {
  return api.get(`/api/clients/${clientId}/itineraries`);
}

export async function getClient(clientId) {
  return api.get(`/api/clients/${clientId}`);
}

/** Empty preference shape — mirrors backend `EMPTY_PREFERENCES`. */
export const EMPTY_CLIENT_PREFERENCES = {
  travel_style: "",
  budget_level: "",
  pace: "",
  hotel_categories: [],
  cuisine: [],
  activities: [],
  special_requirements: "",
  preferred_destinations: [],
  avoid: [],
  notes: "",
};

/** True when the client has at least one preference filled in — used to
 * decide whether to show "Pinned preferences" pills in the chat header. */
export function hasMeaningfulPreferences(prefs) {
  if (!prefs || typeof prefs !== "object") return false;
  return Object.values(prefs).some((v) =>
    Array.isArray(v) ? v.length > 0 : !!v
  );
}
