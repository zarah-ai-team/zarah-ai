import React from "react";
import { Plane } from "lucide-react";
import { useNavigate } from "react-router-dom";

const RecentActivities = ({ activities = [] }) => {
  const navigate = useNavigate();

  return (
    <section className="bg-white rounded-xl border border-gray-100 p-5 h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#1f1f1f]">Recent Activities</h3>
        <button
          onClick={() => navigate("/chat")}
          className="text-xs font-medium text-blue-500 hover:text-blue-700 hover:underline transition cursor-pointer"
        >
          View All
        </button>
      </div>

      {/* List */}
      <ul className="divide-y divide-gray-100">
        {activities.map((activity) => (
          <li
            key={activity.id}
            onClick={() =>
              activity.session_id && navigate(`/chat?session=${activity.session_id}`)
            }
            className={`flex items-center gap-3 py-3 first:pt-0 last:pb-0 -mx-2 px-2 rounded-lg transition-colors duration-200 ${
              activity.session_id ? "cursor-pointer hover:bg-gray-50" : "cursor-default"
            }`}
          >
            <div className="w-8 h-8 rounded-md bg-gray-50 flex items-center justify-center shrink-0">
              <Plane size={15} className="text-[#1f1f1f]" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-semibold text-[#1f1f1f] leading-tight">
                {activity.title}
              </p>
              <p className="text-xs text-gray-500 mt-0.5 truncate">
                {activity.description}
              </p>
            </div>
            <span className="text-xs text-gray-400 whitespace-nowrap ml-2">
              {activity.time}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default RecentActivities;
