import React from "react";
import { Monitor } from "lucide-react";

const MobileNotAvailable = () => {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-sidebar text-white px-8 font-poppins">
      <div className="w-20 h-20 rounded-full bg-brand-400/20 flex items-center justify-center mb-6 animate-pulse">
        <Monitor size={40} className="text-brand-400" />
      </div>

      <h1 className="text-2xl font-semibold mb-2 text-center">
        Not Available on Mobile
      </h1>

      <p className="text-gray-400 text-sm text-center max-w-xs leading-relaxed">
        Zarah is optimized for desktop use. Please open this application on a
        laptop or desktop for the best experience.
      </p>

      <div className="mt-8 w-16 h-1 rounded-full bg-brand-400" />
    </div>
  );
};

export default MobileNotAvailable;
