import React, { useState } from "react";
import { MapPin, Calendar, Users, Hotel, Car, CheckCircle2, Briefcase, Coins } from "lucide-react";

const CURRENCY_OPTIONS = [
  { code: "USD", symbol: "$",  label: "US Dollar" },
  { code: "EUR", symbol: "€",  label: "Euro" },
  { code: "INR", symbol: "₹",  label: "Indian Rupee" },
  { code: "GBP", symbol: "£",  label: "British Pound" },
  { code: "AED", symbol: "AED",label: "UAE Dirham" },
  { code: "SGD", symbol: "S$", label: "Singapore Dollar" },
];

const Row = ({ icon: Icon, label, value }) => {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="w-4 flex-shrink-0 flex items-center justify-center pt-[2px]">
        {Icon ? <Icon size={11} className="text-gray-400 dark:text-gray-400" /> : null}
      </span>
      <span className="text-gray-400 dark:text-gray-400 w-28 flex-shrink-0 text-left">{label}</span>
      <span className="text-gray-700 dark:text-gray-100 font-medium flex-1 text-left break-words">{value}</span>
    </div>
  );
};

const ConfirmationCard = ({ fields, onConfirm }) => {
  const [currency, setCurrency] = useState(fields?.currency || "USD");
  if (!fields) return null;

  const nightsPerCity = fields.nights_per_city && Object.keys(fields.nights_per_city).length > 0
    ? Object.entries(fields.nights_per_city).map(([c, n]) => `${c}: ${n}N`).join(" → ")
    : null;

  const duration = fields.total_nights
    ? `${fields.total_nights} nights / ${fields.total_days || fields.total_nights + 1} days${fields.start_date ? ` from ${fields.start_date}` : ""}`
    : null;

  const paxStr = fields.pax
    ? `${fields.pax} adults${fields.seniors ? ` (incl. ${fields.seniors} senior citizens)` : ""}`
    : null;

  const rooms = fields.room_config && Object.keys(fields.room_config).length > 0
    ? Object.entries(fields.room_config).map(([k, v]) => `${v} ${k}`).join(", ")
    : null;

  const hotel = fields.hotel_category
    ? `${fields.hotel_category}${fields.hotel_location ? ` — ${fields.hotel_location}` : ""}`
    : null;

  return (
    <div className="bg-white dark:bg-[#2A2929] border border-brand-200 dark:border-white/10 rounded-2xl overflow-hidden shadow-sm dark:shadow-[0_2px_8px_rgba(0,0,0,0.25)] max-w-[480px] w-full">
      {/* Header */}
      <div className="bg-gradient-to-r from-brand-50 to-yellow-50 dark:from-[#1F1F1F] dark:to-[#2A2929] px-4 py-3 border-b border-brand-100 dark:border-[#FFDE39]/20 flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-full bg-[#FFDE39] flex items-center justify-center shadow-[0_2px_6px_rgba(255,222,57,0.45)] flex-shrink-0">
          <MapPin size={15} className="text-[#1f1f1f]" strokeWidth={2.5} />
        </span>
        <p className="text-[13px] font-semibold text-gray-800 dark:text-white">Trip Details — Please Review</p>
      </div>

      {/* Fields */}
      <div className="px-4 py-3 space-y-2.5">
        <Row icon={MapPin}   label="Destination"     value={fields.destination} />
        {fields.route && fields.route !== fields.destination && (
          <Row label="Route" value={fields.route} />
        )}
        <Row                  label="Nights per city" value={nightsPerCity} />
        <Row icon={Calendar}  label="Duration"        value={duration} />
        <Row icon={Users}     label="Pax"             value={paxStr} />
        <Row                  label="Rooms"           value={rooms} />
        <Row icon={Hotel}     label="Hotel"           value={hotel} />
        <Row icon={Car}       label="Transport"       value={fields.transport} />
        <Row                  label="Driver"          value={fields.driver} />
        {fields.guide && <Row label="Guide" value="English-speaking local guide" />}
        {fields.senior_friendly && (
          <Row label="Special needs" value="Senior-friendly, comfortable pace" />
        )}
        {fields.preferred_activities && fields.preferred_activities.length > 0 && (
          <Row label="Activities" value={fields.preferred_activities.join(", ")} />
        )}
        {fields.event_type && fields.event_type !== "leisure" && (
          <Row icon={Briefcase} label="Trip type" value={fields.event_type} />
        )}
      </div>

      {/* Currency picker — required step before generation */}
      <div className="px-4 py-3 border-t border-gray-100 dark:border-white/10 bg-[#fffdf5] dark:bg-[#1F1F1F]/60">
        <div className="flex items-center gap-2 mb-2">
          <Coins size={12} className="text-[#E6C800] dark:text-[#FFDE39]" />
          <p className="text-[11px] font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wider">
            Quote currency
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {CURRENCY_OPTIONS.map((c) => {
            const active = currency === c.code;
            return (
              <button
                key={c.code}
                type="button"
                onClick={() => setCurrency(c.code)}
                title={c.label}
                className={`flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-full border transition-all duration-200 cursor-pointer ${
                  active
                    ? "bg-[#FFDE39] text-[#1f1f1f] border-[#FFDE39] shadow-[0_1px_4px_rgba(255,222,57,0.45)]"
                    : "bg-white dark:bg-white/5 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-white/15 hover:border-[#FFDE39]/60 hover:text-[#8A6800] dark:hover:text-[#FFDE39]"
                }`}
              >
                <span className="font-semibold">{c.symbol}</span>
                <span>{c.code}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-100 dark:border-white/10 bg-gray-50 dark:bg-[#1F1F1F] flex items-center justify-between gap-3">
        <p className="text-[11px] text-gray-400 dark:text-gray-400 leading-snug flex-1">
          Reply <span className="font-semibold text-gray-600 dark:text-gray-200">"confirm"</span> to generate in <span className="font-semibold text-gray-600 dark:text-gray-200">{currency}</span>, or tell me what to change.
        </p>
        <button
          onClick={() => onConfirm(currency)}
          className="flex items-center gap-1.5 bg-brand-400 hover:bg-brand-500 text-gray-800 text-xs font-semibold px-3.5 py-1.5 rounded-full transition-all duration-200 flex-shrink-0"
        >
          <CheckCircle2 size={13} />
          Confirm
        </button>
      </div>
    </div>
  );
};

export default ConfirmationCard;
