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
  createChat,
} from "../services/chatService";
import ItineraryDisplay, { generateItineraryPDF } from "../components/chat/ItineraryDisplay";
import ConfirmationCard from "../components/chat/ConfirmationCard";
import DateRangePicker from "../components/chat/DateRangePicker";
import ClientPickerPanel from "../components/chat/ClientPickerPanel";

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

// Mirrors the backend's _GENERATE_INTENT_RE so the frontend can decide whether
// to show the heavy "Building your itinerary" pipeline UI or a lightweight
// "thinking" indicator. Keep these in sync if you change one side.
const GENERATE_INTENT_RE = /\b(?:generate|create|build|make|prepare|draft|design|put\s+together|plan|give\s+me|i\s+want|i\s+need)\b[^.?!]{0,80}?\b(?:itinerary|trip\s+plan|schedule|day-?by-?day|day\s*plan)\b/i;

// Pipeline stages shown during generation — cumulative delay in ms
const PIPELINE_STAGES = [
  { id: "parse",    icon: MapPin,      label: "Analyzing your request",        delay: 400  },
  { id: "search",   icon: Search,      label: "Searching web via Tavily",       delay: 2500 },
  { id: "kb",       icon: Database,    label: "Retrieving knowledge base",      delay: 5000 },
  { id: "cost",     icon: Calculator,  label: "Calculating costs & routing",    delay: 7500 },
  { id: "llm",      icon: Sparkles,    label: "Generating day-by-day itinerary",delay: 9500 },
];

// Light-touch travel facts that rotate while the user waits — kept short and useful.
const PIPELINE_TIPS = [
  "Pro tip: shoulder-season travel often gets you the best weather at the lowest prices.",
  "Did you know? Tavily pulls live web data, so attractions reflect what's open right now.",
  "Quotes assume one room per two adults — tell me if you need triples or single occupancy.",
  "Every figure in the cost breakdown is rounded to the nearest currency-appropriate unit.",
  "Generating a full day-by-day plan locally takes a few minutes — the LLM is the slow step.",
  "Tip: you can ask me to upgrade hotels, swap activities, or switch currency after generation.",
];

function useLoadingStages(isTyping) {
  const [activeStages, setActiveStages] = useState([]);
  const [elapsedSec, setElapsedSec] = useState(0);
  const timersRef = useRef([]);
  const tickRef = useRef(null);
  const startedAtRef = useRef(null);

  useEffect(() => {
    // clear all timers and reset when not typing
    if (!isTyping) {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
      if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
      startedAtRef.current = null;
      setElapsedSec(0);
      // brief delay before hiding so user sees completion
      const t = setTimeout(() => setActiveStages([]), 600);
      timersRef.current.push(t);
      return;
    }
    setActiveStages([]);
    setElapsedSec(0);
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    startedAtRef.current = Date.now();
    // Tick once per second so the active stage can show "running for Xs/Xm"
    tickRef.current = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    PIPELINE_STAGES.forEach((stage) => {
      const t = setTimeout(() => {
        setActiveStages((prev) =>
          prev.find((s) => s.id === stage.id) ? prev : [...prev, stage.id]
        );
      }, stage.delay);
      timersRef.current.push(t);
    });
    return () => {
      timersRef.current.forEach(clearTimeout);
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, [isTyping]);

  return { activeStages, elapsedSec };
}

// ── Extract the first valid JSON object from any string (handles LLM preamble + truncation) ──
// LLM outputs are sometimes cut off mid-JSON (token budget). We strip preamble/fences,
// then attempt strict parse; on failure, repair by closing unterminated strings,
// dropping partial trailing kv-pairs, and balancing brackets. This lets the chat render
// a usable itinerary card from a partial response instead of dumping raw JSON to the user.
function tryParseJson(str) {
  if (!str || typeof str !== "string") return null;
  const t = str.trim().replace(/^```(?:json)?\n?/i, "").replace(/```\s*$/m, "");
  const start = t.indexOf("{");
  if (start === -1) return null;
  const body = t.slice(start);

  // 1) Strict parse on the substring from first '{' to its matching '}' (string-aware).
  let inStr = false, escape = false, depth = 0;
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (escape) { escape = false; continue; }
    if (c === "\\") { escape = true; continue; }
    if (c === '"') { inStr = !inStr; continue; }
    if (inStr) continue;
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) {
        try { return JSON.parse(body.slice(0, i + 1)); } catch { break; }
      }
    }
  }

  // 2) Repair path — JSON is truncated. Walk and remember the last "safe" position
  //    (just before a top-of-context comma, or at the close of a complete sub-value).
  inStr = false; escape = false;
  const stack = [];
  let lastSafeEnd = -1;
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (escape) { escape = false; continue; }
    if (c === "\\") { escape = true; continue; }
    if (c === '"') { inStr = !inStr; continue; }
    if (inStr) continue;
    if (c === "{" || c === "[") stack.push(c);
    else if (c === "}" || c === "]") { stack.pop(); lastSafeEnd = i; }
    else if (c === "," && stack.length > 0) lastSafeEnd = i - 1;
  }
  if (lastSafeEnd < 0) return null;

  let repaired = body.slice(0, lastSafeEnd + 1);
  // Strip any dangling whitespace/colon/comma at the tail
  repaired = repaired.replace(/[\s,:]+$/, "");
  if (!repaired.startsWith("{")) return null;

  // Re-walk repaired to compute remaining open brackets (string state should be clean now)
  const closing = [];
  let inStr2 = false, esc2 = false;
  for (let i = 0; i < repaired.length; i++) {
    const c = repaired[i];
    if (esc2) { esc2 = false; continue; }
    if (c === "\\") { esc2 = true; continue; }
    if (c === '"') { inStr2 = !inStr2; continue; }
    if (inStr2) continue;
    if (c === "{") closing.push("}");
    else if (c === "[") closing.push("]");
    else if (c === "}" || c === "]") closing.pop();
  }
  while (closing.length > 0) repaired += closing.pop();

  try { return JSON.parse(repaired); } catch { return null; }
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

// Detect when the assistant is asking for a date so we can show a calendar
// instead of forcing the user to type one. Returns "range" | "single" | null.
function getDatePromptMode(prompt) {
  if (!prompt) return null;
  const p = prompt.toLowerCase();
  const looksDatey = /\b(date|dates|when|depart|return|arrival|check.?in|check.?out)\b/.test(p);
  if (!looksDatey) return null;
  // Range first — both endpoints mentioned, or phrasing implies start+end together.
  if (
    /\bstart.*end\b/.test(p) ||
    /\bfrom\b.*\bto\b/.test(p) ||
    /\btravel\s+dates?\b/.test(p) ||
    /\btrip\s+dates?\b/.test(p) ||
    /\bdepart(?:ure)?\b.*\breturn\b/.test(p) ||
    /\bdates?\b/.test(p) && !/\bstart\s+date\b|\bend\s+date\b|\breturn\s+date\b/.test(p)
  ) {
    return "range";
  }
  // Single endpoint
  if (/\b(start|begin|depart(?:ure)?|trip\s+start|check.?in)\b/.test(p)) return "single";
  if (/\b(end|return|trip\s+end|check.?out)\b/.test(p)) return "single";
  // Generic "when do you want to travel" → range
  if (/\bwhen\b/.test(p)) return "range";
  return null;
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
  const dateMode = getDatePromptMode(text);
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
      <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed">{text}</p>
      {dateMode ? (
        <DateRangePicker mode={dateMode} onApply={(formatted) => onChipClick(formatted)} />
      ) : (
        chips.length > 0 && (
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
        )
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
  // If we couldn't parse but the payload *looks* like JSON, don't dump it on the user —
  // show a friendly retry message instead.
  const looksLikeJson = (s) => typeof s === "string" && /^\s*[`{\[]/.test(s.trim().replace(/^```(?:json)?\n?/i, ""));
  if (looksLikeJson(response.itinerary_beautified) || looksLikeJson(response.llm_raw)) {
    return "I drafted your itinerary but the response got cut off. Could you try again, or say 'regenerate' so I can rebuild it?";
  }
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

function historyToMessages(history = [], lastLlmRaw = null, pendingConfirmationCard = null) {
  const msgs = [];
  let id = 1;
  // Find index of the last assistant_raw entry so we can use lastLlmRaw for it
  let lastRawIdx = -1;
  history.forEach((h, i) => { if (h.role === "assistant_raw") lastRawIdx = i; });

  history.forEach((h, i) => {
    if (h.role === "user" && h.content) {
      msgs.push({ id: id++, role: "user", text: h.content });
    } else if (h.role === "assistant" && h.content) {
      // need_more prompts and formal request summaries stored as plain text.
      // If the historical message looks like a question (date prompt or has chips),
      // promote it to a QuestionCard so the user gets the inline calendar/chips
      // even after a refresh.
      const datey = getDatePromptMode(h.content);
      const chips = getChipsForPrompt(h.content);
      const promote = !!datey || chips.length > 0;
      msgs.push({
        id: id++,
        role: "assistant",
        text: h.content,
        ...(promote && { isQuestion: true, chips, collected: {} }),
      });
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
        // Don't show a raw JSON blob to the user when our repair didn't recover an itinerary.
        const looksLikeJson = /^\s*[`{\[]/.test(raw.trim().replace(/^```(?:json)?\n?/i, ""));
        msgs.push({
          id: id++,
          role: "assistant",
          text: looksLikeJson
            ? "I drafted your itinerary but the response got cut off. Could you try again, or say 'regenerate' so I can rebuild it?"
            : raw,
        });
      }
    }
  });

  // If the chat is paused on a confirmation card, upgrade the last assistant
  // message (the confirmation prompt text) to render as an interactive card.
  if (pendingConfirmationCard) {
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "assistant" && !msgs[i].itinerary) {
        msgs[i] = {
          ...msgs[i],
          text: "",
          isConfirmation: true,
          confirmationFields: pendingConfirmationCard,
        };
        break;
      }
    }
  }
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

const LAST_SESSION_KEY = "zarah:lastChatSessionId";

const Chat = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionIdParam = searchParams.get("session");
  const isExplicitNew = searchParams.get("new") === "1";
  const outletCtx = useOutletContext() || {};
  const sidebarCollapsed = !!outletCtx.sidebarCollapsed;

  // Restore the last open session when the user lands on /chat without a session param,
  // unless they explicitly asked for a new chat (?new=1). This makes tab-switching
  // (Itinerary → Chat) bring them back to the conversation they were in.
  useEffect(() => {
    if (sessionIdParam || isExplicitNew) return;
    const last = (() => {
      try { return localStorage.getItem(LAST_SESSION_KEY); } catch { return null; }
    })();
    if (last) navigate(`/chat?session=${last}`, { replace: true });
  }, [sessionIdParam, isExplicitNew, navigate]);

  const [query,          setQuery]          = useState("");
  const [messages,       setMessages]       = useState([]);
  const [sessionId,      setSessionId]      = useState(sessionIdParam || null);
  const [chatName,       setChatName]       = useState("New Chat");
  const [isEditingName,  setIsEditingName]  = useState(false);
  const [editNameValue,  setEditNameValue]  = useState("");
  const [isTyping,       setIsTyping]       = useState(false);
  // True only when the in-flight request is a heavyweight itinerary generation,
  // so the pipeline UI shows for those and a small "thinking" dot animation
  // shows for plain chat (e.g. "hi", "what's a good destination?").
  const [isGenerating,   setIsGenerating]   = useState(false);
  const [loadingSession, setLoadingSession] = useState(!!sessionIdParam);
  const [lastError,      setLastError]      = useState(null);
  const [kbWarning,      setKbWarning]      = useState(null);
  const [savedMsgIds,    setSavedMsgIds]    = useState(() => new Set());

  // History panel state
  const [showHistory,    setShowHistory]    = useState(false);
  const [historyList,    setHistoryList]    = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Client picker — gates a fresh chat until the user picks a client or skips.
  // showClientPicker is only true for fresh chats with no existing session.
  const [showClientPicker, setShowClientPicker] = useState(false);
  const [creatingChat,     setCreatingChat]     = useState(false);
  const [linkedClient,     setLinkedClient]     = useState(null);

  const messagesEndRef   = useRef(null);
  const chatNameInputRef = useRef(null);
  const textareaRef      = useRef(null);
  const { activeStages, elapsedSec } = useLoadingStages(isTyping);

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
      setLinkedClient(null);
      // Open the client picker first so the user can attach this trip to a
      // client (and pull in their preferences). The greeting + chat input
      // become available once they pick or skip.
      setShowClientPicker(true);
      return;
    }

    setLoadingSession(true);
    getChatSession(sessionIdParam)
      .then((res) => {
        const chat = res.chat ?? res;
        setChatName(chat.chat_name || "Chat");
        setSessionId(chat.session_id ?? sessionIdParam);
        // Pass last_llm_raw so the final itinerary entry is fully parseable.
        // pending_confirmation_card (set by backend when chat is paused on a confirmation
        // gate) tells us to re-render the last assistant message as a ConfirmationCard.
        const restored = historyToMessages(
          chat.history ?? [],
          chat.last_llm_raw,
          chat.pending_confirmation_card
        );
        setMessages(restored);
      })
      .catch(() => {
        // Session not found in store — open a fresh chat under this session id
        setSessionId(sessionIdParam);
        setChatName("New Chat");
      })
      .finally(() => setLoadingSession(false));
  }, [sessionIdParam, firstName]);

  // Common path for both "Pick client" and "Skip" — creates the chat session
  // up-front so the backend can attach the client_id (and seed preferences)
  // before any messages flow.
  const finishClientSelection = useCallback(async (clientId, clientObj) => {
    setCreatingChat(true);
    try {
      const res = await createChat("", clientId || null);
      const chat = res.chat ?? res;
      const sid = chat?.session_id;
      setLinkedClient(clientObj || chat?.client || null);
      setShowClientPicker(false);
      // Show greeting (slightly customised when a client is linked) right away.
      const greeting = ZARAH_GREETINGS[Math.floor(Math.random() * ZARAH_GREETINGS.length)];
      const baseText = greeting(firstName);
      const greetingText = clientObj
        ? `${baseText}\n\nI've pulled in preferences for **${clientObj.company_name ?? clientObj.company ?? "this client"}** — I'll keep them in mind while we plan.`
        : baseText;
      setMessages([{ id: 1, role: "assistant", text: greetingText, isGreeting: true }]);
      if (sid) {
        setSessionId(sid);
        try { localStorage.setItem(LAST_SESSION_KEY, sid); } catch {}
        const url = new URL(window.location.href);
        url.searchParams.set("session", sid);
        url.searchParams.delete("new");
        window.history.replaceState({}, "", url.toString());
      }
    } catch (err) {
      // If chat creation fails, fall back to the legacy on-first-message
      // creation path so the user is never blocked.
      console.error("createChat failed:", err);
      setShowClientPicker(false);
      const greeting = ZARAH_GREETINGS[Math.floor(Math.random() * ZARAH_GREETINGS.length)];
      setMessages([{ id: 1, role: "assistant", text: greeting(firstName), isGreeting: true }]);
    } finally {
      setCreatingChat(false);
    }
  }, [firstName]);

  const handleSend = useCallback(async (text, meta) => {
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
    // Only flag as itinerary-generation when the user clearly asks for one OR
    // we know we're in a generation flow (already collected fields, awaiting
    // confirmation, etc). "hi" and casual chat get the lightweight indicator.
    const looksLikeGenerate =
      GENERATE_INTENT_RE.test(msg) ||
      messages.some((m) => m.isConfirmation);          // user is confirming a card
    setIsTyping(true);
    setIsGenerating(looksLikeGenerate);
    try {
      const currentSid = sessionId;
      const response = await sendChatMessage(currentSid, msg, meta);
      const returnedSid = response.session_id ?? currentSid;
      if (returnedSid && returnedSid !== sessionId) {
        setSessionId(returnedSid);
        const url = new URL(window.location.href);
        url.searchParams.set("session", returnedSid);
        url.searchParams.delete("new");
        window.history.replaceState({}, "", url.toString());
      }
      if (returnedSid) {
        try { localStorage.setItem(LAST_SESSION_KEY, returnedSid); } catch {}
      }
      const isConfirmation = !!(response.need_confirmation && response.confirmation_fields);
      const isConversational = !!response.conversational && !!response.reply;
      const replyItinerary = isConfirmation || isConversational
        ? null
        : (response.itinerary ||
           tryParseJson(response.itinerary_beautified) ||
           tryParseJson(response.llm_raw) ||
           null);
      const replyText = isConfirmation
        ? ""
        : isConversational
          ? response.reply
          : (replyItinerary ? "" : formatChatResponse(response));
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
      // Network / backend hiccup — instead of a scary "Failed to fetch" toast,
      // greet the user and steer them toward the four details we actually need.
      // The real error still goes to the console for devs to debug.
      console.error("Chat request failed:", err);
      setLastError(null);   // don't show the error banner — friendly bubble replaces it
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "assistant",
          isFallback: true,
          fallbackContent: {
            greeting: `Hi ${firstName}, I'm Zarah — your travel planning assistant.`,
            intro: "Let's plan your trip together. Could you share a few details?",
            fields: [
              { label: "Destination", hint: "country, city, or route (e.g. Singapore or Dubai → Abu Dhabi)" },
              { label: "Duration",    hint: "number of nights / days (e.g. 5 nights)" },
              { label: "Travelers",   hint: "how many pax (e.g. 4 adults)" },
              { label: "Trip type",   hint: "leisure, corporate, honeymoon, incentive, family, etc." },
            ],
            outro: 'Optional but helpful: budget, hotel preference, dates, must-do activities. Once you share these, just say "generate itinerary" and I\'ll build a full day-by-day plan.',
          },
        },
      ]);
    } finally {
      setIsTyping(false);
      setIsGenerating(false);
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
    try { localStorage.removeItem(LAST_SESSION_KEY); } catch {}
    // ?new=1 prevents the mount-effect from immediately redirecting back to lastSessionId.
    navigate("/chat?new=1", { replace: true });
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
    if (!sessionId) return;
    const suggested = (itinerary?.title
      || (itinerary?.destination ? `${itinerary.destination} trip` : "")
      || chatName
      || "Itinerary").toString().slice(0, 80);
    const name = window.prompt("Name this itinerary:", suggested);
    if (name === null) return;          // user cancelled
    const finalName = name.trim() || suggested;
    const payload = {
      itinerary_name: finalName,
      chat_name: finalName,
      status: "saved",                   // initial status; user changes later
    };
    if (itinerary) payload.saved_itinerary = itinerary;
    try {
      await updateChatMetadata(sessionId, payload);
      setChatName(finalName);
    } catch {}
    setSavedMsgIds((prev) => new Set([...prev, msgId]));
    navigate("/itineraries");
  }, [sessionId, chatName, navigate]);

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
    <div className="flex items-center bg-white dark:bg-[#2A2929] rounded-2xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-gray-100 dark:border-white/10 px-4 py-2.5 transition-all duration-300 focus-within:shadow-[0_4px_14px_rgba(0,0,0,0.06)] focus-within:border-gray-200 dark:focus-within:border-white/20">
      <button
        className="p-1 text-gray-500 dark:text-gray-300 hover:text-gray-700 dark:hover:text-white transition-colors duration-200 cursor-pointer flex-shrink-0"
        aria-label="Attach file"
      >
        <Paperclip size={18} />
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
        className="flex-1 bg-transparent outline-none text-[15px] text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-3 py-1 font-poppins resize-none overflow-y-auto leading-relaxed"
        style={{ minHeight: "30px", maxHeight: "160px" }}
        disabled={loadingSession}
        autoFocus={!hasMessages}
      />
      <button
        onClick={() => handleSend()}
        disabled={isTyping || loadingSession || !query.trim()}
        className={`p-1 transition-colors duration-200 flex-shrink-0 ${
          query.trim() && !isTyping && !loadingSession
            ? "text-dark-300 dark:text-[#FFDE39] hover:text-black dark:hover:brightness-110 cursor-pointer"
            : "text-gray-400 dark:text-gray-500 cursor-not-allowed"
        }`}
        aria-label="Send"
      >
        {isTyping ? <RefreshCw size={18} className="animate-spin" /> : <ArrowUp size={20} />}
      </button>
    </div>
  );

  return (
    <div className="relative flex flex-col h-full animate-fadeIn overflow-hidden">

      {/* ── History slide-in panel ── */}
      <div
        className={`absolute inset-y-0 right-0 w-72 bg-white dark:bg-[#2A2929] z-30 flex flex-col shadow-[-6px_0_24px_rgba(0,0,0,0.08)] border-l border-gray-100/80 dark:border-white/10 transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] ${
          showHistory ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Panel header */}
        <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-[#FFFCE6] to-[#FFFAC5] dark:from-[#2A2929] dark:to-[#1F1F1F] border-b border-[#FFDE39]/25 dark:border-[#FFDE39]/15">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-white flex items-center gap-2">
            <Clock size={14} className="text-[#E6C800] dark:text-[#FFDE39]" />
            Chat History
          </h3>
          <button
            onClick={() => setShowHistory(false)}
            className="p-1 text-gray-400 hover:text-gray-600 dark:text-gray-300 dark:hover:text-white transition-colors cursor-pointer rounded"
          >
            <X size={15} />
          </button>
        </div>

        {/* New chat button */}
        <div className="px-3 py-2.5 border-b border-gray-100 dark:border-white/10">
          <button
            onClick={() => { handleNewChat(); setShowHistory(false); }}
            className="w-full flex items-center gap-2 bg-dark-300 dark:bg-[#FFDE39] text-white dark:text-[#1f1f1f] text-xs font-medium px-3 py-2 rounded-lg hover:bg-dark-200 dark:hover:brightness-95 transition-all duration-300 cursor-pointer"
          >
            <MessageSquarePlus size={13} className="text-[#FFDE39] dark:text-[#1f1f1f]" />
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
              <p className="text-xs text-gray-400 dark:text-gray-300">No past chats yet.</p>
              <p className="text-xs text-gray-300 dark:text-gray-400 mt-1">Start a conversation to see history here.</p>
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
                : "bg-gray-300 dark:bg-white/20 group-hover:bg-[#FFDE39]";
              return (
                <button
                  key={sid}
                  onClick={() => { navigate(`/chat?session=${sid}`); setShowHistory(false); }}
                  className={`w-full text-left px-4 py-3 border-b border-gray-50 dark:border-white/5 transition-all duration-200 cursor-pointer group last:border-0 ${
                    isActive
                      ? "bg-[#FFFAC5]/80 dark:bg-[#FFDE39]/15"
                      : "hover:bg-[#FFFCE6] dark:hover:bg-white/5"
                  }`}
                >
                  <div className="flex items-start gap-2.5">
                    <div className={`w-1.5 h-1.5 rounded-full mt-[5px] flex-shrink-0 transition-colors ${
                      isActive ? "bg-[#E6C800] dark:bg-[#FFDE39]" : statusColor
                    }`} />
                    <div className="flex-1 min-w-0">
                      <p className={`text-xs font-medium truncate transition-colors ${
                        isActive
                          ? "text-gray-900 dark:text-white"
                          : "text-gray-700 dark:text-gray-200 group-hover:text-gray-900 dark:group-hover:text-white"
                      }`}>
                        {name}
                      </p>
                      {tripInfo && (
                        <p className="text-[10px] text-gray-400 dark:text-gray-400 truncate mt-0.5">{tripInfo}</p>
                      )}
                      {date && (
                        <p className="text-[10px] text-gray-300 dark:text-gray-500 mt-0.5">{date}</p>
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
        <div className="flex-1 flex items-center justify-center bg-gray-100 dark:bg-[#2A2929] rounded-2xl">
          <RefreshCw size={24} className="animate-spin text-gray-400 dark:text-gray-300" />
        </div>

      ) : !hasMessages ? (
        /* ── Empty state ── */
        <div className="flex-1 flex flex-col animate-fadeIn min-h-0">
          {/* History pill — outside the chat panel, top-right of the page area */}
          <div className="flex justify-end mb-2 flex-shrink-0">
            <button
              onClick={openHistory}
              className="flex items-center gap-1.5 bg-dark-300 text-white text-[12px] font-medium px-3.5 py-1.5 rounded-full shadow-[0_2px_6px_rgba(0,0,0,0.08)] hover:bg-dark-200 hover:-translate-y-0.5 transition-all duration-300 cursor-pointer"
            >
              <Clock size={13} />
              History
            </button>
          </div>

          {/* Chat panel — narrower than full container, centered */}
          <div className="mx-auto w-full max-w-[1440px] flex-1 flex flex-col px-4 sm:px-6 py-3 relative rounded-2xl bg-[#f9f8f4] dark:bg-white/[0.02] dark:focus-within:bg-white/[0.04] transition-all duration-400 ease-[cubic-bezier(0.22,1,0.36,1)]">

          {/* Centered greeting + input + suggestion cards (or client picker) */}
          <div className="flex-1 flex flex-col items-center justify-center">
            <div className="w-full max-w-[760px]">
              {showClientPicker ? (
                <ClientPickerPanel
                  busy={creatingChat}
                  onPick={({ clientId, client }) => finishClientSelection(clientId, client)}
                  onSkip={() => finishClientSelection(null, null)}
                />
              ) : (
                <>
              {/* Greeting block — left-aligned to match Figma */}
              <div className="mb-6 pl-1">
                <p className="text-[16px] text-[#1f1f1f] dark:text-gray-300 font-normal mb-1 font-poppins">
                  Hello <span className="text-[#E6C800] font-medium">{firstName}</span>
                </p>
                <h1 className="text-[30px] sm:text-[34px] font-bold text-[#1f1f1f] dark:text-white leading-tight font-poppins tracking-tight">
                  {welcomeLine}
                </h1>
              </div>

              {inputBar}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => handleSend(s.text)}
                    className="text-left bg-white dark:bg-[#2A2929] rounded-xl border border-gray-100 dark:border-white/10 shadow-[0_1px_2px_rgba(0,0,0,0.02)] p-3.5 text-[12px] text-gray-600 dark:text-gray-300 leading-[1.5] hover:shadow-[0_3px_10px_rgba(0,0,0,0.05)] hover:-translate-y-0.5 hover:border-gray-200 dark:hover:border-white/20 transition-all duration-300 group flex flex-col justify-between min-h-[88px] font-poppins"
                  >
                    <span className="line-clamp-3">{s.text}</span>
                    <ArrowRight size={13} className="mt-1.5 text-gray-400 group-hover:text-gray-700 dark:group-hover:text-white transition-colors duration-200 self-end" />
                  </button>
                ))}
              </div>
                </>
              )}
            </div>
          </div>
          </div>
        </div>

      ) : (
        /* ── Active chat ── */
        <div className="mx-auto w-full max-w-[1620px] flex-1 flex flex-col overflow-hidden animate-fadeIn bg-[#f9f8f4] dark:bg-white/[0.02] rounded-2xl p-3 transition-all duration-400 ease-[cubic-bezier(0.22,1,0.36,1)]">
          {/* Sub-header strip — chat title + actions, full width (no outer gutter) */}
          <div className="bg-white dark:bg-[#2A2929] rounded-xl border border-gray-100 dark:border-white/10 shadow-[0_1px_3px_rgba(0,0,0,0.02)] px-5 py-2.5 flex items-center justify-between mb-3 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <MessageSquare size={14} className="text-[#E6C800] flex-shrink-0" />
              {isEditingName ? (
                <div className="flex items-center gap-1.5">
                  <input
                    ref={chatNameInputRef}
                    value={editNameValue}
                    onChange={(e) => setEditNameValue(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") saveName(); if (e.key === "Escape") cancelEditName(); }}
                    className="text-[13px] font-medium text-gray-800 dark:text-gray-100 bg-gray-50 dark:bg-white/10 rounded-md px-2 py-0.5 outline-none border border-gray-300 dark:border-white/20 focus:border-brand-400 transition-colors duration-200 font-poppins"
                  />
                  <button onClick={saveName} className="p-0.5 text-green-500 hover:text-green-600 cursor-pointer"><Check size={13} /></button>
                  <button onClick={cancelEditName} className="p-0.5 text-gray-400 hover:text-gray-600 cursor-pointer"><X size={13} /></button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 group min-w-0">
                  <h2 className="text-[13px] font-medium text-gray-800 dark:text-gray-100 font-poppins truncate">{chatName}</h2>
                  <button
                    onClick={startEditName}
                    title="Rename chat"
                    className="p-0.5 text-gray-400 dark:text-gray-400 hover:text-gray-700 dark:hover:text-white opacity-0 group-hover:opacity-100 transition-all duration-200 cursor-pointer flex-shrink-0"
                  >
                    <Pencil size={12} />
                  </button>
                </div>
              )}
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={handleNewChat}
                className="flex items-center gap-1.5 text-[12px] font-medium text-gray-700 dark:text-gray-200 hover:text-[#1f1f1f] dark:hover:text-white hover:bg-gray-50 dark:hover:bg-white/5 px-2.5 py-1.5 rounded-md transition-all duration-200 cursor-pointer"
              >
                <MessageSquarePlus size={13} className="text-gray-500 dark:text-gray-300" />
                New Chat
              </button>
              <button
                onClick={openHistory}
                className="flex items-center gap-1.5 text-[12px] font-medium text-gray-700 dark:text-gray-200 hover:text-[#1f1f1f] dark:hover:text-white hover:bg-gray-50 dark:hover:bg-white/5 px-2.5 py-1.5 rounded-md transition-all duration-200 cursor-pointer"
              >
                <Clock size={13} className="text-gray-500 dark:text-gray-300" />
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
                      <div className="bg-white dark:bg-[#2A2929] rounded-xl px-4 py-2.5 shadow-[0_1px_3px_rgba(0,0,0,0.03)] border border-gray-200/80 dark:border-white/10 max-w-[70%] text-[14px] text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
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
                        onConfirm={(currency) => handleSend("confirm", { currency })}
                      />
                    </div>
                  );
                }

                if (msg.isFallback && msg.fallbackContent) {
                  const fb = msg.fallbackContent;
                  return (
                    <div key={msg.id} className="flex justify-start animate-fadeIn">
                      <div className="bg-white dark:bg-[#2A2929] border border-gray-100 dark:border-white/10 rounded-2xl px-5 py-4 max-w-[640px] shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
                        <p className="text-[14px] font-semibold text-gray-900 dark:text-white">
                          {fb.greeting}
                        </p>
                        <p className="text-[13px] text-gray-700 dark:text-gray-300 mt-1.5 leading-relaxed">
                          {fb.intro}
                        </p>
                        <ul className="mt-3 space-y-1.5">
                          {fb.fields.map((f) => (
                            <li key={f.label} className="flex gap-2 text-[13px] leading-relaxed">
                              <span className="text-[#E6C800] mt-0.5">•</span>
                              <span>
                                <span className="font-semibold text-gray-900 dark:text-white">{f.label}</span>
                                <span className="text-gray-600 dark:text-gray-400"> — {f.hint}</span>
                              </span>
                            </li>
                          ))}
                        </ul>
                        <p className="text-[12.5px] text-gray-500 dark:text-gray-400 mt-3 leading-relaxed">
                          {fb.outro}
                        </p>
                      </div>
                    </div>
                  );
                }

                if (isItinerary) {
                  // Itinerary card stays white per spec — design unchanged
                  return (
                    <div key={msg.id} className="flex justify-start animate-fadeIn">
                      <div className="w-full bg-white dark:bg-[#2A2929] rounded-xl px-4 py-3.5 shadow-[0_1px_4px_rgba(0,0,0,0.04)] border border-gray-100 dark:border-white/10">
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
                      <div className="bg-white dark:bg-[#2A2929] rounded-[11px] px-4 py-3">
                        <Sparkles size={18} className="text-[#1f1f1f] dark:text-[#FFDE39] fill-[#1f1f1f] dark:fill-[#FFDE39] mb-2" />
                        {(() => {
                          // Date-prompt safety net: any assistant text the regex
                          // recognises as a date question gets the inline calendar,
                          // even if it slipped through without an isQuestion flag.
                          const datey = !msg.isQuestion ? getDatePromptMode(msg.text) : null;
                          if (msg.isQuestion) {
                            return (
                              <QuestionCard
                                text={msg.text}
                                collected={msg.collected || {}}
                                chips={msg.chips || []}
                                onChipClick={(chip) => handleSend(chip)}
                              />
                            );
                          }
                          return (
                            <>
                              <p className="text-[14px] text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap font-poppins">
                                {msg.text}
                              </p>
                              {datey && (
                                <DateRangePicker mode={datey} onApply={(formatted) => handleSend(formatted)} />
                              )}
                            </>
                          );
                        })()}
                      </div>
                    </div>
                  </div>
                );
              })}

              {isTyping && !isGenerating && (
                <div className="flex justify-start animate-fadeIn">
                  <div className="bg-white dark:bg-[#2A2929] border border-gray-100 dark:border-white/10 rounded-2xl px-4 py-3 shadow-[0_1px_3px_rgba(0,0,0,0.04)] flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-300 animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-300 animate-bounce" style={{ animationDelay: "120ms" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-300 animate-bounce" style={{ animationDelay: "240ms" }} />
                  </div>
                </div>
              )}

              {isTyping && isGenerating && (() => {
                const lastDoneIdx = PIPELINE_STAGES.reduce(
                  (acc, s, idx) => (activeStages.includes(s.id) ? idx : acc),
                  -1
                );
                const visibleIdx = Math.max(0, lastDoneIdx);
                // Progress: each stage worth ~20%; current stage shows partial (~half) until next fires
                const progressPct = lastDoneIdx < 0
                  ? 6
                  : Math.min(100, ((lastDoneIdx + 0.5) / PIPELINE_STAGES.length) * 100);
                const currentTip = PIPELINE_TIPS[Math.floor(elapsedSec / 5) % PIPELINE_TIPS.length];
                const elapsedLabel = elapsedSec < 60
                  ? `${elapsedSec}s`
                  : `${Math.floor(elapsedSec / 60)}m ${elapsedSec % 60}s`;
                return (
                  <div className="flex justify-start animate-fadeIn">
                    <div
                      className="relative rounded-2xl w-[360px] max-w-[92%] overflow-hidden shadow-[0_8px_28px_rgba(255,222,57,0.18)] dark:shadow-[0_8px_28px_rgba(0,0,0,0.35)]"
                      style={{
                        padding: "1.5px",
                        background: "linear-gradient(135deg,#FFDE39 0%,#FFF690 45%,#E9E6CA 100%)",
                      }}
                    >
                      <div className="bg-white dark:bg-[#2A2929] rounded-[15px] overflow-hidden">
                        {/* Top progress strip */}
                        <div className="relative h-1 bg-gray-100 dark:bg-white/5 overflow-hidden">
                          <div
                            className="absolute inset-y-0 left-0 transition-[width] duration-700 ease-[cubic-bezier(0.22,1,0.36,1)] bg-gradient-to-r from-[#FFDE39] via-[#FFF690] to-[#FFDE39] bg-[length:200%_100%] animate-shimmer"
                            style={{ width: `${progressPct}%` }}
                          />
                        </div>

                        <div className="px-4 pt-3.5 pb-4">
                          {/* Header row */}
                          <div className="flex items-center justify-between mb-3.5">
                            <div className="flex items-center gap-2.5 min-w-0">
                              <div className="relative w-8 h-8 rounded-xl bg-gradient-to-br from-[#FFDE39] to-[#FFB800] flex items-center justify-center shadow-[0_3px_10px_rgba(255,222,57,0.45)] flex-shrink-0">
                                <Sparkles size={15} className="text-[#1f1f1f]" strokeWidth={2.5} />
                                <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-green-400 border-2 border-white dark:border-[#2A2929] animate-pulse" />
                              </div>
                              <div className="min-w-0">
                                <p className="text-[9.5px] font-bold text-gray-400 dark:text-gray-400 uppercase tracking-[0.16em] leading-none">Zarah is working</p>
                                <p className="text-[13.5px] font-bold text-gray-900 dark:text-white leading-tight mt-1">Building your itinerary</p>
                              </div>
                            </div>
                            <div className="text-right pl-2 flex-shrink-0">
                              <p className="text-[9.5px] text-gray-400 dark:text-gray-500 leading-none">Step {visibleIdx + 1}/{PIPELINE_STAGES.length}</p>
                              <p className="text-[12px] tabular-nums font-semibold text-gray-700 dark:text-gray-200 mt-1">{elapsedLabel}</p>
                            </div>
                          </div>

                          {/* Vertical timeline */}
                          <div className="relative">
                            <div className="absolute left-[10.5px] top-3 bottom-3 w-px bg-gradient-to-b from-gray-200 via-gray-200 to-gray-100 dark:from-white/10 dark:via-white/10 dark:to-white/5" />
                            <div className="space-y-2.5">
                              {PIPELINE_STAGES.map((stage, idx) => {
                                const StageIcon = stage.icon;
                                const status =
                                  idx < lastDoneIdx ? "past"
                                  : idx === lastDoneIdx ? "current"
                                  : "future";
                                return (
                                  <div
                                    key={stage.id}
                                    className={`relative flex items-center gap-3 transition-all duration-500 ${
                                      status === "future" ? "opacity-40" : "opacity-100 animate-fadeIn"
                                    }`}
                                  >
                                    <div className={`relative z-10 w-[22px] h-[22px] rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-500 ${
                                      status === "current"
                                        ? "bg-gradient-to-br from-[#FFDE39] to-[#FFB800] shadow-[0_0_0_4px_rgba(255,222,57,0.18)] scale-110"
                                        : status === "past"
                                          ? "bg-green-500 dark:bg-green-500"
                                          : "bg-gray-100 dark:bg-white/10 border border-gray-200 dark:border-white/10"
                                    }`}>
                                      {status === "past"
                                        ? <Check size={11} strokeWidth={3} className="text-white" />
                                        : <StageIcon size={11} className={
                                            status === "current" ? "text-[#1f1f1f]" : "text-gray-400 dark:text-gray-400"
                                          } strokeWidth={status === "current" ? 2.5 : 2} />}
                                      {status === "current" && (
                                        <span className="absolute inset-0 rounded-full border-2 border-[#FFDE39] animate-pulseRing pointer-events-none" />
                                      )}
                                    </div>
                                    <p className={`flex-1 text-[12.5px] leading-snug transition-colors duration-300 ${
                                      status === "current" ? "text-gray-900 dark:text-white font-semibold"
                                      : status === "past" ? "text-gray-600 dark:text-gray-400"
                                      : "text-gray-400 dark:text-gray-500"
                                    }`}>
                                      {stage.label}
                                    </p>
                                    {status === "current" && (
                                      <span className="text-[9.5px] font-bold uppercase tracking-wider text-[#8A6800] dark:text-[#1f1f1f] bg-[#FFFAC5] dark:bg-[#FFDE39] px-2 py-0.5 rounded-full whitespace-nowrap flex-shrink-0">
                                        In progress
                                      </span>
                                    )}
                                    {status === "past" && (
                                      <span className="text-[9.5px] font-bold uppercase tracking-wider text-green-600 dark:text-green-400 whitespace-nowrap flex-shrink-0">
                                        Done
                                      </span>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>

                          {/* Rotating helpful tip — appears once we're a few seconds in */}
                          {elapsedSec > 8 && (
                            <div
                              key={currentTip}
                              className="mt-3.5 pt-3 border-t border-gray-100 dark:border-white/10 flex items-start gap-2.5 animate-fadeIn"
                            >
                              <div className="w-5 h-5 rounded-full bg-[#FFFAC5] dark:bg-[#FFDE39]/15 flex items-center justify-center flex-shrink-0 mt-[1px]">
                                <Sparkles size={10} className="text-[#8A6800] dark:text-[#FFDE39]" />
                              </div>
                              <p className="text-[10.5px] text-gray-500 dark:text-gray-400 leading-snug">
                                {currentTip}
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}
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
              {!showClientPicker && inputBar}
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
