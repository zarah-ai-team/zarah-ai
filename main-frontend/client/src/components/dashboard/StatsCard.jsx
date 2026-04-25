import React from "react";
import {
  Plane,
  FileEdit,
  FileText,
  Clock,
  Briefcase,
  FolderCheck,
  Users,
} from "lucide-react";

const iconMap = {
  plane: Plane,
  "file-edit": FileEdit,
  "file-text": FileText,
  clock: Clock,
  briefcase: Briefcase,
  "folder-check": FolderCheck,
  users: Users,
};

const StatsCard = ({ title, value, icon, subtitle, actionLabel, onAction }) => {
  const Icon = iconMap[icon] || Plane;

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-2.5 flex flex-col transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:shadow-[0_8px_20px_rgba(0,0,0,0.05)] hover:-translate-y-0.5">
      {/* Inset yellow block — number, label, icon */}
      <div className="bg-[#FFF6B5] rounded-lg px-4 py-3.5 flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-[24px] font-bold text-[#1f1f1f] leading-none">{value}</p>
          <p className="text-[12px] text-[#1f1f1f] mt-1.5 font-medium">{title}</p>
        </div>
        <Icon
          size={28}
          strokeWidth={1}
          className="text-[#1f1f1f] shrink-0 fill-[#FFDE39]"
        />
      </div>

      {/* Subtitle + pill action */}
      <div className="flex items-center justify-between px-2 pt-3 pb-1">
        <span className="text-[11px] text-gray-500">{subtitle}</span>
        <button
          onClick={onAction}
          className="text-[11px] font-medium text-[#3B82F6] bg-[#EFF6FF] hover:bg-[#DBEAFE] px-2.5 py-1 rounded-full transition cursor-pointer"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
};

export default StatsCard;
