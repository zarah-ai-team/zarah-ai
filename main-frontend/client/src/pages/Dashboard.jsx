import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import StatsCard from "../components/dashboard/StatsCard";
import QuickActions from "../components/dashboard/QuickActions";
import RecentActivities from "../components/dashboard/RecentActivities";
import NotificationsPanel from "../components/dashboard/NotificationsPanel";

import {
  fetchDashboardStats,
  fetchQuickActions,
  fetchRecentActivities,
  fetchNotifications,
  markAllNotificationsRead,
} from "../services/dashboardService";

const Dashboard = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState([]);
  const [actions, setActions] = useState([]);
  const [activities, setActivities] = useState([]);
  const [notifs, setNotifs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [s, a, act, n] = await Promise.all([
          fetchDashboardStats(),
          fetchQuickActions(),
          fetchRecentActivities(),
          fetchNotifications(),
        ]);
        setStats(s);
        setActions(a);
        setActivities(act);
        setNotifs(n);
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleMarkAllRead = async () => {
    await markAllNotificationsRead();
    setNotifs([]);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-8 h-8 border-4 border-brand-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="animate-fadeIn space-y-5">
      {/* Stats grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger">
        {stats.map((stat) => (
          <div key={stat.id} className="animate-fadeIn">
            <StatsCard
              title={stat.title}
              value={stat.value}
              icon={stat.icon}
              subtitle={stat.subtitle}
              actionLabel={stat.actionLabel}
              onAction={() => stat.actionRoute && navigate(stat.actionRoute)}
            />
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <QuickActions actions={actions} />

      {/* Bottom row — activities + notifications */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 items-stretch">
        <div className="lg:col-span-3">
          <RecentActivities activities={activities} />
        </div>
        <div className="lg:col-span-2">
          <NotificationsPanel
            notifications={notifs}
            onMarkAllRead={handleMarkAllRead}
          />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
