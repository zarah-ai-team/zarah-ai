import React from "react";

const NotificationsPanel = ({ notifications = [], onMarkAllRead }) => {
  return (
    <section className="bg-white rounded-xl border border-gray-100 p-5 h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#1f1f1f]">Notification</h3>
        <button
          onClick={onMarkAllRead}
          className="text-xs font-medium text-blue-500 hover:text-blue-700 hover:underline transition cursor-pointer"
        >
          Mark all read
        </button>
      </div>

      {/* List */}
      <ul className="space-y-2">
        {notifications.map((n) => (
          <li
            key={n.id}
            className="bg-[#f4f4f4] rounded-lg px-3.5 py-2.5 transition-all duration-200 hover:bg-[#eeeeee] cursor-pointer"
          >
            <p className="text-[13px] font-semibold text-[#1f1f1f] leading-tight">
              {n.title}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">{n.description}</p>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default NotificationsPanel;
