import { useEffect, useState, useRef } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

function App() {
  const [computers, setComputers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedComputer, setSelectedComputer] = useState(null);
  const [activity, setActivity] = useState(null);
  const [screenFrames, setScreenFrames] = useState({});
  const [expandedComputer, setExpandedComputer] = useState(null);
  const [isBroadcasting, setIsBroadcasting] = useState(false);
  const teacherStreamRef = useRef(null);
  const broadcastIntervalRef = useRef(null);

  const fetchComputers = async () => {
    try {
      const response = await fetch(`${API_URL}/computers`);
      const data = await response.json();
      setComputers(Object.values(data));
    } catch (error) {
      console.error("Failed to fetch computers:", error);
    } finally {
      setLoading(false);
    }
  };

  const sendCommand = async (pcId, command, data = {}) => {
    const response = await fetch(`${API_URL}/computers/${pcId}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, data }),
    });
    return response.json();
  };

  const viewComputer = async (pcId) => {
    try {
      const response = await fetch(`${API_URL}/computers/${pcId}/activity`);
      const data = await response.json();
      setSelectedComputer(pcId);
      setActivity(data.activity || null);
    } catch (error) {
      console.error("Failed to fetch computer activity:", error);
      alert("Could not load activity for this computer.");
    }
  };

  const sendMessage = async (pcId) => {
    const message = window.prompt(`Enter message for ${pcId}:`);
    if (!message || !message.trim()) return;

    try {
      const response = await fetch(`${API_URL}/computers/${pcId}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message.trim() }),
      });
      const data = await response.json();

      if (data.status === "message_sent") {
        alert(`Message sent to ${pcId}`);
      } else {
        alert(`Message failed: ${data.status}`);
      }
    } catch (error) {
      console.error("Message failed:", error);
      alert("Could not send message.");
    }
  };

  const lockComputer = async (pcId) => {
    try {
      const result = await sendCommand(pcId, "LOCK");
      if (result.status === "command_sent") {
        alert(`Lock command sent to ${pcId}`);
      } else {
        alert(`Lock failed: ${result.status}`);
      }
    } catch (error) {
      console.error("Lock failed:", error);
      alert("Could not send lock command.");
    }
  };

  const pingComputer = async (pcId) => {
    try {
      const response = await fetch(`${API_URL}/computers/${pcId}/ping`, {
        method: "POST",
      });
      const data = await response.json();
      alert(
        data.status === "ping_sent"
          ? `${pcId} responded to the ping command.`
          : `${pcId} did not respond: ${data.status}`
      );
    } catch (error) {
      console.error("Ping failed:", error);
      alert("Could not send ping command.");
    }
  };

  useEffect(() => {
    fetchComputers();
    const interval = setInterval(fetchComputers, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!selectedComputer) return;

    let cancelled = false;
    const fetchActivity = async () => {
      try {
        const response = await fetch(
          `${API_URL}/computers/${selectedComputer}/activity`
        );
        const data = await response.json();
        if (!cancelled) setActivity(data.activity || null);
      } catch (error) {
        console.error("Failed to refresh activity:", error);
      }
    };

    fetchActivity();
    const interval = setInterval(fetchActivity, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [selectedComputer]);

  useEffect(() => {
    if (computers.length === 0) return;

    let cancelled = false;

    const fetchScreenFrames = async () => {
      const onlineComputers = computers.filter(
        (computer) => computer.status === "Online"
      );

      const results = await Promise.all(
        onlineComputers.map(async (computer) => {
          try {
            const response = await fetch(
              `${API_URL}/computers/${computer.pc_id}/screen`
            );
            const data = await response.json();

            if (data.status === "ok" && data.frame) {
              return [
                computer.pc_id,
                `data:image/jpeg;base64,${data.frame}`,
              ];
            }
          } catch (error) {
            console.error(`Failed to fetch ${computer.pc_id} screen:`, error);
          }
          return null;
        })
      );

      if (!cancelled) {
        setScreenFrames((previous) => {
          const updated = { ...previous };
          for (const result of results) {
            if (result) updated[result[0]] = result[1];
          }
          return updated;
        });
      }
    };

    fetchScreenFrames();
    const interval = setInterval(fetchScreenFrames, 1000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [computers]);

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
          <span className="status-dot" />
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

        <div className="broadcast-controls">
          {isBroadcasting ? (
            <button onClick={stopTeacherBroadcast}>
              Stop Broadcast
            </button>
            ) : (
            <button onClick={startTeacherBroadcast}>
              Start Broadcast
            </button>
          )}

          <button onClick={fetchComputers}>Refresh</button>
        </div>
      </div>
      
          {loading ? (
            <div className="empty-state">Loading computers...</div>
          ) : computers.length === 0 ? (
            <div className="empty-state">No computers connected.</div>
          ) : (
            <div className="computer-grid">
              {computers.map((computer) => {
                const frame = screenFrames[computer.pc_id];

                return (
                  <article
                    className="computer-card compact-computer-card"
                    key={computer.pc_id}
                    tabIndex={0}
                    role="button"
                    aria-label={`Open ${computer.pc_id} screen`}
                    onClick={() => setExpandedComputer(computer.pc_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setExpandedComputer(computer.pc_id);
                      }
                    }}
                  >
                    <div className="computer-preview">
                      {frame ? (
                        <img
                          className="computer-preview-image"
                          src={frame}
                          alt={`Live screen preview for ${computer.pc_id}`}
                        />
                      ) : (
                        <div className="computer-preview-placeholder">
                          <span className="preview-monitor-icon">▣</span>
                          <span>
                            {computer.status === "Online"
                              ? "Waiting for screen..."
                              : "Computer offline"}
                          </span>
                        </div>
                      )}

                      <span
                        className={
                          computer.status === "Online"
                            ? "preview-status online"
                            : "preview-status offline"
                        }
                      >
                        {computer.status}
                      </span>

                      <div
                        className="computer-hover-controls"
                        onClick={(event) => event.stopPropagation()}
                      >
                        <button onClick={() => viewComputer(computer.pc_id)}>
                          View Activity
                        </button>
                        <button onClick={() => lockComputer(computer.pc_id)}>
                          🔒 Lock
                        </button>
                        <button onClick={() => pingComputer(computer.pc_id)}>
                          📡 Ping
                        </button>
                        <button onClick={() => sendMessage(computer.pc_id)}>
                          💬 Message
                        </button>
                      </div>
                    </div>

                    <div className="computer-card-caption">
                      <h3>{computer.pc_id}</h3>
                      <span>{computer.hostname || "Computer"}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </main>

      {selectedComputer && (
        <div
          className="lab-modal-backdrop"
          onClick={() => setSelectedComputer(null)}
        >
          <section
            className="lab-modal activity-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`${selectedComputer} activity`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <div>
                <h2>{selectedComputer} Activity</h2>
                <p>Live activity information</p>
              </div>
              <button
                className="modal-close-button"
                onClick={() => setSelectedComputer(null)}
                aria-label="Close activity"
              >
                ×
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
                  <strong>{activity.cpu_percent ?? "N/A"}%</strong>
                </div>
                <div className="activity-card">
                  <span>Memory Usage</span>
                  <strong>{activity.memory_percent ?? "N/A"}%</strong>
                </div>
                <div className="activity-card">
                  <span>Idle Time</span>
                  <strong>{activity.idle_seconds ?? "N/A"} seconds</strong>
                </div>
              </div>
            ) : (
              <div className="empty-state">No activity data available.</div>
            )}
          </section>
        </div>
      )}

      {expandedComputer && (
        <div
          className="lab-modal-backdrop screen-modal-backdrop"
          onClick={() => setExpandedComputer(null)}
        >
          <section
            className="lab-modal screen-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`${expandedComputer} screen`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <div>
                <h2>{expandedComputer} · Live Screen</h2>
                <p>Live screen preview</p>
              </div>
              <button
                className="modal-close-button"
                onClick={() => setExpandedComputer(null)}
                aria-label="Close screen"
              >
                ×
              </button>
            </div>

            <div className="expanded-screen-viewer">
              {screenFrames[expandedComputer] ? (
                <img
                  src={screenFrames[expandedComputer]}
                  alt={`Enlarged screen of ${expandedComputer}`}
                />
              ) : (
                <div className="expanded-screen-placeholder">
                  <span className="preview-monitor-icon">▣</span>
                  <p>
                    {computers.find((pc) => pc.pc_id === expandedComputer)
                      ?.status === "Online"
                      ? "Waiting for the first screen frame..."
                      : "This computer is offline."}
                  </p>
                </div>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
