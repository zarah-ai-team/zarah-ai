import React from "react";
import { Plane } from "lucide-react";
import { useNavigate } from "react-router-dom";

const RecentActivities = ({ activities = [] }) => {
  const navigate = useNavigate();

  return (
    <section className="bg-white dark:bg-[#2A2929] rounded-xl border border-gray-100 dark:border-white/10 p-5 h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#1f1f1f] dark:text-white">Recent Activities</h3>
        <button
          onClick={() => navigate("/chat")}
          className="text-xs font-medium text-blue-500 dark:text-[#FFDE39] hover:text-blue-700 dark:hover:text-[#FFE970] hover:underline transition cursor-pointer"
        >
          View All
        </button>
      </div>

      {/* List */}
      <ul className="divide-y divide-gray-100 dark:divide-white/5">
        {activities.map((activity) => (
          <li
            key={activity.id}
            onClick={() =>
              activity.session_id && navigate(`/chat?session=${activity.session_id}`)
            }
            className={`group flex items-center gap-3 py-3 first:pt-0 last:pb-0 -mx-2 px-2 rounded-lg transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] ${
              activity.session_id
                ? "cursor-pointer hover:bg-gray-50 dark:hover:bg-white/[0.04] dark:hover:translate-x-0.5"
                : "cursor-default"
            }`}
          >
            <div className="w-8 h-8 rounded-md bg-gray-50 dark:bg-white/5 dark:group-hover:bg-[#FFDE39]/15 flex items-center justify-center shrink-0 transition-colors duration-300">
              <Plane size={15} className="text-[#1f1f1f] dark:text-gray-300 dark:group-hover:text-[#FFDE39] transition-colors duration-300" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-semibold text-[#1f1f1f] dark:text-gray-100 leading-tight">
                {activity.title}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
                {activity.description}
              </p>
            </div>
            <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap ml-2">
              {activity.time}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default RecentActivities;
