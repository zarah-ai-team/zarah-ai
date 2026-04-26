import React, { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import MobileNotAvailable from "../common/MobileNotAvailable";

const pageTitles = {
  "/": "Dashboard",
  "/chat": "Chat",
  "/chat/new": "Chat",
  "/itineraries": "Itinerary Management",
  "/documents": "Document Management",
  "/clients": "Client Management",
  "/settings": "Settings",
  "/help": "Help and Support",
};

const Layout = () => {
  const { pathname } = useLocation();
  const pageTitle = pageTitles[pathname] || "Dashboard";
  const isChatPage = pathname === "/chat" || pathname.startsWith("/chat/");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <>
      {/* ---- Mobile guard ---- */}
      <div className="md:hidden">
        <MobileNotAvailable />
      </div>

      {/* ---- Desktop layout ---- */}
      <div className="hidden md:flex h-screen overflow-hidden bg-white dark:bg-[#2c2e34] p-3 gap-3 font-poppins">
        <Sidebar
          showProfile={isChatPage}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={() => setSidebarCollapsed((c) => !c)}
        />

        <div className="flex-1 flex flex-col overflow-hidden gap-3 min-w-0">
          {!isChatPage && <TopBar pageTitle={pageTitle} />}

          <main className="flex-1 overflow-y-auto pr-1 -mr-1">
            <Outlet context={{ sidebarCollapsed }} />
          </main>
        </div>
      </div>
    </>
  );
};

export default Layout;
