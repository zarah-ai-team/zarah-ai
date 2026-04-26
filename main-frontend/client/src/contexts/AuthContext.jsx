import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { getMe, logout as doLogout, getStoredUser } from "../services/authService";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getStoredUser);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then((res) => {
        const u = res.user ?? res;
        setUser(u);
        localStorage.setItem("auth_user", JSON.stringify(u));
      })
      .catch(() => {
        doLogout();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const setAuth = useCallback((userData, token) => {
    localStorage.setItem("auth_token", token);
    localStorage.setItem("auth_user", JSON.stringify(userData));
    setUser(userData);
  }, []);

  const logout = useCallback(() => {
    doLogout();
    try { localStorage.removeItem("zarah:lastChatSessionId"); } catch {}
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, setAuth, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
