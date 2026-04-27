import React from "react";
import {
  PlaneIcon,
  DocumentIcon,
  ClockIcon,
  BriefcaseIcon,
  UsersIcon,
  FolderCheckIcon,
} from "./StatsIcons";

const iconMap = {
  plane: PlaneIcon,
  "file-edit": DocumentIcon,
  "file-text": DocumentIcon,
  clock: ClockIcon,
  briefcase: BriefcaseIcon,
  "folder-check": FolderCheckIcon,
  users: UsersIcon,
};

const StatsCard = ({ title, value, icon, subtitle, actionLabel, onAction }) => {
  const Icon = iconMap[icon] || PlaneIcon;

  return (
    <div className="bg-white dark:bg-[#2A2929] rounded-xl border border-gray-100 dark:border-white/10 p-2 flex flex-col transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:shadow-[0_8px_20px_rgba(0,0,0,0.05)] dark:hover:shadow-[0_8px_24px_rgba(0,0,0,0.45)] dark:hover:border-[#FFDE39]/25 hover:-translate-y-0.5">
      {/* Inset yellow block — number, label, icon */}
      <div className="bg-[#FFF6B5] dark:bg-gradient-to-br dark:from-[#1F1F1F] dark:to-[#262524] dark:border dark:border-[#FFDE39]/15 rounded-lg px-4 py-2.5 flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-[22px] font-bold text-[#1f1f1f] dark:text-white leading-none">{value}</p>
          <p className="text-[12px] text-[#1f1f1f] dark:text-gray-300 mt-1 font-medium">{title}</p>
        </div>
        <Icon
          size={30}
          className="shrink-0 text-[#FFDE39] dark:[filter:drop-shadow(0_0_8px_rgba(255,222,57,0.35))]"
        />
      </div>

      {/* Subtitle + pill action */}
      <div className="flex items-center justify-between px-2 pt-2 pb-0.5">
        <span className="text-[11px] text-gray-500 dark:text-gray-400">{subtitle}</span>
        <button
          onClick={onAction}
          className="text-[11px] font-medium text-[#3B82F6] dark:text-[#FFDE39] bg-[#EFF6FF] dark:bg-[#FFDE39]/10 hover:bg-[#DBEAFE] dark:hover:bg-[#FFDE39]/20 px-2.5 py-1 rounded-full transition cursor-pointer"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
};

export default StatsCard;
