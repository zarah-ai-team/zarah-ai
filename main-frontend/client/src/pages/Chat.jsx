import React, { useState, useRef, useEffect, useCallback } from "react";
import { useSearchParams, useNavigate, Link, useOutletContext } from "react-router-dom";
import {
  ArrowUp,
  Paperclip,
  Clock,
  ArrowRight,
  Pencil,
  Check,
  X,
  MessageSquare,
  MessageSquarePlus,
  AlertCircle,
  RefreshCw,
  Upload,
  Search,
  Database,
  Sparkles,
  MapPin,
  Calculator,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import {
  sendChatMessage,
  getChatSession,
  updateChatMetadata,
  listChats,
} from "../services/chatService";
import ItineraryDisplay, { generateItineraryPDF } from "../components/chat/ItineraryDisplay";
import ConfirmationCard from "../components/chat/ConfirmationCard";

const SUGGESTIONS = [
  { id: 1, text: "Create a 4N/5D incentive trip itinerary for Abu Dhabi for 45 people" },
  { id: 2, text: "Estimate the total trip cost per person for this Dubai corporate retreat" },
  { id: 3, text: "Suggest hotel and activity options in Bali for a 3-night leisure group" },
  { id: 4, text: "Summarize key inclusions and exclusions for this Oman & UAE itinerary" },
];

const WELCOME_LINES = [
  "How can I assist you today?",
  "Where would you like to travel next?",
  "Let's plan your next journey.",
  "What kind of trip are we designing today?",
  "How may I help with your itinerary today?",
  "Ready when you are — where shall we go?",
];

const ZARAH_GREETINGS = [
  (name) => `Hi ${name}! I'm Zarah 👋 Your travel planning assistant. What destination are we dreaming up today?`,
  (name) => `Hello ${name}! Zarah here — ready to craft the perfect itinerary for you. Where shall we go?`,
  (name) => `Hey ${name}! I'm Zarah, your DMC planning partner. Drop me a destination and I'll get to work!`,
  (name) => `Good to see you, ${name}! I'm Zarah. Whether it's a corporate retreat or a leisure escape — I've got you covered. What's the trip?`,
  (name) => `Hi there, ${name}! Zarah speaking 🌍 Tell me about your next trip and I'll build a full itinerary with costing.`,
];

// Pipeline stages shown during generation — cumulative delay in ms
const PIPELINE_STAGES = [
  { id: "parse",    icon: MapPin,      label: "Analyzing your request",        delay: 400  },
  { id: "search",   icon: Search,      label: "Searching web via Tavily",       delay: 2500 },
  { id: "kb",       icon: Database,    label: "Retrieving knowledge base",      delay: 5000 },
  { id: "cost",     icon: Calculator,  label: "Calculating costs & routing",    delay: 7500 },
  { id: "llm",      icon: Sparkles,    label: "Generating day-by-day itinerary",delay: 9500 },
];

function useLoadingStages(isTyping) {
  const [activeStages, setActiveStages] = useState([]);
  const timersRef = useRef([]);

  useEffect(() => {
    // clear all timers and reset when not typing
    if (!isTyping) {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
      // brief delay before hiding so user sees completion
      const t = setTimeout(() => setActiveStages([]), 600);
      timersRef.current.push(t);
      return;
    }
    setActiveStages([]);
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    PIPELINE_STAGES.forEach((stage) => {
      const t = setTimeout(() => {
        setActiveStages((prev) =>
          prev.find((s) => s.id === stage.id) ? prev : [...prev, stage.id]
        );
      }, stage.delay);
      timersRef.current.push(t);
    });
    return () => { timersRef.current.forEach(clearTimeout); };
  }, [isTyping]);

  return activeStages;
}

// ── Extract the first valid JSON object from any string (handles LLM preamble) ──
function tryParseJson(str) {
  if (!str || typeof str !== "string") return null;
  try {
    const t = str.trim().replace(/^```(?:json)?\n?/i, "").replace(/```\s*$/m, "");
    const start = t.indexOf("{");
    if (start === -1) return null;
    let depth = 0;
    for (let i = start; i < t.length; i++) {
      if (t[i] === "{") depth++;
      else if (t[i] === "}") { depth--; if (depth === 0) return JSON.parse(t.slice(start, i + 1)); }
    }
    return null;
  } catch { return null; }
}

// ── Quick-reply chip suggestions keyed by question type ──
const QUESTION_CHIPS = {
  destination : ["Dubai", "Abu Dhabi", "Singapore", "Bali / Indonesia", "Europe Multi-City", "Maldives"],
  duration    : ["3 nights", "5 nights", "7 nights", "10 nights", "14 nights"],
  pax         : ["10 pax", "20 pax", "30 pax", "50 pax", "100 pax"],
  event_type  : ["Leisure", "Corporate Offsite", "Incentive Trip", "MICE / Conference", "Honeymoon", "Extension Trip"],
  hotel       : ["3-Star", "4-Star", "4-Star Deluxe", "5-Star Luxury"],
  transport   : ["Private Van", "Mercedes Viano", "Coach / Bus", "No preference"],
};

function getChipsForPrompt(prompt) {
  if (!prompt) return [];
  const p = prompt.toLowerCase();
  if (p.includes("destination") || p.includes("where") || p.includes("cities") || p.includes("travel to")) return QUESTION_CHIPS.destination;
  if (p.includes("nights") || p.includes("duration") || p.includes("how long") || p.includes("days")) return QUESTION_CHIPS.duration;
  if (p.includes("pax") || p.includes("travelers") || p.includes("people") || p.includes("how many")) return QUESTION_CHIPS.pax;
  if (p.includes("occasion") || p.includes("event") || p.includes("trip type") || p.includes("purpose")) return QUESTION_CHIPS.event_type;
  if (p.includes("hotel") || p.includes("star") || p.includes("category") || p.includes("accommodation")) return QUESTION_CHIPS.hotel;
  if (p.includes("transport") || p.includes("vehicle")) return QUESTION_CHIPS.transport;
  return [];
}

// Friendly labels for collected fields shown in the context strip
const FIELD_LABELS = {
  destination        : (v) => Array.isArray(v) ? v.join(" → ") : v,
  destinations       : (v) => Array.isArray(v) ? v.join(" → ") : v,
  pax                : (v) => `${v} pax`,
  total_nights       : (v) => `${v} nights`,
  nights             : (v) => `${v} nights`,
  hotel_category     : (v) => v,
  trip_start_date    : (v) => v,
  event_type         : (v) => v,
  contact_person     : (v) => `Attn: ${v}`,
};

function collectFieldPills(collected) {
  if (!collected || typeof collected !== "object") return [];
  const pills = [];
  const seen = new Set();
  for (const [key, label] of Object.entries(FIELD_LABELS)) {
    const val = collected[key];
    if (!val || seen.has(label)) continue;
    const text = label(val);
    if (text) { pills.push(text); seen.add(text); }
  }
  return pills;
}

// ── QuestionCard — renders a need_more prompt with context + chip suggestions ──
function QuestionCard({ text, collected, chips, onChipClick }) {
  const pills = collectFieldPills(collected);
  return (
    <div className="space-y-3">
      {pills.length > 0 && (
        <div>
          <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">What I have so far</p>
          <div className="flex flex-wrap gap-1.5">
            {pills.map((p, i) => (
              <span key={i} className="text-[11px] bg-[#FFFAC5] text-[#8A6800] border border-[#FFDE39]/40 px-2.5 py-0.5 rounded-full font-medium">
                {p}
              </span>
            ))}
          </div>
        </div>
      )}
      <p className="text-sm text-gray-800 leading-relaxed">{text}</p>
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {chips.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => onChipClick(chip)}
              className="text-xs font-medium text-gray-700 bg-gray-100 hover:bg-[#FFFAC5] hover:text-[#8A6800] hover:border-[#FFDE39]/60 border border-gray-200 px-3 py-1.5 rounded-full transition-all duration-200 cursor-pointer"
            >
              {chip}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function formatChatResponse(response) {
  if (!response) return "No response received.";
  if (response.need_more && response.prompt) return response.prompt;
  // Try to get itinerary from any source — LLM sometimes adds preamble before the JSON
  const itinerary = response.itinerary
    || tryParseJson(response.itinerary_beautified)
    || tryParseJson(response.llm_raw);
  if (itinerary && typeof itinerary === "object" && itinerary.days) return "__ITINERARY__";
  if (response.itinerary_beautified) return response.itinerary_beautified;
  if (response.llm_raw) return response.llm_raw;
  return "I wasn't able to generate an itinerary. Please try again.";
}

function formatItinerary(itinerary, response) {
  const lines = [];
  if (itinerary.title) lines.push(itinerary.title);
  if (itinerary.destination) {
    const pax = itinerary.pax ? ` · ${itinerary.pax} pax` : "";
    const dur = itinerary.duration_days ? ` · ${itinerary.duration_days} days` : "";
    lines.push(`${itinerary.destination}${pax}${dur}`);
  }
  if (Array.isArray(itinerary.days) && itinerary.days.length > 0) {
    lines.push("\nDay-by-Day Itinerary:");
    itinerary.days.forEach((day) => {
      const num = day.day ?? day.day_number ?? "";
      const city = day.city ? ` — ${day.city}` : "";
      const summary = day.summary ?? day.title ?? "";
      lines.push(`\nDay ${num}${city}${summary ? ` | ${summary}` : ""}`);
      if (day.morning)   lines.push(`  Morning   : ${day.morning}`);
      if (day.afternoon) lines.push(`  Afternoon : ${day.afternoon}`);
      if (day.evening)   lines.push(`  Evening   : ${day.evening}`);
      if (Array.isArray(day.activities) && day.activities.length) {
        day.activities.slice(0, 8).forEach((act) => lines.push(`    - ${act}`));
        if (day.activities.length > 8) lines.push(`    - ... +${day.activities.length - 8} more`);
      }
      if (day.hotel?.name && day.hotel.name !== "To be confirmed") {
        lines.push(`  Hotel     : ${day.hotel.name}${day.hotel.area ? `, ${day.hotel.area}` : ""}${day.hotel.category ? ` (${day.hotel.category})` : ""}`);
      }
    });
  }
  const cb = itinerary.cost_breakdown ?? response?.cost_breakdown;
  if (cb && typeof cb === "object" && Object.keys(cb).length) {
    lines.push("\nCost Breakdown:");
    Object.entries(cb).forEach(([k, v]) => {
      if (v) lines.push(`  ${k.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()).padEnd(30)}: ${v}`);
    });
  }
  if (Array.isArray(itinerary.hotels) && itinerary.hotels.length) {
    lines.push("\nHotel Options:");
    itinerary.hotels.slice(0, 4).forEach((h) => {
      const price = h.price_per_night_inr || h.price_per_night_in_inr || (h.price_per_night ? `${h.currency || ""} ${h.price_per_night}/night` : "");
      const city = h.city ? `${h.city} — ` : "";
      lines.push(`  • ${city}${h.name}${price ? ` (${price})` : ""}`);
    });
  }
  if (Array.isArray(itinerary.inclusions) && itinerary.inclusions.length) {
    lines.push("\nInclusions:");
    itinerary.inclusions.forEach((inc) => lines.push(`  + ${inc}`));
  }
  if (Array.isArray(itinerary.exclusions) && itinerary.exclusions.length) {
    lines.push("\nExclusions:");
    itinerary.exclusions.forEach((exc) => lines.push(`  - ${exc}`));
  }
  if (Array.isArray(itinerary.important_guidelines) && itinerary.important_guidelines.length) {
    lines.push("\nImportant Guidelines:");
    itinerary.important_guidelines.forEach((g) => lines.push(`  * ${g}`));
  }
  if (itinerary.notes) lines.push(`\nNotes: ${itinerary.notes}`);
  const predictedCost = response?.predicted_cost;
  if (predictedCost) lines.push(`\nML Cost Estimate: USD ${Math.round(predictedCost).toLocaleString()}`);
  return lines.join("\n");
}

function historyToMessages(history = [], lastLlmRaw = null) {
  const msgs = [];
  let id = 1;
  // Find index of the last assistant_raw entry so we can use lastLlmRaw for it
  let lastRawIdx = -1;
  history.forEach((h, i) => { if (h.role === "assistant_raw") lastRawIdx = i; });

  history.forEach((h, i) => {
    if (h.role === "user" && h.content) {
      msgs.push({ id: id++, role: "user", text: h.content });
    } else if (h.role === "assistant" && h.content) {
      // need_more prompts and formal request summaries stored as plain text
      msgs.push({ id: id++, role: "assistant", text: h.content });
    } else if (h.role === "assistant_raw" && h.content) {
      // Use full lastLlmRaw for the final entry (avoids truncation issues)
      const raw = (i === lastRawIdx && lastLlmRaw) ? lastLlmRaw : h.content;
      let parsed = null;
      try {
        parsed = JSON.parse(raw.trim().replace(/^```[a-z]*\n?/, "").replace(/```$/, ""));
      } catch {
        parsed = tryParseJson(raw);
      }
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && (parsed.days || parsed.title || parsed.destination)) {
        msgs.push({ id: id++, role: "assistant", text: "", itinerary: parsed });
      } else if (raw.trim().length > 0) {
        msgs.push({ id: id++, role: "assistant", text: raw });
      }
    }
  });
  return msgs;
}

function formatRelativeDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const diffDays = Math.floor((Date.now() - d) / 86400000);
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  } catch { return ""; }
}

const Chat = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionIdParam = searchParams.get("session");
  const outletCtx = useOutletContext() || {};
  const sidebarCollapsed = !!outletCtx.sidebarCollapsed;

  const [query,          setQuery]          = useState("");
  const [messages,       setMessages]       = useState([]);
  const [sessionId,      setSessionId]      = useState(sessionIdParam || null);
  const [chatName,       setChatName]       = useState("New Chat");
  const [isEditingName,  setIsEditingName]  = useState(false);
  const [editNameValue,  setEditNameValue]  = useState("");
  const [isTyping,       setIsTyping]       = useState(false);
  const [loadingSession, setLoadingSession] = useState(!!sessionIdParam);
  const [lastError,      setLastError]      = useState(null);
  const [kbWarning,      setKbWarning]      = useState(null);
  const [savedMsgIds,    setSavedMsgIds]    = useState(() => new Set());

  // History panel state
  const [showHistory,    setShowHistory]    = useState(false);
  const [historyList,    setHistoryList]    = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const messagesEndRef   = useRef(null);
  const chatNameInputRef = useRef(null);
  const textareaRef      = useRef(null);
  const activeStages     = useLoadingStages(isTyping);

  const firstName  = (user?.full_name || user?.username || "there").split(" ")[0];
  // treat a lone greeting as "no real messages" so suggestions stay visible
  const hasMessages = messages.some((m) => !m.isGreeting);
  // rotating welcome line — picks a fresh tagline on every visit
  const [welcomeLine, setWelcomeLine] = useState(
    () => WELCOME_LINES[Math.floor(Math.random() * WELCOME_LINES.length)]
  );

  // refresh the tagline whenever the user lands on a fresh chat
  useEffect(() => {
    if (!sessionIdParam) {
      setWelcomeLine(WELCOME_LINES[Math.floor(Math.random() * WELCOME_LINES.length)]);
    }
  }, [sessionIdParam]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  useEffect(() => {
    if (isEditingName) chatNameInputRef.current?.focus();
  }, [isEditingName]);

  useEffect(() => {
    // Always wipe stale state when session param changes (covers navigation between sessions)
    setMessages([]);
    setQuery("");
    setIsTyping(false);
    setLastError(null);
    setIsEditingName(false);

    if (!sessionIdParam) {
      setSessionId(null);
      setChatName("New Chat");
      setLoadingSession(false);
      // Show Zarah greeting for fresh chats with a small typing delay
      const greeting = ZARAH_GREETINGS[Math.floor(Math.random() * ZARAH_GREETINGS.length)];
      const t = setTimeout(() => {
        setMessages([{ id: 1, role: "assistant", text: greeting(firstName), isGreeting: true }]);
      }, 420);
      return () => clearTimeout(t);
    }

    setLoadingSession(true);
    getChatSession(sessionIdParam)
      .then((res) => {
        const chat = res.chat ?? res;
        setChatName(chat.chat_name || "Chat");
        setSessionId(chat.session_id ?? sessionIdParam);
        // Pass last_llm_raw so the final itinerary entry is fully parseable
        const restored = historyToMessages(chat.history ?? [], chat.last_llm_raw);
        setMessages(restored);
      })
      .catch(() => {
        // Session not found in store — open a fresh chat under this session id
        setSessionId(sessionIdParam);
        setChatName("New Chat");
      })
      .finally(() => setLoadingSession(false));
  }, [sessionIdParam, firstName]);

  const handleSend = useCallback(async (text) => {
    const msg = (text || query).trim();
    if (!msg || isTyping) return;
    setLastError(null);
    setQuery("");
    if (textareaRef.current) { textareaRef.current.style.height = "auto"; }
    setMessages((prev) => [...prev, { id: Date.now(), role: "user", text: msg }]);
    if (messages.length === 0 && chatName === "New Chat") {
      const name = msg.length > 45 ? msg.slice(0, 45) + "…" : msg;
      setChatName(name);
    }
    setIsTyping(true);
    try {
      const currentSid = sessionId;
      const response = await sendChatMessage(currentSid, msg);
      const returnedSid = response.session_id ?? currentSid;
      if (returnedSid && returnedSid !== sessionId) {
        setSessionId(returnedSid);
        const url = new URL(window.location.href);
        url.searchParams.set("session", returnedSid);
        window.history.replaceState({}, "", url.toString());
      }
      const isConfirmation = !!(response.need_confirmation && response.confirmation_fields);
      const replyItinerary = isConfirmation
        ? null
        : (response.itinerary ||
           tryParseJson(response.itinerary_beautified) ||
           tryParseJson(response.llm_raw) ||
           null);
      const replyText = isConfirmation ? "" : replyItinerary ? "" : formatChatResponse(response);
      const isQuestion = !isConfirmation && !!(response.need_more && response.prompt);
      const replyMsg = {
        id: Date.now() + 1,
        role: "assistant",
        text: replyText,
        raw: response,
        itinerary: replyItinerary,
        ...(isConfirmation && {
          isConfirmation: true,
          confirmationFields: response.confirmation_fields,
        }),
        ...(isQuestion && {
          isQuestion: true,
          chips: getChipsForPrompt(response.prompt),
          collected: response.collected || {},
        }),
      };
      setMessages((prev) => [...prev, replyMsg]);
      if (response.kb_warning && (response.itinerary || response.itinerary_beautified)) {
        setKbWarning(response.kb_warning);
      } else if (response.kb_docs_used > 0) {
        setKbWarning(null);
      }
      if (returnedSid && messages.length === 0) {
        const name = msg.length > 45 ? msg.slice(0, 45) + "…" : msg;
        updateChatMetadata(returnedSid, { chat_name: name }).catch(() => {});
      }
    } catch (err) {
      const errMsg = err?.data?.detail || err?.message || "Unknown error";
      setLastError(errMsg);
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: "error", text: `⚠️ ${errMsg}` }]);
    } finally {
      setIsTyping(false);
    }
  }, [query, messages, isTyping, sessionId, chatName]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleNewChat = () => {
    setMessages([]);
    setQuery("");
    setSessionId(null);
    setChatName("New Chat");
    setIsTyping(false);
    setLastError(null);
    navigate("/chat", { replace: true });
  };

  const startEditName  = () => { setEditNameValue(chatName); setIsEditingName(true); };
  const saveName       = () => {
    const name = editNameValue.trim();
    if (name) {
      setChatName(name);
      if (sessionId) updateChatMetadata(sessionId, { chat_name: name }).catch(() => {});
    }
    setIsEditingName(false);
  };
  const cancelEditName = () => setIsEditingName(false);

  const handleSaveItinerary = useCallback(async (msgId, itinerary) => {
    if (sessionId) {
      const payload = { status: "completed" };
      if (itinerary) payload.saved_itinerary = itinerary;
      await updateChatMetadata(sessionId, payload).catch(() => {});
      if (itinerary) generateItineraryPDF(itinerary);
    }
    setSavedMsgIds((prev) => new Set([...prev, msgId]));
    navigate("/itineraries");
  }, [sessionId, navigate]);

  const handleDiscardItinerary = useCallback((msgId) => {
    setMessages((prev) => prev.filter((m) => m.id !== msgId));
  }, []);

  const openHistory = async () => {
    setShowHistory(true);
    setHistoryLoading(true);
    try {
      const data = await listChats();
      const list = Array.isArray(data) ? data : (data.chats ?? data.sessions ?? []);
      list.sort((a, b) => new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0));
      setHistoryList(list);
    } catch {}
    finally { setHistoryLoading(false); }
  };

  const inputBar = (
    <div className="flex items-center bg-white rounded-2xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-gray-100 px-4 py-2.5 transition-all duration-300 focus-within:shadow-[0_4px_14px_rgba(0,0,0,0.06)] focus-within:border-gray-200">
      <button
        className="p-1 text-gray-500 hover:text-gray-700 transition-colors duration-200 cursor-pointer flex-shrink-0"
        aria-label="Attach file"
      >
        <Paperclip size={17} />
      </button>
      <textarea
        ref={textareaRef}
        rows={1}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          const ta = e.target;
          ta.style.height = "auto";
          ta.style.height = `${Math.min(ta.scrollHeight, 140)}px`;
        }}
        onKeyDown={handleKeyDown}
        placeholder="Enter your query"
        className="flex-1 bg-transparent outline-none text-[13.5px] text-gray-800 placeholder-gray-400 px-3 py-1 font-poppins resize-none overflow-y-auto leading-relaxed"
        style={{ minHeight: "28px", maxHeight: "140px" }}
        disabled={isTyping || loadingSession}
        autoFocus={!hasMessages}
      />
      <button
        onClick={() => handleSend()}
        disabled={isTyping || loadingSession || !query.trim()}
        className={`p-1 transition-colors duration-200 flex-shrink-0 ${
          query.trim() && !isTyping && !loadingSession
            ? "text-dark-300 hover:text-black cursor-pointer"
            : "text-gray-400 cursor-not-allowed"
        }`}
        aria-label="Send"
      >
        {isTyping ? <RefreshCw size={16} className="animate-spin" /> : <ArrowUp size={18} />}
      </button>
    </div>
  );

  return (
    <div className="relative flex flex-col h-full animate-fadeIn overflow-hidden">

      {/* ── History slide-in panel ── */}
      <div
        className={`absolute inset-y-0 right-0 w-72 bg-white z-30 flex flex-col shadow-[-6px_0_24px_rgba(0,0,0,0.08)] border-l border-gray-100/80 transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] ${
          showHistory ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Panel header */}
        <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-[#FFFCE6] to-[#FFFAC5] border-b border-[#FFDE39]/25">
          <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
            <Clock size={14} className="text-[#E6C800]" />
            Chat History
          </h3>
          <button
            onClick={() => setShowHistory(false)}
            className="p-1 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer rounded"
          >
            <X size={15} />
          </button>
        </div>

        {/* New chat button */}
        <div className="px-3 py-2.5 border-b border-gray-100">
          <button
            onClick={() => { handleNewChat(); setShowHistory(false); }}
            className="w-full flex items-center gap-2 bg-dark-300 text-white text-xs font-medium px-3 py-2 rounded-lg hover:bg-dark-200 transition-all duration-300 cursor-pointer"
          >
            <MessageSquarePlus size={13} className="text-[#FFDE39]" />
            New Chat
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto">
          {historyLoading ? (
            <div className="flex items-center justify-center py-10">
              <RefreshCw size={16} className="animate-spin text-gray-400" />
            </div>
          ) : historyList.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
              <p className="text-xs text-gray-400">No past chats yet.</p>
              <p className="text-xs text-gray-300 mt-1">Start a conversation to see history here.</p>
            </div>
          ) : (
            historyList.map((session) => {
              const sid = session.session_id ?? session.id;
              const isActive = sid === sessionId;
              const name = session.chat_name || `Chat ${String(sid).slice(0, 8)}`;
              const date = formatRelativeDate(session.updated_at || session.created_at);
              const meta = session.metadata || {};
              const tripParts = [
                meta.itinerary_name,
                meta.travelers_max ? `${meta.travelers_max} pax` : null,
                meta.duration || null,
              ].filter(Boolean);
              const tripInfo = tripParts.join(" · ");
              const statusColor = meta.status === "in_progress" ? "bg-green-400"
                : meta.status === "completed" ? "bg-blue-400"
                : "bg-gray-300 group-hover:bg-[#FFDE39]";
              return (
                <button
                  key={sid}
                  onClick={() => { navigate(`/chat?session=${sid}`); setShowHistory(false); }}
                  className={`w-full text-left px-4 py-3 border-b border-gray-50 transition-all duration-200 cursor-pointer group last:border-0 ${
                    isActive ? "bg-[#FFFAC5]/80" : "hover:bg-[#FFFCE6]"
                  }`}
                >
                  <div className="flex items-start gap-2.5">
                    <div className={`w-1.5 h-1.5 rounded-full mt-[5px] flex-shrink-0 transition-colors ${
                      isActive ? "bg-[#E6C800]" : statusColor
                    }`} />
                    <div className="flex-1 min-w-0">
                      <p className={`text-xs font-medium truncate transition-colors ${
                        isActive ? "text-gray-900" : "text-gray-700 group-hover:text-gray-900"
                      }`}>
                        {name}
                      </p>
                      {tripInfo && (
                        <p className="text-[10px] text-gray-400 truncate mt-0.5">{tripInfo}</p>
                      )}
                      {date && (
                        <p className="text-[10px] text-gray-300 mt-0.5">{date}</p>
                      )}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Backdrop */}
      {showHistory && (
        <div
          className="absolute inset-0 z-20 bg-gray-800/5 backdrop-blur-[1px]"
          onClick={() => setShowHistory(false)}
        />
      )}

      {/* ── Loading ── */}
      {loadingSession ? (
        <div className="flex-1 flex items-center justify-center bg-gray-100 rounded-2xl">
          <RefreshCw size={24} className="animate-spin text-gray-400" />
        </div>

      ) : !hasMessages ? (
        /* ── Empty state ── */
        <div className="flex-1 flex flex-col px-2 sm:px-4 py-1.5 relative animate-fadeIn">
          {/* History pill — top-right */}
          <div className="flex justify-end">
            <button
              onClick={openHistory}
              className="flex items-center gap-1.5 bg-dark-300 text-white text-[12px] font-medium px-3.5 py-1.5 rounded-full shadow-[0_2px_6px_rgba(0,0,0,0.08)] hover:bg-dark-200 hover:-translate-y-0.5 transition-all duration-300 cursor-pointer"
            >
              <Clock size={13} />
              History
            </button>
          </div>

          {/* Centered greeting + input + suggestion cards */}
          <div className="flex-1 flex flex-col items-center justify-center">
            <div className="w-full max-w-[600px]">
              {/* Greeting block — left-aligned to match Figma */}
              <div className="mb-5 pl-1">
                <p className="text-[14px] text-[#1f1f1f] font-normal mb-0.5 font-poppins">
                  Hello <span className="text-[#E6C800] font-medium">{firstName}</span>
                </p>
                <h1 className="text-[26px] sm:text-[28px] font-bold text-[#1f1f1f] leading-tight font-poppins tracking-tight">
                  {welcomeLine}
                </h1>
              </div>

              {inputBar}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mt-2.5">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => handleSend(s.text)}
                    className="text-left bg-white rounded-xl border border-gray-100 shadow-[0_1px_2px_rgba(0,0,0,0.02)] p-3 text-[10.5px] text-gray-500 leading-[1.45] hover:shadow-[0_3px_10px_rgba(0,0,0,0.05)] hover:-translate-y-0.5 hover:border-gray-200 transition-all duration-300 group flex flex-col justify-between min-h-[78px] font-poppins"
                  >
                    <span className="line-clamp-3">{s.text}</span>
                    <ArrowRight size={11} className="mt-1.5 text-gray-400 group-hover:text-gray-700 transition-colors duration-200 self-end" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

      ) : (
        /* ── Active chat ── */
        <div className="flex-1 flex flex-col overflow-hidden animate-fadeIn">
          {/* Sub-header strip — chat title + actions, full width (no outer gutter) */}
          <div className="bg-white rounded-xl border border-gray-100 shadow-[0_1px_3px_rgba(0,0,0,0.02)] px-5 py-2.5 flex items-center justify-between mb-3 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <MessageSquare size={14} className="text-[#E6C800] flex-shrink-0" />
              {isEditingName ? (
                <div className="flex items-center gap-1.5">
                  <input
                    ref={chatNameInputRef}
                    value={editNameValue}
                    onChange={(e) => setEditNameValue(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") saveName(); if (e.key === "Escape") cancelEditName(); }}
                    className="text-[13px] font-medium text-gray-800 bg-gray-50 rounded-md px-2 py-0.5 outline-none border border-gray-300 focus:border-brand-400 transition-colors duration-200 font-poppins"
                  />
                  <button onClick={saveName} className="p-0.5 text-green-500 hover:text-green-600 cursor-pointer"><Check size={13} /></button>
                  <button onClick={cancelEditName} className="p-0.5 text-gray-400 hover:text-gray-600 cursor-pointer"><X size={13} /></button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 group min-w-0">
                  <h2 className="text-[13px] font-medium text-gray-800 font-poppins truncate">{chatName}</h2>
                  <button
                    onClick={startEditName}
                    title="Rename chat"
                    className="p-0.5 text-gray-400 hover:text-gray-700 opacity-0 group-hover:opacity-100 transition-all duration-200 cursor-pointer flex-shrink-0"
                  >
                    <Pencil size={12} />
                  </button>
                </div>
              )}
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={handleNewChat}
                className="flex items-center gap-1.5 text-[12px] font-medium text-gray-700 hover:text-[#1f1f1f] hover:bg-gray-50 px-2.5 py-1.5 rounded-md transition-all duration-200 cursor-pointer"
              >
                <MessageSquarePlus size={13} className="text-gray-500" />
                New Chat
              </button>
              <button
                onClick={openHistory}
                className="flex items-center gap-1.5 text-[12px] font-medium text-gray-700 hover:text-[#1f1f1f] hover:bg-gray-50 px-2.5 py-1.5 rounded-md transition-all duration-200 cursor-pointer"
              >
                <Clock size={13} className="text-gray-500" />
                History
              </button>
            </div>
          </div>

          {/* Messages + input column — scroll area is full-width (scrollbar pinned far right);
              padding moves to inner wrappers so content stays comfortably gutter-aligned */}
          <div className="w-full flex-1 flex flex-col overflow-hidden">
            {/* Messages — full-width scroll area; inner padding only on content */}
            <div className="flex-1 overflow-y-auto">
              <div className={`space-y-3 pb-2 transition-[padding] duration-400 ease-[cubic-bezier(0.16,1,0.3,1)] ${sidebarCollapsed ? "px-32" : "px-10"}`}>
              {messages.map((msg) => {
                const isItinerary = !!(msg.itinerary || msg.raw?.itinerary);
                const itineraryObj = msg.itinerary || msg.raw?.itinerary;

                if (msg.role === "user") {
                  return (
                    <div key={msg.id} className="flex justify-end animate-fadeIn">
                      <div className="bg-white rounded-xl px-3.5 py-2 shadow-[0_1px_3px_rgba(0,0,0,0.03)] border border-gray-200/80 max-w-[70%] text-[12.5px] text-gray-800 leading-relaxed whitespace-pre-wrap">
                        {msg.text}
                      </div>
                    </div>
                  );
                }

                if (msg.role === "error") {
                  return (
                    <div key={msg.id} className="flex justify-start animate-fadeIn">
                      <div className="bg-red-50 text-red-700 border border-red-200 rounded-xl px-3.5 py-2.5 max-w-[85%] text-[12.5px] leading-relaxed flex items-start gap-2">
                        <AlertCircle size={14} className="text-red-500 mt-0.5 flex-shrink-0" />
                        <span className="whitespace-pre-wrap">{msg.text}</span>
                      </div>
                    </div>
                  );
                }

                if (msg.isConfirmation) {
                  return (
                    <div key={msg.id} className="flex justify-start animate-fadeIn">
                      <ConfirmationCard
                        fields={msg.confirmationFields}
                        onConfirm={() => handleSend("confirm")}
                      />
                    </div>
                  );
                }

                if (isItinerary) {
                  // Itinerary card stays white per spec — design unchanged
                  return (
                    <div key={msg.id} className="flex justify-start animate-fadeIn">
                      <div className="w-full bg-white rounded-xl px-4 py-3.5 shadow-[0_1px_4px_rgba(0,0,0,0.04)] border border-gray-100">
                        <Sparkles size={15} className="text-[#FFDE39] fill-[#FFDE39] mb-2.5" />
                        <ItineraryDisplay
                          itinerary={itineraryObj}
                          sessionId={sessionId}
                          saved={savedMsgIds.has(msg.id)}
                          onSave={() => handleSaveItinerary(msg.id, itineraryObj)}
                          onDiscard={() => handleDiscardItinerary(msg.id)}
                        />
                      </div>
                    </div>
                  );
                }

                // Regular assistant bubble — white container w/ gradient stroke
                return (
                  <div key={msg.id} className="flex justify-start animate-fadeIn">
                    <div
                      className="rounded-xl max-w-[90%] shadow-[0_4px_16px_rgba(0,0,0,0.05)]"
                      style={{
                        padding: "1.2px",
                        background: "linear-gradient(135deg, #FFF690 0%, #E9E6CA 100%)",
                      }}
                    >
                      <div className="bg-white rounded-[11px] px-4 py-3">
                        <Sparkles size={18} className="text-[#1f1f1f] fill-[#1f1f1f] mb-2" />
                        {msg.isQuestion ? (
                          <QuestionCard
                            text={msg.text}
                            collected={msg.collected || {}}
                            chips={msg.chips || []}
                            onChipClick={(chip) => handleSend(chip)}
                          />
                        ) : (
                          <p className="text-[12.5px] text-gray-800 leading-relaxed whitespace-pre-wrap font-poppins">
                            {msg.text}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}

              {isTyping && (
                <div className="flex justify-start animate-fadeIn">
                  <div
                    className="rounded-xl min-w-[240px] shadow-[0_4px_16px_rgba(0,0,0,0.05)]"
                    style={{
                      padding: "1.2px",
                      background: "linear-gradient(135deg, #FFF690 0%, #E9E6CA 100%)",
                    }}
                  >
                    <div className="bg-white rounded-[11px] px-4 py-3">
                      <Sparkles size={18} className="text-[#1f1f1f] fill-[#1f1f1f] mb-2" />
                      <p className="text-[10px] font-semibold text-gray-600 mb-2.5 tracking-wide uppercase">Building your itinerary</p>
                      <div className="space-y-2">
                        {PIPELINE_STAGES.map((stage) => {
                          const StageIcon = stage.icon;
                          const done = activeStages.includes(stage.id);
                          const isLast = stage.id === PIPELINE_STAGES[PIPELINE_STAGES.length - 1].id;
                          const isActive = done && isLast;
                          return (
                            <div key={stage.id} className={`flex items-center gap-2 transition-all duration-500 ${done ? "opacity-100" : "opacity-25"}`}>
                              <div className={`w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300 ${
                                done && isActive ? "bg-[#FFDE39]" : done ? "bg-green-100" : "bg-gray-100"
                              }`}>
                                {done && !isActive
                                  ? <Check size={9} className="text-green-600" />
                                  : <StageIcon size={9} className={done ? "text-dark-300" : "text-gray-400"} />
                                }
                              </div>
                              <span className={`text-[11px] transition-colors duration-300 ${done ? "text-gray-800 font-medium" : "text-gray-500"}`}>
                                {stage.label}
                              </span>
                              {done && isActive && (
                                <RefreshCw size={10} className="animate-spin text-gray-500 ml-auto" />
                              )}
                              {done && !isActive && (
                                <span className="ml-auto text-[9px] text-green-600 font-medium">Done</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Bottom-anchored input — padded to align with messages */}
            <div className={`pt-1.5 transition-[padding] duration-400 ease-[cubic-bezier(0.16,1,0.3,1)] ${sidebarCollapsed ? "px-32" : "px-10"}`}>
              {kbWarning && (
                <div className="mb-2 flex items-center justify-between gap-3 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-lg text-[11px] text-amber-800">
                  <div className="flex items-center gap-2 min-w-0">
                    <AlertCircle size={12} className="flex-shrink-0 text-amber-500" />
                    <span className="truncate">{kbWarning}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Link
                      to="/documents/upload"
                      className="flex items-center gap-1 font-medium text-amber-700 hover:text-amber-900 underline underline-offset-2 transition-colors"
                    >
                      <Upload size={10} /> Upload
                    </Link>
                    <button onClick={() => setKbWarning(null)} className="text-amber-400 hover:text-amber-600 transition-colors">
                      <X size={12} />
                    </button>
                  </div>
                </div>
              )}
              {inputBar}
              {lastError && (
                <p className="mt-1.5 text-[11px] text-red-500 text-center">⚠️ {lastError}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Chat;
