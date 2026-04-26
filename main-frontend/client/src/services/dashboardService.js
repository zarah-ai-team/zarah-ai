import { api } from "./api";

const quickActions = [
  { id: 1, label: "New Chat", icon: "message-square-plus", route: "/chat/new" },
  { id: 2, label: "Upload Document", icon: "upload", route: "/documents/upload" },
  { id: 3, label: "Add Client", icon: "user-plus", route: "/clients/add" },
  { id: 4, label: "Itinerary Manage", icon: "clipboard-list", route: "/itineraries" },
];

const MOCK_STATS = [
  { id: 1, title: "Active Trips", value: 8, icon: "plane",
    subtitle: "4 Starting this month", actionLabel: "View All", actionRoute: "/itineraries" },
  { id: 2, title: "Draft Itineraries", value: 2, icon: "file-edit",
    subtitle: "3 need review", actionLabel: "View All", actionRoute: "/itineraries/drafts" },
  { id: 3, title: "Pending Requests", value: 4, icon: "clock",
    subtitle: "2 urgent", actionLabel: "Review", actionRoute: "/requests" },
  { id: 4, title: "Completed Trips", value: 24, icon: "briefcase",
    subtitle: "Last 30 days", actionLabel: "History", actionRoute: "/itineraries" },
];

const MOCK_ACTIVITIES = Array.from({ length: 5 }).map((_, i) => ({
  id: i + 1,
  session_id: null,
  title: "New Itinerary created",
  description: 'Manish Shah created "Oman Adventure Tour 2025"',
  time: ["29 mins ago", "1 hour ago", "3 Hours ago", "4 Hours ago", "1 Day ago"][i],
}));

const MOCK_NOTIFICATIONS = Array.from({ length: 5 }).map((_, i) => ({
  id: i + 1,
  title: "Trip Starting Soon",
  description: "Dubai Corporate Retreat starts in 3 days",
}));

function timeAgo(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  return `${Math.floor(hrs / 24)} days ago`;
}

export async function fetchDashboardStats() {
  try {
    const [chatsRes, clientsRes] = await Promise.all([
      api.get("/api/chats").catch(() => null),
      api.get("/api/clients").catch(() => null),
    ]);
    if (!chatsRes && !clientsRes) return MOCK_STATS;
    const chats = chatsRes?.chats ?? [];
    const clients = clientsRes?.clients ?? [];

    // "Active" = ongoing trips only (status: in_progress).
    // Saved / draft / completed are tracked separately so the badge isn't inflated.
    const active = chats.filter((c) => c.metadata?.status === "in_progress").length;
    const drafts = chats.filter(
      (c) => c.metadata?.status === "saved" || c.metadata?.status === "draft" || !c.metadata?.status
    ).length;
    const completed = chats.filter((c) => c.metadata?.status === "completed").length;

    return [
      { id: 1, title: "Active Trips", value: active, icon: "plane",
        subtitle: `${chats.length} total sessions`, actionLabel: "View All", actionRoute: "/itineraries" },
      { id: 2, title: "Draft Itineraries", value: drafts, icon: "file-edit",
        subtitle: "In progress", actionLabel: "View All", actionRoute: "/itineraries" },
      { id: 3, title: "Total Clients", value: clients.length, icon: "users",
        subtitle: `${clients.filter((c) => c.status === "active").length} active`, actionLabel: "View All", actionRoute: "/clients" },
      { id: 4, title: "Completed Trips", value: completed, icon: "briefcase",
        subtitle: "All time", actionLabel: "History", actionRoute: "/itineraries" },
    ];
  } catch {
    return MOCK_STATS;
  }
}

export async function fetchQuickActions() {
  return quickActions;
}

export async function fetchRecentActivities() {
  try {
    const res = await api.get("/api/chats");
    const chats = res?.chats ?? [];
    if (!chats.length) return MOCK_ACTIVITIES;
    return chats
      .slice()
      .sort((a, b) => new Date(b.updated_at ?? b.created_at) - new Date(a.updated_at ?? a.created_at))
      .slice(0, 5)
      .map((c, i) => ({
        id: i + 1,
        session_id: c.session_id,
        title: c.metadata?.status === "completed" ? "Itinerary completed" : "New Itinerary created",
        description: `${c.metadata?.group_client_name ?? "Manish Shah"} created "${c.chat_name || "Untitled"}"`,
        time: timeAgo(c.updated_at ?? c.created_at),
      }));
  } catch {
    return MOCK_ACTIVITIES;
  }
}

export async function fetchNotifications() {
  return MOCK_NOTIFICATIONS;
}

export async function markAllNotificationsRead() {
  return { success: true };
}
