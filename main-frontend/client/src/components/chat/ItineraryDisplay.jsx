import React, { useState } from "react";
import {
  ChevronDown, ChevronUp, Download, BookmarkPlus, Trash2,
  Check, Minus, MapPin, Users, Moon, AlertCircle, Building2,
} from "lucide-react";

// ── PDF generator ─────────────────────────────────────────────────────────────
export function generateItineraryPDF(itinerary) {
  const days = itinerary.days || [];
  const cb   = itinerary.cost_breakdown || {};
  const hotels = itinerary.hotels || [];
  const inclusions = itinerary.inclusions || [];
  const exclusions = itinerary.exclusions || [];
  const guidelines = itinerary.important_guidelines || [];

  const dayHTML = days.map((day) => `
    <div class="day-card">
      <div class="day-header">
        <span class="day-num">Day ${day.day}${day.city ? ` &nbsp;·&nbsp; ${day.city}` : ""}</span>
        ${day.date ? `<span class="day-date">${day.date}</span>` : ""}
        ${day.summary ? `<p class="day-summary">${day.summary}</p>` : ""}
      </div>
      <div class="day-body">
        ${["Morning","Afternoon","Evening"].filter(p => day[p.toLowerCase()]).map(p => `
          <div class="period">
            <div class="period-label">${p}</div>
            <div class="period-content">${day[p.toLowerCase()]}</div>
          </div>`).join("")}
        ${day.transport_note ? `
          <div class="period" style="background:#eff6ff;border-radius:4px;padding:4px 8px;margin-top:6px;">
            <div class="period-label" style="color:#3b82f6;">Transport</div>
            <div class="period-content" style="color:#1d4ed8;">${day.transport_note}</div>
          </div>` : ""}
        ${day.hotel?.name ? `
          <div class="hotel-tag">
            Hotel: ${day.hotel.name}${day.hotel.area ? `, ${day.hotel.area}` : ""}${day.hotel.category ? ` (${day.hotel.category})` : ""}
          </div>` : ""}
      </div>
    </div>`).join("");

  const costHTML = Object.keys(cb).length ? `
    <section>
      <h2>Cost Breakdown</h2>
      <table class="data-table">
        ${Object.entries(cb).map(([k, v]) => `
          <tr class="${k.includes("total") || k.includes("grand") ? "total-row" : ""}">
            <td>${k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</td>
            <td class="amount">${v}</td>
          </tr>`).join("")}
      </table>
    </section>` : "";

  const hotelsHTML = hotels.length ? `
    <section>
      <h2>Hotel Options</h2>
      <table class="data-table">
        ${hotels.map((h) => {
          const price = h.price_per_night_inr || h.price_per_night_in_inr ||
            (h.price_per_night ? `${h.currency || ""} ${h.price_per_night}/night` : "—");
          return `<tr><td>${h.city ? h.city + " — " : ""}${h.name}${h.area ? `, ${h.area}` : ""}</td><td class="amount">${price}</td></tr>`;
        }).join("")}
      </table>
    </section>` : "";

  const inclExclHTML = (inclusions.length || exclusions.length) ? `
    <section>
      <h2>Inclusions &amp; Exclusions</h2>
      <div class="two-col">
        <div>
          <strong>Inclusions</strong>
          <ul class="incl-list green">${inclusions.map((i) => `<li>${i}</li>`).join("")}</ul>
        </div>
        <div>
          <strong>Exclusions</strong>
          <ul class="incl-list red">${exclusions.map((e) => `<li>${e}</li>`).join("")}</ul>
        </div>
      </div>
    </section>` : "";

  const guidelinesHTML = guidelines.length ? `
    <section>
      <h2>Important Guidelines</h2>
      <ul class="incl-list amber">${guidelines.map((g) => `<li>${g}</li>`).join("")}</ul>
    </section>` : "";

  const notesHTML = itinerary.notes
    ? `<section><h2>Notes</h2><p class="notes-text">${itinerary.notes}</p></section>`
    : "";

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${itinerary.title || "Travel Itinerary"}</title>
  <style>
    @page { margin: 18mm 20mm; size: A4; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: "Segoe UI", Arial, sans-serif; font-size: 11px; color: #1a1a1a; line-height: 1.55; }
    .cover { background: #1a1a1a; color: #fff; padding: 28px 32px 24px; margin-bottom: 24px; }
    .cover h1 { font-size: 20px; font-weight: 700; margin-bottom: 8px; }
    .cover-pills { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .pill { background: rgba(255,222,57,0.15); border: 1px solid rgba(255,222,57,0.35); color: #FFE066; padding: 3px 10px; border-radius: 20px; font-size: 11px; }
    h2 { font-size: 13px; font-weight: 700; color: #1a1a1a; margin: 18px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #FFDE39; }
    .day-card { margin-bottom: 12px; border: 1px solid #e0e0e0; border-radius: 6px; overflow: hidden; break-inside: avoid; page-break-inside: avoid; }
    .day-header { background: #f5f5f5; padding: 9px 14px; border-bottom: 1px solid #e0e0e0; }
    .day-num { font-weight: 700; font-size: 12px; }
    .day-date { color: #888; margin-left: 10px; font-size: 10px; }
    .day-summary { color: #555; margin-top: 3px; font-style: italic; font-size: 10.5px; }
    .day-body { padding: 10px 14px; }
    .period { margin-bottom: 7px; }
    .period-label { font-weight: 700; font-size: 10px; color: #8A6800; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 2px; }
    .period-content { color: #333; }
    .activities { margin-top: 7px; }
    .activities ul { list-style: disc; padding-left: 16px; color: #444; }
    .activities li { margin-bottom: 2px; }
    .hotel-tag { margin-top: 7px; font-size: 10.5px; color: #555; background: #f0f0f0; padding: 3px 9px; border-radius: 4px; display: inline-block; }
    .data-table { width: 100%; border-collapse: collapse; margin-top: 4px; }
    .data-table tr:nth-child(even) { background: #fafafa; }
    .data-table td { padding: 5px 10px; border: 1px solid #ebebeb; vertical-align: top; }
    .data-table .amount { text-align: right; font-weight: 600; white-space: nowrap; }
    .total-row td { font-weight: 700; background: #FFFCE6 !important; border-top: 2px solid #FFDE39; }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    .incl-list { list-style: none; padding: 0; margin-top: 6px; }
    .incl-list li { padding: 3px 0 3px 18px; position: relative; margin-bottom: 2px; }
    .incl-list.green li::before { content: "✓"; position: absolute; left: 0; color: #22c55e; font-weight: 700; }
    .incl-list.red li::before { content: "✕"; position: absolute; left: 0; color: #ef4444; font-weight: 700; }
    .incl-list.amber li::before { content: "•"; position: absolute; left: 0; color: #f59e0b; font-weight: 700; }
    .notes-text { color: #555; font-style: italic; }
    section { margin-bottom: 14px; }
    .footer { margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 9.5px; color: #999; }
  </style>
</head>
<body>
  <div class="cover">
    <h1>${itinerary.title || "Travel Itinerary"}</h1>
    <div class="cover-pills">
      ${itinerary.destination ? `<span class="pill">&#x1F4CD; ${itinerary.destination}</span>` : ""}
      ${itinerary.pax        ? `<span class="pill">&#x1F465; ${itinerary.pax} Pax</span>` : ""}
      ${itinerary.duration_days ? `<span class="pill">&#x1F5D3; ${itinerary.duration_days} Days</span>` : ""}
      ${itinerary.event_type ? `<span class="pill">${itinerary.event_type}</span>` : ""}
    </div>
  </div>

  ${(itinerary.itinerary_summary || itinerary.overview) ? `
  <section style="background:#fafafa;border-left:3px solid #FFDE39;padding:10px 14px;border-radius:0 6px 6px 0;margin-bottom:14px;">
    <h2 style="margin-bottom:6px;">Itinerary Summary</h2>
    <p style="color:#444;line-height:1.6;">${itinerary.itinerary_summary || itinerary.overview}</p>
  </section>` : ""}

  <section>
    <h2>Day-by-Day Itinerary</h2>
    ${dayHTML || "<p>No day-by-day breakdown available.</p>"}
  </section>

  ${costHTML}
  ${hotelsHTML}
  ${inclExclHTML}
  ${guidelinesHTML}
  ${notesHTML}

  <div class="footer">
    Generated by Zarah &middot; AI Travel Planning Assistant &nbsp;&middot;&nbsp;
    ${new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}
  </div>
  <script>window.onload = function () { window.print(); };</script>
</body>
</html>`;

  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url  = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 90000);
}

// ── DayCard ────────────────────────────────────────────────────────────────────
function DayCard({ day, isOpen, onToggle }) {
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-[#FFFCE6] transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="w-7 h-7 rounded-full bg-dark-300 text-white text-xs font-bold flex items-center justify-center flex-shrink-0">
            {day.day}
          </span>
          <div className="min-w-0">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-sm font-semibold text-gray-800">
                {day.city || `Day ${day.day}`}
              </span>
              {day.date && (
                <span className="text-xs text-gray-400">{day.date}</span>
              )}
            </div>
            {day.summary && (
              <p className="text-xs text-gray-500 mt-0.5 truncate">{day.summary}</p>
            )}
          </div>
        </div>
        {isOpen
          ? <ChevronUp  size={15} className="text-gray-400 flex-shrink-0" />
          : <ChevronDown size={15} className="text-gray-400 flex-shrink-0" />}
      </button>

      {isOpen && (
        <div className="px-4 py-3.5 bg-white space-y-3 border-t border-gray-100">
          {[["Morning", day.morning], ["Afternoon", day.afternoon], ["Evening", day.evening]]
            .filter(([, v]) => v)
            .map(([label, content]) => {
              // Split the time-block prose into separate lines whenever a new
              // HH:MM marker appears so each timed activity sits on its own row.
              // Handles "07:30 –", "9:00 -", "07:30:" forms. Trim/dedupe blanks.
              const parts = String(content)
                .split(/(?=\b\d{1,2}:\d{2}\b)/g)
                .map((s) => s.trim())
                .filter(Boolean);
              return (
                <div key={label}>
                  <span className="text-[10px] font-bold text-[#8A6800] uppercase tracking-wider">
                    {label}
                  </span>
                  <ul className="mt-1 space-y-1">
                    {parts.map((line, i) => (
                      <li key={i} className="text-sm text-gray-700 leading-relaxed">
                        {line}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}

          {day.transport_note && (
            <div className="flex items-start gap-2 bg-blue-50 rounded-lg px-3 py-2">
              <span className="text-[10px] font-bold text-blue-500 uppercase tracking-wider flex-shrink-0 mt-0.5">Transport</span>
              <p className="text-xs text-blue-700 leading-relaxed">{day.transport_note}</p>
            </div>
          )}

          {day.hotel?.name && (
            <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
              <Building2 size={12} className="text-gray-400 flex-shrink-0" />
              <span className="text-xs text-gray-600">
                {day.hotel.name}
                {day.hotel.area ? `, ${day.hotel.area}` : ""}
              </span>
              {day.hotel.category && (
                <span className="text-[10px] bg-[#FFFAC5] border border-[#FFDE39]/30 text-[#8A6800] px-2 py-0.5 rounded-full ml-1">
                  {day.hotel.category}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── ItineraryDisplay ──────────────────────────────────────────────────────────
export default function ItineraryDisplay({ itinerary, sessionId, onSave, onDiscard, saved }) {
  const [expandedDays, setExpandedDays] = useState(
    () => new Set(itinerary.days?.slice(0, 1).map((d) => d.day) ?? [])
  );
  const [showCost, setShowCost] = useState(true);
  const [saving,   setSaving]   = useState(false);

  const toggleDay = (n) =>
    setExpandedDays((prev) => {
      const s = new Set(prev);
      s.has(n) ? s.delete(n) : s.add(n);
      return s;
    });

  const cb         = itinerary.cost_breakdown || {};
  const hasCost    = Object.keys(cb).length > 0;
  const hotels     = itinerary.hotels || [];
  const inclusions = itinerary.inclusions || [];
  const exclusions = itinerary.exclusions || [];
  const guidelines = itinerary.important_guidelines || [];

  const handleSave = async () => {
    setSaving(true);
    try { await onSave(); } finally { setSaving(false); }
  };

  return (
    <div className="w-full space-y-3">

      {/* ── Header card ── */}
      <div className="bg-dark-300 text-white rounded-xl px-5 py-4">
        <h3 className="text-base font-bold leading-snug">
          {itinerary.title || "Travel Itinerary"}
        </h3>
        <div className="flex flex-wrap gap-2 mt-2.5">
          {itinerary.destination && (
            <span className="flex items-center gap-1 text-xs bg-white/10 px-2.5 py-1 rounded-full">
              <MapPin size={10} /> {itinerary.destination}
            </span>
          )}
          {itinerary.pax && (
            <span className="flex items-center gap-1 text-xs bg-white/10 px-2.5 py-1 rounded-full">
              <Users size={10} /> {itinerary.pax} Pax
            </span>
          )}
          {itinerary.duration_days && (
            <span className="flex items-center gap-1 text-xs bg-white/10 px-2.5 py-1 rounded-full">
              <Moon size={10} /> {itinerary.duration_days} Days
            </span>
          )}
          {itinerary.event_type && (
            <span className="text-xs bg-[#FFDE39]/20 text-[#FFE066] border border-[#FFDE39]/30 px-2.5 py-1 rounded-full capitalize">
              {itinerary.event_type}
            </span>
          )}
        </div>
      </div>

      {/* ── Itinerary Summary ── */}
      {(itinerary.itinerary_summary || itinerary.overview) && (
        <div className="bg-gray-50 rounded-xl px-5 py-4 border border-gray-100">
          <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2">Itinerary Summary</p>
          <p className="text-sm text-gray-700 leading-relaxed">{itinerary.itinerary_summary || itinerary.overview}</p>
        </div>
      )}

      {/* ── Day-by-day ── */}
      {itinerary.days?.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">
              Day-by-Day Itinerary
            </p>
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={() => setExpandedDays(new Set(itinerary.days.map((d) => d.day)))}
                className="text-[10px] text-gray-400 hover:text-gray-600 px-2 py-0.5 rounded hover:bg-gray-100 transition-colors"
              >
                Expand all
              </button>
              <button
                type="button"
                onClick={() => setExpandedDays(new Set())}
                className="text-[10px] text-gray-400 hover:text-gray-600 px-2 py-0.5 rounded hover:bg-gray-100 transition-colors"
              >
                Collapse all
              </button>
            </div>
          </div>
          <div className="space-y-1.5">
            {itinerary.days.map((day) => (
              <DayCard
                key={day.day}
                day={day}
                isOpen={expandedDays.has(day.day)}
                onToggle={() => toggleDay(day.day)}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Cost breakdown ── */}
      {hasCost && (
        <div>
          <button
            type="button"
            onClick={() => setShowCost((v) => !v)}
            className="flex items-center gap-1.5 text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2 hover:text-gray-700 transition-colors w-full text-left"
          >
            Cost Breakdown
            {showCost ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
          {showCost && (
            <div className="border border-gray-200 rounded-xl overflow-hidden">
              {Object.entries(cb).map(([k, v], i) => {
                const isTotal = k.includes("total") || k.includes("grand");
                return (
                  <div
                    key={k}
                    className={`flex justify-between px-4 py-2.5 text-sm ${
                      i % 2 === 0 ? "bg-white" : "bg-gray-50"
                    } ${isTotal ? "font-semibold border-t-2 border-[#FFDE39] bg-[#FFFCE6]!" : ""}`}
                  >
                    <span className={`capitalize ${isTotal ? "text-gray-900" : "text-gray-600"}`}>
                      {k.replace(/_/g, " ")}
                    </span>
                    <span className={`font-medium ${isTotal ? "text-gray-900" : "text-gray-800"}`}>
                      {v}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Hotels ── */}
      {hotels.length > 0 && (
        <div>
          <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2">
            Hotel Options
          </p>
          <div className="border border-gray-200 rounded-xl overflow-hidden divide-y divide-gray-100">
            {hotels.slice(0, 5).map((h, i) => {
              const price =
                h.price_per_night_inr ||
                h.price_per_night_in_inr ||
                (h.price_per_night ? `${h.currency || ""} ${h.price_per_night}/night` : null);
              return (
                <div key={i} className="flex justify-between items-center px-4 py-2.5 bg-white hover:bg-[#FFFCE6] transition-colors">
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-gray-800 truncate">{h.name}</span>
                    {(h.city || h.area) && (
                      <span className="text-xs text-gray-400 ml-2">
                        {[h.city, h.area].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </div>
                  {price && (
                    <span className="text-xs text-gray-600 font-medium ml-3 flex-shrink-0">{price}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Inclusions & Exclusions ── */}
      {(inclusions.length > 0 || exclusions.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {inclusions.length > 0 && (
            <div>
              <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2">
                Inclusions
              </p>
              <ul className="space-y-1.5">
                {inclusions.map((inc, i) => (
                  <li key={i} className="flex gap-2 text-xs text-gray-600 leading-relaxed">
                    <Check size={12} className="text-green-500 flex-shrink-0 mt-0.5" />
                    {inc}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {exclusions.length > 0 && (
            <div>
              <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2">
                Exclusions
              </p>
              <ul className="space-y-1.5">
                {exclusions.map((exc, i) => (
                  <li key={i} className="flex gap-2 text-xs text-gray-600 leading-relaxed">
                    <Minus size={12} className="text-red-400 flex-shrink-0 mt-0.5" />
                    {exc}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ── Guidelines ── */}
      {guidelines.length > 0 && (
        <div>
          <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2">
            Important Guidelines
          </p>
          <ul className="space-y-1.5">
            {guidelines.map((g, i) => (
              <li key={i} className="flex gap-2 text-xs text-gray-600 leading-relaxed">
                <AlertCircle size={12} className="text-amber-400 flex-shrink-0 mt-0.5" />
                {g}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Notes ── */}
      {itinerary.notes && (
        <p className="text-xs text-gray-500 italic border-l-2 border-gray-200 pl-3">
          {itinerary.notes}
        </p>
      )}

      {/* ── Action bar ── */}
      <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
        {saved ? (
          <>
            <div className="flex items-center gap-1.5 text-xs text-green-600 font-medium">
              <Check size={13} /> Saved to Itineraries
            </div>
            <div className="flex-1" />
            <button
              type="button"
              onClick={() => generateItineraryPDF(itinerary)}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded-lg transition-colors"
            >
              <Download size={13} /> Download PDF
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => generateItineraryPDF(itinerary)}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded-lg transition-colors"
            >
              <Download size={13} /> Download PDF
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 text-xs font-medium text-white bg-dark-300 hover:bg-dark-200 px-3 py-2 rounded-lg transition-colors disabled:opacity-60"
            >
              <BookmarkPlus size={13} />
              {saving ? "Saving…" : "Save to Itineraries"}
            </button>
            <div className="flex-1" />
            <button
              type="button"
              onClick={onDiscard}
              className="flex items-center gap-1.5 text-xs font-medium text-red-500 bg-red-50 hover:bg-red-100 px-3 py-2 rounded-lg transition-colors"
            >
              <Trash2 size={13} /> Discard
            </button>
          </>
        )}
      </div>
    </div>
  );
}
