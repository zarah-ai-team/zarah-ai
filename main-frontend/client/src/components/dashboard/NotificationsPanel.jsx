import React from "react";

const NotificationsPanel = ({ notifications = [], onMarkAllRead }) => {
  return (
    <section className="bg-white dark:bg-[#2A2929] rounded-xl border border-gray-100 dark:border-white/10 p-5 h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#1f1f1f] dark:text-white">Notification</h3>
        <button
          onClick={onMarkAllRead}
          className="text-xs font-medium text-blue-500 dark:text-gray-400 hover:text-blue-700 dark:hover:text-gray-200 hover:underline transition cursor-pointer"
        >
          Mark all read
        </button>
      </div>

      {/* List */}
      <ul className="space-y-2">
        {notifications.map((n) => (
          <li
            key={n.id}
            className="bg-[#f4f4f4] dark:bg-white/[0.03] dark:border dark:border-transparent rounded-lg px-3.5 py-2.5 transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#eeeeee] dark:hover:bg-white/[0.05] dark:hover:border-white/10 cursor-pointer"
          >
            <p className="text-[13px] font-semibold text-[#1f1f1f] dark:text-gray-200 leading-tight">
              {n.title}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{n.description}</p>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default NotificationsPanel;
