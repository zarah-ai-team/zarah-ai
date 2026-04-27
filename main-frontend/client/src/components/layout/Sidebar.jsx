import React, { useState, useRef, useEffect } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  MessageSquarePlus,
  LayoutDashboard,
  Map,
  FileText,
  Users,
  Settings,
  HelpCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Bell,
  ChevronUp,
  LogOut,
  User,
  Sun,
  Moon,
} from "lucide-react";
import logo from "../../images/dashboard/logo.svg";
import { useAuth } from "../../contexts/AuthContext";
import { useTheme } from "../../contexts/ThemeContext";

const navItems = [
  { label: "New Chat", icon: MessageSquarePlus, path: "/chat?new=1" },
  { label: "Dashboard", icon: LayoutDashboard, path: "/" },
  { label: "Itinerary Management", icon: Map, path: "/itineraries" },
  { label: "Document Management", icon: FileText, path: "/documents" },
  { label: "Client Management", icon: Users, path: "/clients" },
];

const bottomItems = [
  { label: "Settings", icon: Settings, path: "/settings" },
];

const Sidebar = ({ showProfile = false, collapsed: collapsedProp, onToggleCollapsed }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const collapsed = collapsedProp !== undefined ? collapsedProp : internalCollapsed;
  const toggleCollapsed = onToggleCollapsed || (() => setInternalCollapsed((c) => !c));
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef(null);
  const isActive = (path) => location.pathname === path;

  const displayName  = user?.full_name || user?.username || "User";
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
      if (profileRef.current && !profileRef.current.contains(e.target)) setProfileOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const NavItem = ({ item }) => {
    const active = isActive(item.path);
    return (
      <NavLink
        to={item.path}
        title={collapsed ? item.label : undefined}
        className={`
          relative flex items-center ${collapsed ? "justify-center px-0" : "gap-3 px-3"}
          mx-2 py-2.5 rounded-lg text-xs font-medium
          transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] cursor-pointer group
          ${active
            ? "text-brand-400"
            : "text-white/90 hover:text-brand-300 hover:bg-white/5"}
        `}
      >
        {active && (
          <span className="absolute -left-2 top-1.5 bottom-1.5 w-[3px] rounded-r-full bg-[#FFDE39]" />
        )}
        <item.icon
          size={18}
          className="shrink-0 transition-transform duration-300 group-hover:scale-110"
        />
        {!collapsed && <span className="truncate">{item.label}</span>}
      </NavLink>
    );
  };

  return (
    <aside
      className={`
        relative bg-sidebar h-full flex flex-col
        rounded-2xl shadow-[0_4px_16px_rgba(0,0,0,0.08)] dark:shadow-[0_4px_20px_rgba(0,0,0,0.45)]
        transition-[width] duration-400 ease-[cubic-bezier(0.16,1,0.3,1)]
        ${collapsed ? "w-[80px]" : "w-[256px]"}
      `}
    >
      {/* Brand row + collapse toggle (inside sidebar) */}
      <div
        className={`flex items-center ${collapsed ? "flex-col gap-3 px-2" : "justify-between px-4"} py-4 overflow-hidden`}
      >
        <div className={`flex items-center ${collapsed ? "" : "gap-2.5 min-w-0"}`}>
          <img src={logo} alt="Zarah" className="w-8 h-8 shrink-0" />
          {!collapsed && (
            <h1 className="text-white font-semibold text-[15px] leading-none truncate">
              Zarah <span className="text-gray-400 font-normal">AI</span>
            </h1>
          )}
        </div>

        <button
          onClick={toggleCollapsed}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-white/70 hover:text-brand-300 hover:bg-white/5 transition-colors duration-200 cursor-pointer"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      {/* Main nav */}
      <nav className="flex-1 mt-1 space-y-0.5 overflow-y-auto overflow-x-hidden">
        {navItems.map((item) => (
          <NavItem key={item.path} item={item} />
        ))}
      </nav>

      {/* Bottom nav */}
      <div className="pb-3 space-y-0.5">
        {bottomItems.map((item) => (
          <NavItem key={item.path} item={item} />
        ))}
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          title={collapsed ? (theme === "dark" ? "Light mode" : "Dark mode") : undefined}
          aria-label="Toggle theme"
          className={`
            relative flex items-center ${collapsed ? "justify-center px-0" : "gap-3 px-3"}
            mx-2 py-2.5 rounded-lg text-xs font-medium
            transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] cursor-pointer group w-[calc(100%-1rem)]
            text-white/90 hover:text-brand-300 hover:bg-white/5
          `}
        >
          {theme === "dark"
            ? <Sun  size={18} className="shrink-0 transition-transform duration-300 group-hover:rotate-45" />
            : <Moon size={18} className="shrink-0 transition-transform duration-300 group-hover:-rotate-12" />}
          {!collapsed && (
            <span className="truncate">{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          )}
        </button>
      </div>

      {/* Notification + profile (only when topbar is hidden, e.g. on chat) */}
      {showProfile && (
        <div className="border-t border-white/10 pt-2.5 pb-3 px-2 space-y-1">
          {/* Notification bell */}
          <button
            title={collapsed ? "Notifications" : undefined}
            aria-label="Notifications"
            className={`
              relative flex items-center ${collapsed ? "justify-center px-0" : "gap-3 px-3"}
              mx-0 py-2 rounded-lg text-xs font-medium
              transition-all duration-200 cursor-pointer
              text-white/90 hover:text-brand-300 hover:bg-white/5 w-full
            `}
          >
            <span className="relative shrink-0">
              <Bell size={16} />
              <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-[#FFDE39] rounded-full" />
            </span>
            {!collapsed && <span className="truncate">Notifications</span>}
          </button>

          {/* User profile w/ logout dropdown */}
          <div className="relative" ref={profileRef}>
            <button
              onClick={() => setProfileOpen((v) => !v)}
              title={collapsed ? displayName : undefined}
              className={`
                flex items-center ${collapsed ? "justify-center px-0" : "gap-2.5 px-2"}
                py-1.5 rounded-lg
                transition-all duration-200 cursor-pointer
                hover:bg-white/5 w-full
              `}
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#FFDE39] to-[#E6C800] flex items-center justify-center text-[#1f1f1f] text-[10px] font-bold flex-shrink-0 shadow-[0_2px_6px_rgba(255,222,57,0.3)]">
                {initials || <User size={14} />}
              </div>
              {!collapsed && (
                <>
                  <div className="text-left min-w-0 flex-1 leading-tight">
                    <p className="text-[12px] font-medium text-white truncate">{displayName}</p>
                    <p className="text-[10px] text-gray-400 truncate">{displayEmail}</p>
                  </div>
                  <ChevronUp
                    size={12}
                    className={`text-gray-400 flex-shrink-0 transition-transform duration-200 ${profileOpen ? "" : "rotate-180"}`}
                  />
                </>
              )}
            </button>

            {profileOpen && (
              <div
                className={`
                  absolute z-30 bg-white rounded-lg shadow-[0_8px_24px_rgba(0,0,0,0.18)] py-1.5
                  ${collapsed
                    ? "bottom-0 left-full ml-3 w-56"
                    : "bottom-full left-0 right-0 mb-1.5"}
                `}
              >
                <div className="px-3 py-2 border-b border-gray-100">
                  <p className="text-xs font-semibold text-[#1f1f1f] truncate">{displayName}</p>
                  <p className="text-[10px] text-gray-400 truncate">{displayEmail}</p>
                </div>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-600 hover:bg-red-50 transition-colors"
                >
                  <LogOut size={13} /> Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
};

export default Sidebar;
