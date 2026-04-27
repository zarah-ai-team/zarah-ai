import React from "react";
import { useNavigate } from "react-router-dom";
import {
  MessageSquarePlus,
  Upload,
  UserPlus,
  ClipboardList,
} from "lucide-react";

const iconMap = {
  "message-square-plus": MessageSquarePlus,
  upload: Upload,
  "user-plus": UserPlus,
  "clipboard-list": ClipboardList,
};

const QuickActions = ({ actions = [] }) => {
  const navigate = useNavigate();

  return (
    <section className="mt-5 bg-white dark:bg-[#2A2929] rounded-xl border border-gray-100 dark:border-white/10 p-5">
      <h2 className="text-sm font-semibold text-[#1f1f1f] dark:text-white mb-4">Quick Actions</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {actions.map((action) => {
          const Icon = iconMap[action.icon] || ClipboardList;

          return (
            <button
              key={action.id}
              onClick={() => navigate(action.route)}
              className="relative flex items-center gap-3 bg-white dark:bg-[#1F1F1F] rounded-xl border border-gray-100 dark:border-white/10 px-4 py-3 cursor-pointer group text-left
                         transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]
                         hover:-translate-y-0.5 hover:border-[#FFDE39]/60 dark:hover:border-[#FFDE39]/50
                         hover:shadow-[0_0_0_1px_rgba(255,222,57,0.4),0_8px_24px_-6px_rgba(255,222,57,0.55)]
                         dark:hover:shadow-[0_0_0_1px_rgba(255,222,57,0.35),0_8px_24px_-6px_rgba(255,222,57,0.35)]
                         hover:bg-gradient-to-br hover:from-white hover:to-[#FFFCE6]
                         dark:hover:from-[#1F1F1F] dark:hover:to-[#2A2620]"
            >
              <div className="w-9 h-9 rounded-lg bg-[#1f1f1f] dark:bg-white/10 flex items-center justify-center shrink-0
                              transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]
                              group-hover:bg-[#FFDE39] group-hover:shadow-[0_0_12px_rgba(255,222,57,0.6)]
                              dark:group-hover:bg-[#FFDE39]">
                <Icon
                  size={17}
                  className="text-white transition-colors duration-500 group-hover:text-[#1f1f1f] dark:group-hover:text-[#1f1f1f]"
                />
              </div>
              <span className="text-sm font-medium text-[#1f1f1f] dark:text-gray-100 transition-colors duration-300 group-hover:text-[#1f1f1f] dark:group-hover:text-white">
                {action.label}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
};

export default QuickActions;
