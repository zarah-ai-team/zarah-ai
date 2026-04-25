import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Layout from "./components/layout/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import ItineraryManagement from "./pages/ItineraryManagement";
import DocumentManagement from "./pages/DocumentManagement";
import ClientManagement from "./pages/ClientManagement";
import Placeholder from "./pages/Placeholder";

function AuthGuard() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-8 h-8 border-4 border-[#FFDE39] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<LoginGuard />} />
          <Route element={<AuthGuard />}>
            <Route element={<Layout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/chat/new" element={<Chat key="new" />} />
              <Route path="/itineraries" element={<ItineraryManagement />} />
              <Route path="/itineraries/drafts" element={<Placeholder />} />
              <Route path="/documents" element={<DocumentManagement />} />
              <Route path="/documents/upload" element={<DocumentManagement />} />
              <Route path="/clients" element={<ClientManagement />} />
              <Route path="/clients/add" element={<ClientManagement />} />
              <Route path="/settings" element={<Placeholder />} />
              <Route path="/help" element={<Placeholder />} />
              <Route path="/trips/*" element={<Placeholder />} />
              <Route path="/requests/*" element={<Placeholder />} />
              <Route path="*" element={<Placeholder />} />
            </Route>
          </Route>
        </Routes>
      </Router>
    </AuthProvider>
  );
}

// Redirect to dashboard if already logged in
function LoginGuard() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/" replace />;
  return <Login />;
}

export default App;
