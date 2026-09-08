import { useEffect, useState } from "react";
import "./App.css";

const API_URL = "http://192.168.100.4:8000";

function App() {
  const [computers, setComputers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedComputer, setSelectedComputer] = useState(null);
  const [activity, setActivity] = useState(null);

  const fetchComputers = async () => {
    try {
      const response = await fetch(`${API_URL}/computers`);
      const data = await response.json();

      setComputers(Object.values(data));;
      setLoading(false);
    } catch (error) {
      console.error("Failed to fetch computers:", error);
      setLoading(false);
    }
  };
  
  const viewComputer = async (pcId) => {
  try {
    const response = await fetch(
      `${API_URL}/computers/${pcId}/activity`
    );

    const data = await response.json();

    setSelectedComputer(pcId);
    setActivity(data.activity);
  } catch (error) {
    console.error("Failed to fetch computer activity:", error);
  }
};

useEffect(() => {
  if (!selectedComputer) return;

  const interval = setInterval(async () => {
    try {
      const response = await fetch(
        `${API_URL}/computers/${selectedComputer}/activity`
      );

      const data = await response.json();

      setActivity(data.activity);
    } catch (error) {
      console.error("Failed to refresh activity:", error);
    }
  }, 3000);

  return () => clearInterval(interval);
}, [selectedComputer]);

  useEffect(() => {
    fetchComputers();
    

    const interval = setInterval(fetchComputers, 5000);

    return () => clearInterval(interval);
  }, []);

  const onlineCount = computers.filter(
    (computer) => computer.status === "Online"
  ).length;

  const offlineCount = computers.length - onlineCount;

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>LabSphere</h1>
          <p>Smart Laboratory Management System</p>
        </div>

        <div className="server-status">
          <span className="status-dot"></span>
          Server Online
        </div>
      </header>

      <main className="dashboard">
        <section className="stats">
          <div className="stat-card">
            <span>Total Computers</span>
            <strong>{computers.length}</strong>
          </div>

          <div className="stat-card">
            <span>Online</span>
            <strong>{onlineCount}</strong>
          </div>

          <div className="stat-card">
            <span>Offline</span>
            <strong>{offlineCount}</strong>
          </div>
        </section>

        <section className="computer-section">
          <div className="section-header">
            <div>
              <h2>Lab Computers</h2>
              <p>Live computer activity</p>
            </div>

            <button onClick={fetchComputers}>Refresh</button>
          </div>

          {loading ? (
            <div className="empty-state">
              Loading computers...
            </div>
          ) : computers.length === 0 ? (
            <div className="empty-state">
              No computers connected.
            </div>
          ) : (
            <div className="computer-grid">
              {computers.map((computer) => (
                <div className="computer-card" key={computer.pc_id}>
                  <div className="card-header">
                    <div>
                      <h3>{computer.pc_id}</h3>
                      <p>{computer.hostname}</p>
                    </div>

                    <span
                      className={
                        computer.status === "Online"
                          ? "online-badge"
                          : "offline-badge"
                      }
                    >
                      {computer.status}
                    </span>
                  </div>

                  <div className="computer-info">
                    <div>
                      <span>Student</span>
                      <strong>
                        {computer.student_name || "Not assigned"}
                      </strong>
                    </div>

                    <div>
                      <span>IP Address</span>
                      <strong>{computer.ip_address}</strong>
                    </div>

                    <div>
                      <span>Last Seen</span>
                      <strong>
                        {computer.last_seen
                          ? new Date(computer.last_seen).toLocaleTimeString()
                          : "Unknown"}
                      </strong>
                    </div>
                  </div>

                  <button className="control-button"
                  onClick={() => viewComputer(computer.pc_id)}>
                    View Activity
                  </button>
                  <button
  className="control-button lock-button"
  onClick={async () => {
    try {
      const response = await fetch(
        `${API_URL}/computers/${computer.pc_id}/command`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            command: "LOCK",
            data: {}
          })
        }
      );

      const data = await response.json();

      console.log("Lock response:", data);

      if (data.status === "command_sent") {
        alert(`Lock command sent to ${computer.pc_id}`);
      } else {
        alert(`Lock failed: ${data.status}`);
      }
    } catch (error) {
      console.error("Lock failed:", error);
      alert("Could not send lock command.");
    }
  }}
>
  🔒 Lock
</button>
                  <button className="control-button"
                  onClick={async () => {
                    try {
                      const response = await fetch(
                        `${API_URL}/computers/${computer.pc_id}/ping`,
                        { method: "POST" }
                      );
                      const data = await response.json();
                      alert(
                        data.status === "ping_sent"
                        ? `${computer.pc_id} is responding.`
                        : `${computer.pc_id} is not responding.`
                      );
                    } catch (error) {
                      console.error("Ping Failed:", error);
                    }
                  }}
                  > 📡Ping
                  </button>
                  <button
    className="control-button"
    onClick={async () => {
      const message = window.prompt(
        `Message for ${computer.pc_id}:`
      );

      if (!message) return;

      try {
        await fetch(
          `${API_URL}/computers/${computer.pc_id}/message`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json"
            },
            body: JSON.stringify({
              message: message
            })
          }
        );

        alert("Message sent");
      } catch (error) {
        console.error("Message failed:", error);
      }
    }}
  >
    💬 Message
  </button>
</div>
                
              ))}
            </div>
          )}
        </section>
        {selectedComputer && (
  <section className="activity-panel">
    <div className="section-header">
      <div>
        <h2>{selectedComputer} Activity</h2>
        <p>Live activity information</p>
      </div>

      <button onClick={() => setSelectedComputer(null)}>
        Close
      </button>
    </div>

    {activity ? (
      <div className="activity-grid">
        <div className="activity-card">
          <span>Active Application</span>
          <strong>{activity.active_window || "Unknown"}</strong>
        </div>

        <div className="activity-card">
          <span>CPU Usage</span>
          <strong>{activity.cpu_percent}%</strong>
        </div>

        <div className="activity-card">
          <span>Memory Usage</span>
          <strong>{activity.memory_percent}%</strong>
        </div>

        <div className="activity-card">
          <span>Idle Time</span>
          <strong>{activity.idle_seconds} seconds</strong>
        </div>
      </div>
    ) : (
      <div className="empty-state">
        No activity data available.
      </div>
    )}
  </section>
)}
      </main>
    </div>
  );
}

export default App;