import { useEffect, useState } from "react";
import "./css/app.css";
import Calendar from "./Calendar";
import Taskbar from "./Taskbar";

interface UserData {
  user_name: string;
  user_email: string;
  user_id: string;
}

export default function Dashboard() {
  const [user, setUser] = useState<UserData | null>(null);

  useEffect(() => {
    // Get user data from localStorage
    const userData = localStorage.getItem("user");
    if (userData) {
      setUser(JSON.parse(userData));
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("user");
    window.location.href = "/";
  };

  const handleOpenCampusMap = () => {
    window.open("https://campusmap.ufl.edu/", "_blank");
  };

  if (!user) {
    return (
      <div style={{ padding: "2rem", textAlign: "center" }}>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header with user info and logout */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-[#003087]">
                Campus Compass
              </h1>
              <p className="text-sm text-gray-600 mt-1">
                Welcome, {user.user_name} • {user.user_email}
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleOpenCampusMap}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                title="Open UF Campus Map"
              >
                🗺️ Campus Map
              </button>
              <button
                onClick={handleLogout}
                className="px-4 py-2 bg-[#FA4616] text-white rounded-md hover:bg-[#d93a0f] transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content - Calendar and Taskbar */}
      <main className="flex-1 overflow-hidden flex">
        <div className="flex-1 overflow-hidden">
          <Calendar userId={user.user_id} />
        </div>
        <div className="w-80 overflow-hidden border-l border-gray-200">
          <Taskbar userId={user.user_id} />
        </div>
      </main>
    </div>
  );
}
