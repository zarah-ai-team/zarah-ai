import React, { useState, useRef, useEffect } from "react";
import { Bell, ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useNavigate } from "react-router-dom";

const TopBar = ({ pageTitle = "Dashboard" }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  const displayName = user?.full_name || user?.username || "User";
  const displayEmail = user?.email || "";
  const initials = displayName
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <header className="h-[60px] bg-white rounded-xl border border-gray-100 flex items-center justify-between px-5 font-poppins shrink-0">
      {/* Left — Welcome + page title (minimal, lighter weights) */}
      <div className="min-w-0">
        <p className="text-[11px] text-gray-500 font-light leading-tight">
          Welcome,
        </p>
        <p className="text-[13px] leading-tight mt-0.5 truncate">
          <span className="font-medium text-gray-700">{displayName}</span>
          <span className="text-[#FFDE39] mx-1.5 font-normal">|</span>
          <span className="font-semibold text-[#1f1f1f]">{pageTitle}</span>
        </p>
      </div>

      {/* Right — Notification + Profile */}
      <div className="flex items-center gap-3">
        {/* Notification bell — subtle white circle */}
        <button
          className="relative w-9 h-9 rounded-full bg-white border border-gray-100 shadow-[0_1px_3px_rgba(0,0,0,0.04)] flex items-center justify-center hover:shadow-[0_2px_6px_rgba(0,0,0,0.06)] transition-shadow duration-200"
          aria-label="Notifications"
        >
          <Bell size={14} className="text-[#1f1f1f]" />
          <span className="absolute top-1.5 right-2 w-1.5 h-1.5 bg-[#FFDE39] rounded-full" />
        </button>

        {/* Profile dropdown — solid yellow circle, lighter typography, no divider */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2.5 hover:bg-gray-50 rounded-lg py-1 px-1.5 transition-colors duration-200"
          >
            <div className="w-8 h-8 rounded-full bg-[#FFDE39] flex items-center justify-center text-[#1f1f1f] text-[11px] font-semibold flex-shrink-0">
              {initials}
            </div>
            <div className="text-left hidden lg:block leading-tight">
              <p className="text-[12px] font-medium text-[#1f1f1f]">{displayName}</p>
              <p className="text-[10px] text-gray-400 font-light truncate max-w-[160px]">{displayEmail}</p>
            </div>
            <ChevronDown
              size={12}
              className={`text-gray-400 hidden lg:block transition-transform duration-200 ${menuOpen ? "rotate-180" : ""}`}
            />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-[44px] z-20 bg-white border border-gray-100 rounded-xl shadow-[0_8px_24px_rgba(0,0,0,0.08)] py-1.5 min-w-[200px]">
              <div className="px-4 py-3 border-b border-gray-100">
                <p className="text-[13px] font-medium text-[#1f1f1f] truncate">{displayName}</p>
                <p className="text-[11px] text-gray-400 font-light truncate">{displayEmail}</p>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-4 py-2 text-[12.5px] text-red-600 hover:bg-red-50 transition-colors"
              >
                <LogOut size={13} /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default TopBar;
