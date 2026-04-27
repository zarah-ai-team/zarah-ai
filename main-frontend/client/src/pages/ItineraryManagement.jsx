import React, { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  ChevronDown,
  MoreVertical,
  RefreshCw,
  Trash2,
  Download,
  Eye,
  X,
} from "lucide-react";
import { listChats, createChat, deleteChat, getChatSession, updateChatMetadata } from "../services/chatService";
import ItineraryDisplay, { generateItineraryPDF } from "../components/chat/ItineraryDisplay";
import PortalMenu from "../components/common/PortalMenu";
import {
  TotalItinerariesIcon,
  SavedIcon,
  InProgressIcon,
  CompletedIcon,
  ChatPlusIcon,
} from "../components/itinerary/ItineraryIcons";

/** Per-row action menu using PortalMenu so it isn't clipped by the table's overflow-hidden. */
function RowActionMenu({ open, onToggle, onClose, items }) {
  const triggerRef = useRef(null);
  return (
    <>
      <button
        ref={triggerRef}
        onClick={onToggle}
        className="p-1 text-gray-400 hover:text-gray-700 dark:hover:text-white transition-all duration-200"
        aria-label="Actions"
      >
        <MoreVertical size={14} />
      </button>
      <PortalMenu open={open} anchorRef={triggerRef} onClose={onClose} width={172}>
        {items.map((it, i) => (
          <button
            key={i}
            onClick={() => { it.onClick(); onClose(); }}
            className={`w-full text-left flex items-center gap-2 px-3.5 py-2 text-[12.5px] transition-colors ${
              it.danger
                ? "text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                : "text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5"
            }`}
          >
            {it.icon}{it.label}
          </button>
        ))}
      </PortalMenu>
    </>
  );
}

const iconMap = {
  "clipboard-list": TotalItinerariesIcon,
  "file-edit": SavedIcon,
  "file-check": InProgressIcon,
  "check-circle": CompletedIcon,
};

function formatDateRange(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch {
    return "—";
  }
}

// Status keys stored in backend ↔ user-facing label.
// "saved" is the default state right after the user clicks Save Itinerary.
const STATUS_LABEL = {
  saved:        "Saved",
  not_started:  "Not Started",
  in_progress:  "In Progress",
  completed:    "Completed",
  // Legacy backward-compat
  draft:        "Saved",
  cancelled:    "Completed",
};

// Options shown in the dropdown — keys are what we send back to the backend.
const STATUS_OPTIONS = [
  { value: "saved",       label: "Saved",       color: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300" },
  { value: "not_started", label: "Not Started", color: "bg-gray-100  text-gray-700  dark:bg-white/10 dark:text-gray-200" },
  { value: "in_progress", label: "In Progress", color: "bg-blue-100  text-blue-800  dark:bg-blue-500/20 dark:text-blue-200" },
  { value: "completed",   label: "Completed",   color: "bg-green-100 text-green-800 dark:bg-green-500/20 dark:text-green-200" },
];

const STATUS_KEY_BY_LABEL = Object.fromEntries(STATUS_OPTIONS.map((o) => [o.label, o.value]));

function normalizeSession(s) {
  const meta = s.metadata || {};
  const statusKey = meta.status || s.status || "saved";
  return {
    id: s.session_id ?? s.id,
    name: meta.itinerary_name || s.chat_name || s.name || `Session ${s.session_id ?? s.id}`,
    group: meta.group_client_name || s.client_name || s.group || "—",
    travelDates: meta.travel_dates || s.travel_dates || (s.created_at ? formatDateRange(s.created_at) : "—"),
    travelers: meta.travelers_max ? `${meta.travelers_max} pax` : (s.travelers || (s.adults ? `${s.adults} Adults` : "—")),
    duration: meta.duration || s.duration || (s.total_nights ? `${s.total_nights} Nights` : "—"),
    estimatedCost: meta.estimated_cost || s.estimated_cost || s.total_cost || "—",
    statusKey,
    status: STATUS_LABEL[statusKey] || "Saved",
    sessionId: s.session_id ?? s.id,
    hasItinerary: s.has_saved_itinerary || false,
  };
}

const ItineraryManagement = () => {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [creating, setCreating] = useState(false);

  // Itinerary viewer modal
  const [viewItinerary, setViewItinerary] = useState(null);
  const [viewLoading, setViewLoading] = useState(false);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listChats();
      const list = Array.isArray(data) ? data : (data.chats ?? data.sessions ?? []);
      // Only show chats whose itinerary the user has explicitly saved.
      // Plain conversations stay in chat history and don't appear here.
      const saved = list.filter((s) => s.has_saved_itinerary);
      setSessions(saved.map(normalizeSession));
    } catch {
      // keep previous list on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  const stats = useMemo(() => [
    { id: 1, label: "Total Itineraries", value: sessions.length, icon: "clipboard-list", bg: "#FFFAC5" },
    { id: 2, label: "Saved",       value: sessions.filter((s) => s.statusKey === "saved").length,       icon: "file-edit",  bg: "#FFFAC5" },
    { id: 3, label: "In Progress", value: sessions.filter((s) => s.statusKey === "in_progress").length, icon: "file-check", bg: "#FFFAC5" },
    { id: 4, label: "Completed",   value: sessions.filter((s) => s.statusKey === "completed").length,   icon: "check-circle", bg: "#FFFAC5" },
  ], [sessions]);

  const filtered = useMemo(() =>
    sessions.filter((item) => {
      const matchesSearch = (item.name || "").toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === "All" || item.status === statusFilter;
      return matchesSearch && matchesStatus;
    }),
  [sessions, searchQuery, statusFilter]);

  const handleCreateNew = async () => {
    setCreating(true);
    try {
      const session = await createChat("New Itinerary");
      const sessionId = session?.session_id ?? session?.id;
      navigate(sessionId ? `/chat?session=${sessionId}` : "/chat");
    } catch {
      navigate("/chat");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (sessionId) => {
    setMenuOpenId(null);
    if (!window.confirm("Delete this itinerary session? This cannot be undone.")) return;
    try {
      await deleteChat(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch (err) {
      alert("Delete failed: " + (err.message || "Unknown error"));
    }
  };

  const handleStatusChange = async (sessionId, newStatusKey) => {
    // Optimistic update — flip the local row immediately, roll back on error.
    setSessions((prev) =>
      prev.map((s) =>
        s.sessionId === sessionId
          ? { ...s, statusKey: newStatusKey, status: STATUS_LABEL[newStatusKey] || s.status }
          : s
      )
    );
    try {
      await updateChatMetadata(sessionId, { status: newStatusKey });
    } catch (err) {
      alert("Status update failed: " + (err.message || "Unknown error"));
      fetchSessions();   // rollback by refetching the truth
    }
  };

  const loadAndView = async (sessionId) => {
    setMenuOpenId(null);
    setViewLoading(true);
    setViewItinerary("loading");
    try {
      const res = await getChatSession(sessionId);
      const chat = res.chat ?? res;
      const itinerary = chat.saved_itinerary;
      if (itinerary) {
        setViewItinerary(itinerary);
      } else {
        setViewItinerary(null);
        navigate(`/chat?session=${sessionId}`);
      }
    } catch {
      setViewItinerary(null);
    } finally {
      setViewLoading(false);
    }
  };

  const loadAndDownload = async (sessionId) => {
    setMenuOpenId(null);
    try {
      const res = await getChatSession(sessionId);
      const chat = res.chat ?? res;
      const itinerary = chat.saved_itinerary;
      if (itinerary) {
        generateItineraryPDF(itinerary);
      }
    } catch {}
  };

  return (
    <div className="animate-fadeIn" onClick={() => setMenuOpenId(null)}>

      {/* ── Itinerary viewer modal ── */}
      {viewItinerary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-gray-900/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-800">Saved Itinerary</h3>
              <button
                onClick={() => setViewItinerary(null)}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-5">
              {viewItinerary === "loading" || viewLoading ? (
                <div className="flex items-center justify-center py-16">
                  <RefreshCw size={20} className="animate-spin text-gray-400" />
                </div>
              ) : (
                <ItineraryDisplay
                  itinerary={viewItinerary}
                  sessionId={null}
                  saved={true}
                  onSave={() => {}}
                  onDiscard={() => setViewItinerary(null)}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Stats cards — wider, tighter row, smaller corner radius, lower height */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        {stats.map((stat) => {
          const Icon = iconMap[stat.icon] || TotalItinerariesIcon;
          return (
            <div
              key={stat.id}
              className="bg-white dark:bg-[#2A2929] rounded-lg border border-gray-100 dark:border-white/10 p-1.5 shadow-[0_1px_3px_rgba(0,0,0,0.03)] dark:shadow-[0_2px_10px_rgba(0,0,0,0.35)] transition-all duration-300 hover:shadow-[0_6px_16px_rgba(0,0,0,0.06)] hover:border-gray-200 dark:hover:border-[#FFDE39]/25 dark:hover:shadow-[0_6px_18px_rgba(0,0,0,0.45)]"
            >
              <div className="bg-[#FFF6B5] dark:bg-gradient-to-br dark:from-[#1F1F1F] dark:to-[#262524] dark:border dark:border-[#FFDE39]/15 rounded-md px-4 py-2.5 flex items-center justify-between">
                <div className="min-w-0">
                  <p className="text-[22px] font-bold text-[#1f1f1f] dark:text-white leading-none">{stat.value}</p>
                  <p className="text-[10.5px] text-[#1f1f1f] dark:text-gray-300 mt-1 font-medium">{stat.label}</p>
                </div>
                <Icon
                  size={28}
                  className="shrink-0 text-[#FFDE39] dark:[filter:drop-shadow(0_0_6px_rgba(255,222,57,0.35))]"
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Single white card containing controls + table */}
      <div className="bg-white dark:bg-[#2A2929] rounded-xl border border-gray-100 dark:border-white/10 overflow-hidden shadow-[0_1px_4px_rgba(0,0,0,0.03)] dark:shadow-[0_2px_14px_rgba(0,0,0,0.35)]">
        {/* Controls row — title + search + filters + CTA */}
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <h2 className="text-[15px] font-semibold text-gray-800 dark:text-white mr-1">Itinerary list</h2>

          <div className="flex items-center bg-white dark:bg-[#1F1F1F] border border-gray-200 dark:border-white/10 rounded-full px-3.5 py-1.5 w-64 focus-within:border-gray-300 dark:focus-within:border-white/20 transition-all duration-300">
            <Search size={14} className="text-gray-400 dark:text-gray-500 mr-2" />
            <input
              type="text"
              placeholder="Search history"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent outline-none text-[12.5px] text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 w-full font-poppins"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[12.5px] text-gray-500 dark:text-gray-400">Status</span>
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="appearance-none bg-white dark:bg-[#1F1F1F] border border-gray-200 dark:border-white/10 rounded-md pl-3 pr-7 py-1.5 text-[12.5px] text-gray-700 dark:text-gray-200 outline-none focus:border-gray-300 dark:focus:border-white/20 transition-all duration-300 cursor-pointer font-poppins min-w-[88px]"
              >
                <option>All</option>
                <option>Saved</option>
                <option>Not Started</option>
                <option>In Progress</option>
                <option>Completed</option>
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[12.5px] text-gray-500 dark:text-gray-400">Clients</span>
            <div className="relative">
              <select
                defaultValue="All"
                className="appearance-none bg-white dark:bg-[#1F1F1F] border border-gray-200 dark:border-white/10 rounded-md pl-3 pr-7 py-1.5 text-[12.5px] text-gray-700 dark:text-gray-200 outline-none focus:border-gray-300 dark:focus:border-white/20 transition-all duration-300 cursor-pointer font-poppins min-w-[88px]"
              >
                <option>All</option>
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none" />
            </div>
          </div>

          <button
            onClick={(e) => { e.stopPropagation(); fetchSessions(); }}
            className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-50 dark:hover:text-white dark:hover:bg-white/5 rounded-md transition-all duration-200"
            title="Refresh"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>

          <div className="flex-1" />

          <button
            onClick={handleCreateNew}
            disabled={creating}
            className="group relative overflow-hidden flex items-center gap-2 bg-[#1f1f1f] text-[#FFDE39] text-[12.5px] font-medium px-3.5 py-1.5 rounded-[8px] border border-transparent whitespace-nowrap shrink-0
                       transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]
                       hover:border-[#FFDE39]/40
                       hover:shadow-[0_0_0_1px_rgba(255,222,57,0.35),0_6px_18px_-8px_rgba(255,222,57,0.55)]
                       hover:bg-[#262524]
                       active:scale-[0.98]
                       disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {/* Shimmer sweep on hover */}
            <span
              aria-hidden
              className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/2 bg-gradient-to-r from-transparent via-[#FFDE39]/15 to-transparent translate-x-0 group-hover:translate-x-[300%] transition-transform duration-[900ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
            />
            <ChatPlusIcon
              size={16}
              className="relative shrink-0 transition-transform duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:rotate-[-8deg] group-hover:scale-110 group-hover:[filter:drop-shadow(0_0_5px_rgba(255,222,57,0.55))]"
            />
            <span className="relative">{creating ? "Creating…" : "Create New Itinerary"}</span>
          </button>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="bg-[#1f1f1f]">
                <th className="text-left px-5 py-3 font-medium text-white text-[12.5px]">Name</th>
                <th className="text-left px-5 py-3 font-medium text-white text-[12.5px]">Group</th>
                <th className="text-left px-5 py-3 font-medium text-white text-[12.5px]">Travel Dates</th>
                <th className="text-left px-5 py-3 font-medium text-white text-[12.5px]">Travelers</th>
                <th className="text-left px-5 py-3 font-medium text-white text-[12.5px]">Duration</th>
                <th className="text-left px-5 py-3 font-medium text-white text-[12.5px]">Estimated Cost</th>
                <th className="text-left px-5 py-3 font-medium text-white text-[12.5px]">Status</th>
                <th className="text-left px-5 py-3 font-medium text-white text-[12.5px]">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && sessions.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-10 text-center text-gray-400 dark:text-gray-500 text-[12.5px]">
                    Loading itineraries…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-10 text-center text-gray-400 dark:text-gray-500 text-[12.5px]">
                    No itineraries found.
                  </td>
                </tr>
              ) : (
                filtered.map((item, i) => (
                  <tr
                    key={item.id}
                    className={`${i % 2 === 0 ? "bg-white dark:bg-[#2A2929]" : "bg-[#f5f5f5] dark:bg-white/[0.02]"} hover:bg-[#FFFCE6] dark:hover:bg-[#FFDE39]/[0.06] transition-all duration-300 cursor-pointer`}
                    onClick={() => navigate(`/chat?session=${item.sessionId}`)}
                  >
                    <td className="px-5 py-3 text-[#1f1f1f] dark:text-gray-100 font-medium whitespace-nowrap max-w-[220px]">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="truncate underline underline-offset-2 decoration-[#1f1f1f]/60 dark:decoration-white/40">{item.name}</span>
                        {item.hasItinerary && (
                          <span className="text-[9.5px] font-medium text-green-700 bg-green-50 border border-green-200 dark:text-green-300 dark:bg-green-500/10 dark:border-green-500/20 px-1.5 py-0.5 rounded-full flex-shrink-0">
                            Saved
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{item.group}</td>
                    <td className="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{item.travelDates}</td>
                    <td className="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{item.travelers}</td>
                    <td className="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{item.duration}</td>
                    <td className="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{item.estimatedCost}</td>
                    <td className="px-5 py-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      {(() => {
                        const opt = STATUS_OPTIONS.find((o) => o.value === item.statusKey)
                                  || STATUS_OPTIONS[0];
                        return (
                          <div className="relative inline-block">
                            <select
                              value={item.statusKey}
                              onChange={(e) => handleStatusChange(item.sessionId, e.target.value)}
                              className={`appearance-none ${opt.color} text-[11.5px] font-medium pl-2.5 pr-7 py-1 rounded-full border-0 outline-none cursor-pointer focus:ring-2 focus:ring-[#FFDE39]/40 transition-all`}
                            >
                              {STATUS_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value} className="bg-white text-gray-800">
                                  {o.label}
                                </option>
                              ))}
                            </select>
                            <ChevronDown size={11} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 opacity-70" />
                          </div>
                        );
                      })()}
                    </td>
                    <td className="px-5 py-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <RowActionMenu
                        open={menuOpenId === item.id}
                        onToggle={() => setMenuOpenId(menuOpenId === item.id ? null : item.id)}
                        onClose={() => setMenuOpenId(null)}
                        items={[
                          {
                            label: "Open Chat",
                            onClick: () => navigate(`/chat?session=${item.sessionId}`),
                          },
                          ...(item.hasItinerary ? [
                            { icon: <Eye size={12} />,      label: "View Itinerary", onClick: () => loadAndView(item.sessionId) },
                            { icon: <Download size={12} />, label: "Download PDF",  onClick: () => loadAndDownload(item.sessionId) },
                          ] : []),
                          {
                            icon: <Trash2 size={12} />, label: "Delete", danger: true,
                            onClick: () => handleDelete(item.sessionId),
                          },
                        ]}
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ItineraryManagement;
