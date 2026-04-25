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
