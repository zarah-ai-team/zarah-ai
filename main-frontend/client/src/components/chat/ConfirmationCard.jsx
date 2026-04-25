import React from "react";
import { MapPin, Calendar, Users, Hotel, Car, CheckCircle2 } from "lucide-react";

const Row = ({ label, value }) => {
  if (!value) return null;
  return (
    <div className="flex gap-2 text-xs">
      <span className="text-gray-400 w-32 flex-shrink-0">{label}</span>
      <span className="text-gray-700 font-medium flex-1">{value}</span>
    </div>
  );
};

const ConfirmationCard = ({ fields, onConfirm }) => {
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
    <div className="bg-white border border-brand-200 rounded-2xl overflow-hidden shadow-sm max-w-[480px] w-full">
      {/* Header */}
      <div className="bg-gradient-to-r from-brand-50 to-yellow-50 px-4 py-3 border-b border-brand-100 flex items-center gap-2">
        <MapPin size={14} className="text-brand-500 flex-shrink-0" />
        <p className="text-xs font-semibold text-gray-700">Trip Details — Please Review</p>
      </div>

      {/* Fields */}
      <div className="px-4 py-3 space-y-2.5">
        {fields.destination && (
          <Row label="Destination" value={fields.destination} />
        )}
        {fields.route && fields.route !== fields.destination && (
          <Row label="Route" value={fields.route} />
        )}
        {nightsPerCity && (
          <Row label="Nights per city" value={nightsPerCity} />
        )}
        {duration && (
          <div className="flex gap-2 text-xs items-center">
            <Calendar size={11} className="text-gray-400 flex-shrink-0 mt-0.5" />
            <span className="text-gray-400 w-[116px] flex-shrink-0">Duration</span>
            <span className="text-gray-700 font-medium">{duration}</span>
          </div>
        )}
        {paxStr && (
          <div className="flex gap-2 text-xs items-center">
            <Users size={11} className="text-gray-400 flex-shrink-0 mt-0.5" />
            <span className="text-gray-400 w-[116px] flex-shrink-0">Pax</span>
            <span className="text-gray-700 font-medium">{paxStr}</span>
          </div>
        )}
        {rooms && <Row label="Rooms" value={rooms} />}
        {hotel && (
          <div className="flex gap-2 text-xs items-center">
            <Hotel size={11} className="text-gray-400 flex-shrink-0 mt-0.5" />
            <span className="text-gray-400 w-[116px] flex-shrink-0">Hotel</span>
            <span className="text-gray-700 font-medium">{hotel}</span>
          </div>
        )}
        {fields.transport && (
          <div className="flex gap-2 text-xs items-center">
            <Car size={11} className="text-gray-400 flex-shrink-0 mt-0.5" />
            <span className="text-gray-400 w-[116px] flex-shrink-0">Transport</span>
            <span className="text-gray-700 font-medium">{fields.transport}</span>
          </div>
        )}
        {fields.driver && <Row label="Driver" value={fields.driver} />}
        {fields.guide && <Row label="Guide" value="English-speaking local guide" />}
        {fields.senior_friendly && (
          <Row label="Special needs" value="Senior-friendly, comfortable pace" />
        )}
        {fields.preferred_activities && fields.preferred_activities.length > 0 && (
          <Row label="Activities" value={fields.preferred_activities.join(", ")} />
        )}
        {fields.event_type && fields.event_type !== "leisure" && (
          <Row label="Trip type" value={fields.event_type} />
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-100 bg-gray-50 flex items-center justify-between gap-3">
        <p className="text-[11px] text-gray-400 leading-snug flex-1">
          Reply <span className="font-semibold text-gray-600">"confirm"</span> to generate, or tell me what to change.
        </p>
        <button
          onClick={onConfirm}
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
