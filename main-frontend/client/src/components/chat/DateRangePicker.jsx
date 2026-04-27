import React, { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const DAY_LABELS = ["S", "M", "T", "W", "T", "F", "S"];

const startOfDay = (d) => {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
};
const sameDay = (a, b) => !!a && !!b && a.toDateString() === b.toDateString();
const isBetween = (d, a, b) => a && b && d > a && d < b;

// Backend parses full month names ("March", not "Mar") for `trip_start_date`.
// Output "12 March 2026" so conversation_manager._extract_dates and
// formal_request_parser._extract_dates both pick it up cleanly.
function formatDate(d) {
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "long", year: "numeric" });
}

function getMonthGrid(year, month) {
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const days = [];
  for (let i = 0; i < first.getDay(); i++) days.push(null);
  for (let d = 1; d <= last.getDate(); d++) days.push(new Date(year, month, d));
  return days;
}

/**
 * Inline calendar for the chat. mode = "range" (start + end) or "single".
 * onApply receives the formatted string ("12 Mar 2026" or "12 Mar 2026 to 19 Mar 2026").
 */
export default function DateRangePicker({ mode = "range", onApply }) {
  const today = useMemo(() => startOfDay(new Date()), []);
  const [view, setView] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [start, setStart] = useState(null);
  const [end, setEnd] = useState(null);
  const [hover, setHover] = useState(null);

  const days = useMemo(() => getMonthGrid(view.year, view.month), [view]);

  const goPrev = () =>
    setView((v) => (v.month === 0 ? { year: v.year - 1, month: 11 } : { ...v, month: v.month - 1 }));
  const goNext = () =>
    setView((v) => (v.month === 11 ? { year: v.year + 1, month: 0 } : { ...v, month: v.month + 1 }));

  const handleClick = (d) => {
    if (!d) return;
    if (mode === "single") {
      setStart(d);
      return;
    }
    if (!start || (start && end)) {
      setStart(d);
      setEnd(null);
      return;
    }
    if (d < start) {
      setStart(d);
      return;
    }
    setEnd(d);
  };

  const valid = mode === "single" ? !!start : !!start && !!end;
  const submit = () => {
    if (!valid) return;
    const text =
      mode === "single"
        ? formatDate(start)
        : `${formatDate(start)} to ${formatDate(end)}`;
    onApply(text);
  };

  const previewEnd = !end && start && hover && hover > start ? hover : end;

  return (
    <div className="mt-3 inline-flex flex-col gap-3 bg-white dark:bg-[#1F1F1F] rounded-xl border border-[#FFDE39]/40 dark:border-[#FFDE39]/20 shadow-[0_4px_14px_rgba(255,222,57,0.10)] dark:shadow-[0_6px_18px_rgba(0,0,0,0.45)] p-3 w-[280px]">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={goPrev}
          className="w-7 h-7 rounded-md flex items-center justify-center text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
          aria-label="Previous month"
        >
          <ChevronLeft size={14} />
        </button>
        <div className="text-[13px] font-semibold text-[#1f1f1f] dark:text-white">
          {MONTH_NAMES[view.month]} {view.year}
        </div>
        <button
          type="button"
          onClick={goNext}
          className="w-7 h-7 rounded-md flex items-center justify-center text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
          aria-label="Next month"
        >
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {DAY_LABELS.map((d, i) => (
          <div key={i} className="text-[10px] font-semibold text-center text-gray-400 dark:text-gray-500 py-0.5">
            {d}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {days.map((d, i) => {
          if (!d) return <div key={i} />;
          const isStart = sameDay(d, start);
          const isEnd = sameDay(d, previewEnd);
          const inRange = isBetween(d, start, previewEnd);
          const isToday = sameDay(d, today);
          const isPast = d < today;

          const base = "relative w-8 h-7 text-[12px] flex items-center justify-center select-none transition-colors duration-150";
          let style = base + " ";
          if (isPast && !isStart && !isEnd) {
            style += "text-gray-300 dark:text-gray-600 cursor-not-allowed";
          } else if (isStart || isEnd) {
            style += "bg-[#FFDE39] text-[#1f1f1f] font-semibold rounded-md cursor-pointer shadow-[0_2px_6px_rgba(255,222,57,0.35)]";
          } else if (inRange) {
            style += "bg-[#FFFAC5] dark:bg-[#FFDE39]/15 text-[#1f1f1f] dark:text-gray-100 cursor-pointer";
          } else {
            style += "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/5 rounded-md cursor-pointer";
          }
          if (isToday && !isStart && !isEnd) {
            style += " ring-1 ring-[#FFDE39]/60 rounded-md";
          }

          return (
            <div
              key={i}
              onClick={() => !isPast && handleClick(d)}
              onMouseEnter={() => setHover(d)}
              onMouseLeave={() => setHover(null)}
              className={style}
            >
              {d.getDate()}
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-white/10 gap-2">
        <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
          {start && end && <span>{formatDate(start)} → {formatDate(end)}</span>}
          {start && !end && <span>{formatDate(start)}{mode === "range" ? " → …" : ""}</span>}
          {!start && <span>{mode === "range" ? "Pick start & end" : "Pick a date"}</span>}
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={!valid}
          className="text-[11px] font-semibold bg-[#1f1f1f] text-[#FFDE39] px-3 py-1 rounded-md hover:bg-[#262524] disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          {mode === "single" ? "Use date" : "Apply"}
        </button>
      </div>
    </div>
  );
}
