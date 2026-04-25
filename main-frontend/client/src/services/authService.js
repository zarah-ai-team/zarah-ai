import { api } from "./api";

export async function login(username, password) {
  const data = await api.post("/api/auth/login", { username, password });
  localStorage.setItem("auth_token", data.access_token);
  localStorage.setItem("auth_user", JSON.stringify(data.user));
  return data;
}

export async function register(username, email, password, fullName = "") {
  return api.post("/api/auth/register", {
    username,
    email,
    password,
    full_name: fullName,
  });
}

export async function getMe() {
  return api.get("/api/auth/me");
}

export function logout() {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user");
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem("auth_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function isAuthenticated() {
  return !!localStorage.getItem("auth_token");
}
