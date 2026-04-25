import React from "react";
import { useLocation } from "react-router-dom";
import { Construction } from "lucide-react";

/**
 * Generic placeholder for pages not yet built.
 * Will be replaced with real page components as each feature is developed.
 */
const Placeholder = () => {
  const { pathname } = useLocation();

  // Derive a human‑friendly title from the path
  const title = pathname
    .replace("/", "")
    .split("/")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ") || "Page";

  return (
    <div className="flex flex-col items-center justify-center h-full text-center animate-fadeIn">
      <div className="w-16 h-16 rounded-2xl bg-brand-100 flex items-center justify-center mb-4">
        <Construction size={32} className="text-brand-500" />
      </div>
      <h2 className="text-xl font-semibold text-gray-800">{title}</h2>
      <p className="text-sm text-gray-400 mt-1 max-w-xs">
        This section is under development. Check back soon!
      </p>
    </div>
  );
};

export default Placeholder;
