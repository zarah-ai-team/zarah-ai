import React, { useState, useMemo, useEffect, useCallback } from "react";
import {
  Search,
  ChevronDown,
  UserPlus,
  User,
  Users,
  UserCheck,
  Phone,
  Mail,
  MapPin,
  Plane,
  Pencil,
  Trash2,
  MoreVertical,
  ArrowLeft,
  Upload,
  RefreshCw,
  Star,
  Crown,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import {
  listClients,
  createClient,
  deleteClient,
} from "../services/clientService";

const INITIALS_COLORS = [
  "#FFDE39", "#93C5FD", "#FCA5A5", "#86EFAC",
  "#C4B5FD", "#FCD34D", "#6EE7B7", "#F9A8D4",
];

function getInitials(name = "") {
  const words = name.trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function getColor(name = "") {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return INITIALS_COLORS[Math.abs(hash) % INITIALS_COLORS.length];
}

function timeAgoFromDate(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / 86400000);
  if (days < 1) return "Today";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} month${months > 1 ? "s" : ""} ago`;
  const years = Math.floor(months / 12);
  return `${years} year${years > 1 ? "s" : ""} ago`;
}

// Map raw API client to display shape
function normalizeClient(c) {
  const company = c.company_name ?? c.company ?? "";
  const pc = c.primary_contact ?? {};
  return {
    id: c.id ?? c.client_id,
    company,
    type: c.client_type ?? c.type ?? "",
    isVIP: c.is_vip ?? c.isVIP ?? false,
    status: c.status ?? "Active",
    contact: pc.full_name ?? c.full_name ?? c.contact_name ?? c.contact ?? "",
    phone: pc.phone ?? c.phone ?? c.contact_phone ?? "",
    email: pc.email ?? c.email ?? c.contact_email ?? "",
    location: [c.city, c.country].filter(Boolean).join(", ") || c.location || "",
    trips: Array.isArray(c.itineraries) ? c.itineraries.length : (c.trip_count ?? c.trips ?? 0),
    addedAgo: timeAgoFromDate(c.created_at ?? c.added_at),
    initials: getInitials(company),
    initialsColor: getColor(company),
  };
}

/* ---- Controlled form input ---- */
const FormInput = ({ label, placeholder, type = "text", value, onChange }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
    <input
      type={type}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-gray-700 placeholder-gray-400 outline-none focus:border-gray-400 transition-all duration-300 font-poppins bg-white"
    />
  </div>
);

/* ---- Controlled form select ---- */
const FormSelect = ({ label, placeholder, options = [], value, onChange }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none w-full border border-gray-200 rounded-lg px-3 py-2.5 pr-8 text-sm text-gray-700 outline-none focus:border-gray-400 transition-all duration-300 cursor-pointer font-poppins bg-white"
      >
        <option value="">{placeholder}</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
      <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
    </div>
  </div>
);

const EMPTY_FORM = {
  companyName: "", clientType: "", status: "Active", isVIP: false,
  contactName: "", contactEmail: "", contactPhone: "",
  secContactName: "", secContactEmail: "", secContactPhone: "",
  country: "", city: "", address: "",
  industry: "", leadSource: "", notes: "",
};

const ClientManagement = () => {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [showAddForm, setShowAddForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(null);

  const setField = (key) => (val) => setForm((f) => ({ ...f, [key]: val }));

  const fetchClients = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listClients();
      const list = Array.isArray(data) ? data : (data.clients ?? []);
      setClients(list.map(normalizeClient));
    } catch {
      // keep previous list on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchClients(); }, [fetchClients]);

  const stats = useMemo(() => [
    {
      id: 1,
      label: "Total Clients",
      value: clients.length,
      icon: Users,
      accent: "#FFDE39",
      tint: "#FFFCE6",
      iconBg: "#FFF6B5",
      iconColor: "#8A6800",
      decoFrom: "#FFDE39",
      decoTo: "#FFEC85",
      delta: "+12%",
    },
    {
      id: 2,
      label: "Active",
      value: clients.filter((c) => c.status === "Active").length,
      icon: UserCheck,
      accent: "#E6C800",
      tint: "#FFFAC5",
      iconBg: "#FFEC85",
      iconColor: "#7A5C00",
      decoFrom: "#E6C800",
      decoTo: "#FFDE39",
      delta: "+8%",
    },
    {
      id: 3,
      label: "VIP",
      value: clients.filter((c) => c.isVIP).length,
      icon: Crown,
      accent: "#FBEC5D",
      tint: "#FFF9D6",
      iconBg: "#FFF690",
      iconColor: "#8A6800",
      decoFrom: "#FBEC5D",
      decoTo: "#FFF690",
      delta: "+3%",
    },
    {
      id: 4,
      label: "New This Month",
      value: clients.filter((c) => {
        const created = c.addedAgo;
        return created === "Today" || created.includes("day");
      }).length,
      icon: Sparkles,
      accent: "#F5C84A",
      tint: "#FFF4D6",
      iconBg: "#FFE99A",
      iconColor: "#704D00",
      decoFrom: "#F5C84A",
      decoTo: "#FFDE39",
      delta: "+24%",
    },
  ], [clients]);

  const filtered = useMemo(() =>
    clients.filter((c) => {
      const matchesSearch =
        c.company.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.contact.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesType = typeFilter === "All" || c.type === typeFilter;
      const matchesStatus = statusFilter === "All" || c.status === statusFilter;
      return matchesSearch && matchesType && matchesStatus;
    }),
  [clients, searchQuery, typeFilter, statusFilter]);

  const handleDelete = async (clientId) => {
    if (!window.confirm("Delete this client? This cannot be undone.")) return;
    try {
      await deleteClient(clientId);
      setClients((prev) => prev.filter((c) => c.id !== clientId));
    } catch (err) {
      alert("Delete failed: " + (err.message || "Unknown error"));
    }
  };

  const handleSave = async () => {
    if (!form.companyName.trim()) {
      setFormError("Company name is required.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const payload = {
        company_name: form.companyName,
        client_type: (form.clientType || "Corporate").toLowerCase(),
        status: (form.status || "active").toLowerCase(),
        full_name: form.contactName,
        email: form.contactEmail,
        phone: form.contactPhone,
        secondary_contact: form.secContactName ? {
          full_name: form.secContactName,
          email: form.secContactEmail,
          phone: form.secContactPhone,
        } : null,
        country: form.country,
        city: form.city,
        address: form.address,
        industry: (form.industry || "Other").toLowerCase(),
        lead_source: form.leadSource,
        notes: form.notes,
      };
      const res = await createClient(payload);
      const created = res.client ?? res;
      setClients((prev) => [normalizeClient(created), ...prev]);
      setForm(EMPTY_FORM);
      setShowAddForm(false);
    } catch (err) {
      setFormError(err.message || "Failed to save client.");
    } finally {
      setSaving(false);
    }
  };

  // ============================
  // ADD CLIENT FORM
  // ============================
  if (showAddForm) {
    return (
      <div className="animate-fadeIn">
        <div className="flex items-center justify-between mb-8">
          <button
            onClick={() => { setShowAddForm(false); setFormError(null); setForm(EMPTY_FORM); }}
            className="flex items-center gap-2 text-gray-800 hover:text-gray-600 transition-all duration-300 group"
          >
            <ArrowLeft size={20} className="group-hover:-translate-x-0.5 transition-transform duration-300" />
            <span className="text-lg font-semibold">Add Client</span>
          </button>
          <button className="flex items-center gap-2 bg-dark-300 text-white text-sm font-medium px-5 py-2.5 rounded-lg shadow-[0_1px_4px_rgba(0,0,0,0.04)] hover:bg-dark-200 hover:shadow-[0_4px_12px_rgba(0,0,0,0.06)] hover:-translate-y-0.5 transition-all duration-300">
            <Upload size={16} className="text-[#FFDE39]" />
            Upload Excel
          </button>
        </div>

        <div className="space-y-6 pb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <FormInput label="Company Name" placeholder="Enter name" value={form.companyName} onChange={setField("companyName")} />
            <FormSelect label="Client Type" placeholder="Select Type" options={["Corporate", "Leisure", "MICE", "DMC"]} value={form.clientType} onChange={setField("clientType")} />
            <FormSelect label="Status" placeholder="Active" options={["Active", "Inactive"]} value={form.status} onChange={setField("status")} />
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.isVIP}
              onChange={(e) => setField("isVIP")(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-[#FFDE39] focus:ring-[#FFDE39] cursor-pointer"
            />
            <span className="text-sm text-gray-700">Mark as VIP Client</span>
          </label>

          <div className="bg-gray-50 rounded-xl p-5 border border-gray-100/80">
            <h3 className="text-base font-semibold text-gray-800 mb-4">Primary Contact</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <FormInput label="Full Name" placeholder="Contact person name" value={form.contactName} onChange={setField("contactName")} />
              <FormInput label="Email" placeholder="Contact@company.com" type="email" value={form.contactEmail} onChange={setField("contactEmail")} />
              <FormInput label="Phone" placeholder="+91 XXXXX XXXXX" type="tel" value={form.contactPhone} onChange={setField("contactPhone")} />
            </div>
          </div>

          <div className="bg-gray-50 rounded-xl p-5 border border-gray-100/80">
            <div className="flex items-center gap-3 mb-4">
              <h3 className="text-base font-semibold text-gray-800">Secondary Contact</h3>
              <span className="text-sm text-gray-400 italic">Optional</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <FormInput label="Full Name" placeholder="Secondary Contact name" value={form.secContactName} onChange={setField("secContactName")} />
              <FormInput label="Email" placeholder="Secondary@company.com" type="email" value={form.secContactEmail} onChange={setField("secContactEmail")} />
              <FormInput label="Phone" placeholder="+91 XXXXX XXXXX" type="tel" value={form.secContactPhone} onChange={setField("secContactPhone")} />
            </div>
          </div>

          <div className="bg-gray-50 rounded-xl p-5 border border-gray-100/80">
            <h3 className="text-base font-semibold text-gray-800 mb-4">Company Address</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <FormSelect label="Country" placeholder="Select Country" options={["India", "United States", "United Kingdom", "UAE", "Singapore", "Australia"]} value={form.country} onChange={setField("country")} />
              <FormSelect label="City" placeholder="e.g., Mumbai" options={["Mumbai", "Delhi", "Bangalore", "Pune", "Hyderabad", "Chennai"]} value={form.city} onChange={setField("city")} />
              <FormInput label="Address" placeholder="Street Address" value={form.address} onChange={setField("address")} />
            </div>
          </div>

          <div className="bg-gray-50 rounded-xl p-5 border border-gray-100/80">
            <h3 className="text-base font-semibold text-gray-800 mb-4">Additional Information</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <FormSelect label="Industry" placeholder="Select Industry" options={["Travel", "Technology", "Finance", "Healthcare", "Education", "Manufacturing"]} value={form.industry} onChange={setField("industry")} />
              <FormSelect label="Lead Source" placeholder="Select Source" options={["Website", "Referral", "Social Media", "Cold Call", "Exhibition"]} value={form.leadSource} onChange={setField("leadSource")} />
              <FormInput label="Notes" placeholder="Any additional notes.." value={form.notes} onChange={setField("notes")} />
            </div>
          </div>

          {formError && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-4 py-3">
              {formError}
            </p>
          )}

          <div className="flex justify-end pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-dark-300 text-white text-sm font-medium px-8 py-2.5 rounded-lg shadow-[0_1px_4px_rgba(0,0,0,0.04)] hover:bg-dark-200 hover:shadow-[0_4px_12px_rgba(0,0,0,0.06)] hover:-translate-y-0.5 transition-all duration-300 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {saving ? "Saving…" : "Save Client"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ============================
  // CLIENT LIST VIEW
  // ============================
  return (
    <div className="animate-fadeIn">
      {/* Stats cards — premium themed cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.id}
              className="group relative bg-white rounded-xl border border-gray-100 overflow-hidden px-3.5 py-2.5 shadow-[0_2px_8px_rgba(0,0,0,0.04)] transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-1 hover:shadow-[0_10px_24px_rgba(0,0,0,0.06)]"
            >
              {/* Decorative gradient blob (top-right) */}
              <div
                className="absolute -top-6 -right-6 w-24 h-24 rounded-full blur-2xl opacity-40 transition-opacity duration-500 group-hover:opacity-70 pointer-events-none"
                style={{ background: `radial-gradient(circle at center, ${stat.decoFrom} 0%, ${stat.decoTo} 60%, transparent 100%)` }}
              />

              {/* Soft tint base */}
              <div
                className="absolute inset-0 opacity-50 pointer-events-none"
                style={{ background: `linear-gradient(135deg, ${stat.tint} 0%, transparent 60%)` }}
              />

              {/* Bottom accent line */}
              <div
                className="absolute bottom-0 left-3 right-3 h-[2px] rounded-full opacity-60 transition-opacity duration-500 group-hover:opacity-100"
                style={{ background: `linear-gradient(to right, transparent, ${stat.accent}, transparent)` }}
              />

              <div className="relative flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[22px] font-bold text-[#1f1f1f] leading-none tracking-tight">
                    {stat.value}
                  </p>
                  <p className="text-[10px] text-gray-500 mt-1 font-medium uppercase tracking-[0.06em]">
                    {stat.label}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  <div
                    className="w-7 h-7 rounded-md flex items-center justify-center shadow-[0_2px_6px_rgba(0,0,0,0.06)] transition-transform duration-500 group-hover:scale-105 group-hover:rotate-3"
                    style={{ backgroundColor: stat.iconBg }}
                  >
                    <Icon size={13} strokeWidth={2.2} style={{ color: stat.iconColor }} />
                  </div>
                  <span
                    className="flex items-center gap-0.5 text-[9px] font-semibold px-1 py-0.5 rounded"
                    style={{ color: stat.iconColor, backgroundColor: stat.iconBg }}
                  >
                    <TrendingUp size={8} strokeWidth={2.5} />
                    {stat.delta}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Single white card containing controls + cards */}
      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden shadow-[0_1px_4px_rgba(0,0,0,0.03)]">
        {/* Controls row */}
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <h2 className="text-[15px] font-semibold text-gray-800 mr-1">Clients</h2>

          <div className="flex items-center bg-white border border-gray-200 rounded-full px-3.5 py-1.5 w-64 focus-within:border-gray-300 transition-all duration-300">
            <Search size={14} className="text-gray-400 mr-2" />
            <input
              type="text"
              placeholder="Search history"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent outline-none text-[12.5px] text-gray-700 placeholder-gray-400 w-full font-poppins"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[12.5px] text-gray-500">All Type</span>
            <div className="relative">
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="appearance-none bg-white border border-gray-200 rounded-md pl-3 pr-7 py-1.5 text-[12.5px] text-gray-700 outline-none focus:border-gray-300 transition-all duration-300 cursor-pointer font-poppins min-w-[88px]"
              >
                <option>All</option>
                <option>Corporate</option>
                <option>Leisure</option>
                <option>MICE</option>
                <option>DMC</option>
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[12.5px] text-gray-500">Status</span>
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="appearance-none bg-white border border-gray-200 rounded-md pl-3 pr-7 py-1.5 text-[12.5px] text-gray-700 outline-none focus:border-gray-300 transition-all duration-300 cursor-pointer font-poppins min-w-[88px]"
              >
                <option>All</option>
                <option>Active</option>
                <option>Inactive</option>
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          </div>

          <button
            onClick={fetchClients}
            className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-50 rounded-md transition-all duration-200"
            title="Refresh"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>

          <div className="flex-1" />

          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 bg-[#1f1f1f] text-white text-[12.5px] font-medium px-4 py-2 rounded-md hover:bg-[#2A2929] transition-all duration-300"
          >
            <UserPlus size={14} className="text-[#FFDE39]" />
            Add Client
          </button>
        </div>

        {/* Card grid / empty state */}
        <div className="px-4 pb-4 pt-1">
          {loading && clients.length === 0 ? (
            <div className="py-20 text-center text-gray-400 text-[13px]">Loading clients…</div>
          ) : filtered.length === 0 ? (
            <div className="py-24 text-center text-gray-400 text-[13px]">No clients found.</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map((client) => (
                <div
                  key={client.id}
                  className="group relative bg-white rounded-2xl overflow-hidden border border-gray-100 shadow-[0_2px_8px_rgba(0,0,0,0.04)] transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-1 hover:shadow-[0_12px_32px_rgba(0,0,0,0.08)] hover:border-[#FFDE39]/40"
                >
                  {/* Decorative yellow corner accent */}
                  <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-[#FFDE39]/15 to-transparent rounded-bl-full pointer-events-none transition-opacity duration-500 group-hover:opacity-80" />

                  {/* VIP top stripe */}
                  {client.isVIP && (
                    <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-[#FFDE39] via-[#FFEC85] to-[#FFDE39]" />
                  )}

                  {/* Header — premium avatar + company + status */}
                  <div className="relative flex items-start gap-3 px-4 pt-4 pb-3">
                    <div className="relative flex-shrink-0">
                      <div
                        className="w-12 h-12 rounded-xl flex items-center justify-center text-[15px] font-bold text-[#1f1f1f] shadow-[0_4px_10px_rgba(0,0,0,0.10)] transition-transform duration-500 group-hover:scale-105"
                        style={{
                          background: `linear-gradient(135deg, ${client.initialsColor} 0%, ${client.initialsColor}CC 100%)`,
                        }}
                      >
                        {client.initials}
                      </div>
                      {client.isVIP && (
                        <span className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-gradient-to-br from-[#FFDE39] to-[#E6C800] flex items-center justify-center shadow-[0_2px_6px_rgba(230,200,0,0.45)] ring-2 ring-white">
                          <Star size={10} className="text-[#1f1f1f]" fill="#1f1f1f" />
                        </span>
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <p className="text-[14px] font-bold text-[#1f1f1f] truncate leading-tight">{client.company}</p>
                      <p className="text-[10px] text-gray-500 uppercase tracking-[0.08em] mt-1 font-semibold">{client.type || "Client"}</p>
                    </div>

                    <span className={`flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full flex-shrink-0 ${
                      client.status === "Active"
                        ? "bg-green-50 text-green-700 border border-green-100"
                        : "bg-red-50 text-red-600 border border-red-100"
                    }`}>
                      <span className={`relative flex w-1.5 h-1.5`}>
                        {client.status === "Active" && (
                          <span className="absolute inline-flex w-full h-full rounded-full bg-green-400 opacity-75 animate-ping" />
                        )}
                        <span className={`relative inline-flex w-1.5 h-1.5 rounded-full ${client.status === "Active" ? "bg-green-500" : "bg-red-500"}`} />
                      </span>
                      {client.status}
                    </span>
                  </div>

                  {/* Body — contact info as elegant rows with icon chips */}
                  <div className="relative px-4 pb-3 space-y-1.5">
                    {[
                      { icon: User,   label: client.contact,  empty: "—" },
                      { icon: Mail,   label: client.email,    empty: "—" },
                      { icon: Phone,  label: client.phone,    empty: "—" },
                      { icon: MapPin, label: client.location, empty: "—" },
                    ].map(({ icon: Icon, label, empty }, i) => (
                      <div key={i} className="flex items-center gap-2.5 text-[12px] text-gray-700 min-w-0">
                        <div className="w-6 h-6 rounded-md bg-gray-50 border border-gray-100 flex items-center justify-center flex-shrink-0 transition-colors duration-300 group-hover:bg-[#FFFCE6] group-hover:border-[#FFDE39]/30">
                          <Icon size={11} className="text-gray-500 transition-colors duration-300 group-hover:text-[#8A6800]" />
                        </div>
                        <span className="truncate">{label || empty}</span>
                      </div>
                    ))}
                  </div>

                  {/* Footer — trips chip, added time, actions */}
                  <div className="relative flex items-center justify-between px-4 py-2.5 border-t border-gray-100 bg-gradient-to-r from-gray-50/60 to-transparent">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="flex items-center gap-1 px-2 py-0.5 bg-white border border-[#FFDE39]/40 rounded-md shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                        <Plane size={10} className="text-[#E6C800]" />
                        <span className="text-[11px] font-bold text-[#1f1f1f]">{client.trips}</span>
                        <span className="text-[10px] text-gray-500">Trips</span>
                      </div>
                      <span className="text-[10px] text-gray-400 truncate hidden sm:inline">· {client.addedAgo}</span>
                    </div>
                    <div className="flex items-center gap-0.5 flex-shrink-0">
                      <button
                        title="Edit"
                        className="p-1.5 text-gray-400 hover:text-[#1f1f1f] hover:bg-white rounded-md transition-all duration-200"
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        onClick={() => handleDelete(client.id)}
                        title="Delete"
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-white rounded-md transition-all duration-200"
                      >
                        <Trash2 size={12} />
                      </button>
                      <button
                        title="More"
                        className="p-1.5 text-gray-400 hover:text-[#1f1f1f] hover:bg-white rounded-md transition-all duration-200"
                      >
                        <MoreVertical size={12} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ClientManagement;
