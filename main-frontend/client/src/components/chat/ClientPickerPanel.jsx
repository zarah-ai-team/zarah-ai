import React, { useEffect, useMemo, useState } from "react";
import { Search, Users, Star, Crown, ArrowRight, X } from "lucide-react";
import { listClients, hasMeaningfulPreferences } from "../../services/clientService";

/**
 * Inline pre-chat panel that asks "who is this trip for?" before the user
 * starts a fresh itinerary. Picking a client links the chat to them and seeds
 * the planner with their stored preferences. The "Skip" path keeps the
 * existing no-preferences behaviour intact.
 */
export default function ClientPickerPanel({ onPick, onSkip, busy }) {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listClients()
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res) ? res : (res.clients ?? []);
        setClients(list);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || "Failed to load clients");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    if (!query.trim()) return clients;
    const q = query.toLowerCase();
    return clients.filter((c) => {
      const company = (c.company_name ?? c.company ?? "").toLowerCase();
      const contact = (c.primary_contact?.full_name ?? c.contact ?? "").toLowerCase();
      return company.includes(q) || contact.includes(q);
    });
  }, [clients, query]);

  const summarisePrefs = (prefs) => {
    if (!hasMeaningfulPreferences(prefs)) return "No preferences set";
    const parts = [];
    if (prefs.travel_style) parts.push(prefs.travel_style);
    if (prefs.pace) parts.push(`${prefs.pace} pace`);
    if (Array.isArray(prefs.activities) && prefs.activities.length) {
      parts.push(prefs.activities.slice(0, 2).join(" / "));
    }
    return parts.slice(0, 3).join(" · ") || "Preferences set";
  };

  return (
    <div className="mx-auto w-full max-w-[640px] animate-fadeIn">
      <div className="bg-white dark:bg-[#2A2929] border border-gray-100 dark:border-white/10 rounded-2xl shadow-[0_4px_18px_rgba(0,0,0,0.05)] dark:shadow-[0_4px_24px_rgba(0,0,0,0.4)] overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-100 dark:border-white/10">
          <div className="w-9 h-9 rounded-lg bg-[#FFDE39] flex items-center justify-center shrink-0 shadow-[0_2px_8px_rgba(255,222,57,0.4)]">
            <Users size={16} className="text-[#1f1f1f]" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-[14px] font-semibold text-[#1f1f1f] dark:text-white">Who is this trip for?</h3>
            <p className="text-[11.5px] text-gray-500 dark:text-gray-400 mt-0.5">
              Pick a client and I'll use their saved preferences to shape the itinerary.
            </p>
          </div>
          <button
            type="button"
            onClick={onSkip}
            disabled={busy}
            className="text-[11.5px] font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-white px-2.5 py-1 rounded-md hover:bg-gray-50 dark:hover:bg-white/5 transition-colors flex items-center gap-1 disabled:opacity-50"
          >
            Skip <X size={12} />
          </button>
        </div>

        {/* Search */}
        <div className="px-5 pt-3 pb-2">
          <div className="flex items-center bg-white dark:bg-[#1F1F1F] border border-gray-200 dark:border-white/10 rounded-full px-3.5 py-1.5 focus-within:border-gray-300 dark:focus-within:border-white/20 transition-colors">
            <Search size={13} className="text-gray-400 dark:text-gray-500 mr-2" />
            <input
              type="text"
              autoFocus
              placeholder="Search by company or contact"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="bg-transparent outline-none text-[12px] text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 w-full font-poppins"
            />
          </div>
        </div>

        {/* List */}
        <div className="px-2 pb-2 max-h-[320px] overflow-y-auto">
          {loading ? (
            <div className="py-10 text-center text-[12px] text-gray-400 dark:text-gray-500">Loading clients…</div>
          ) : error ? (
            <div className="py-10 text-center text-[12px] text-red-500 dark:text-red-300">{error}</div>
          ) : filtered.length === 0 ? (
            <div className="py-10 text-center text-[12px] text-gray-400 dark:text-gray-500">
              {query ? "No clients match that search." : "No clients yet — add one in Client Management."}
            </div>
          ) : (
            <ul className="space-y-0.5">
              {filtered.map((c) => {
                const id = c.id ?? c.client_id;
                const company = c.company_name ?? c.company ?? "Untitled client";
                const contact = c.primary_contact?.full_name ?? c.contact ?? "";
                const isVIP = !!(c.is_vip || c.isVIP);
                const prefs = c.preferences ?? {};
                const has = hasMeaningfulPreferences(prefs);
                return (
                  <li key={id}>
                    <button
                      type="button"
                      onClick={() => onPick({ clientId: id, client: c })}
                      disabled={busy}
                      className="group w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors duration-200 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <div className="relative w-9 h-9 rounded-lg bg-gradient-to-br from-[#FFDE39]/30 to-[#FFEC85]/30 dark:from-[#FFDE39]/15 dark:to-[#FFDE39]/5 flex items-center justify-center text-[12px] font-bold text-[#1f1f1f] dark:text-[#FFDE39] flex-shrink-0">
                        {company.slice(0, 2).toUpperCase()}
                        {isVIP && (
                          <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-[#FFDE39] flex items-center justify-center ring-2 ring-white dark:ring-[#2A2929]">
                            <Crown size={7} className="text-[#1f1f1f]" />
                          </span>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[13px] font-semibold text-[#1f1f1f] dark:text-white truncate">{company}</span>
                          {has && (
                            <Star size={10} className="text-[#FFDE39] fill-[#FFDE39] flex-shrink-0" />
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-[10.5px] text-gray-500 dark:text-gray-400 truncate mt-0.5">
                          {contact && <span className="truncate">{contact}</span>}
                          {contact && <span className="text-gray-300 dark:text-gray-600">·</span>}
                          <span className="truncate">{summarisePrefs(prefs)}</span>
                        </div>
                      </div>
                      <ArrowRight size={13} className="text-gray-300 dark:text-gray-600 group-hover:text-[#FFDE39] group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-2.5 border-t border-gray-100 dark:border-white/10 bg-gray-50/40 dark:bg-white/[0.02] flex items-center justify-between">
          <span className="text-[10.5px] text-gray-500 dark:text-gray-400">
            ⭐ marks clients with saved preferences
          </span>
          <button
            type="button"
            onClick={onSkip}
            disabled={busy}
            className="text-[11px] font-medium text-[#1f1f1f] dark:text-[#FFDE39] hover:underline disabled:opacity-50"
          >
            Continue without a client
          </button>
        </div>
      </div>
    </div>
  );
}
