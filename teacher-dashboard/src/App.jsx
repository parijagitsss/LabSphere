import { useEffect, useState, useRef } from "react";
import "./App.css";

const API_URL = "http://10.19.154.84:8000";

function App() {
  const [computers, setComputers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedComputer, setSelectedComputer] = useState(null);
  const [activity, setActivity] = useState(null);
  const [screenFrames, setScreenFrames] = useState({});
  const [expandedComputer, setExpandedComputer] = useState(null);
  const [annotationMode, setAnnotationMode] = useState(false);
  const [annotationColor, setAnnotationColor] = useState("#ff3333");
  const [annotationLines, setAnnotationLines] = useState({});
  const [currentLine, setCurrentLine] = useState(null);
  const annotationCanvasRef = useRef(null);
  const currentLineRef = useRef(null);
  const [isBroadcasting, setIsBroadcasting] = useState(false);
  const teacherStreamRef = useRef(null);
  const broadcastIntervalRef = useRef(null);
  // Broadcast annotation state
  const [broadcastPenEnabled, setBroadcastPenEnabled] = useState(false);
  const [broadcastPenColor, setBroadcastPenColor] = useState("#ff3333");
  const [broadcastAnnotationLines, setBroadcastAnnotationLines] = useState([]);
  const [currentBroadcastLine, setCurrentBroadcastLine] = useState(null);
  const currentBroadcastLineRef = useRef(null);
  const broadcastVideoRef = useRef(null);
  const broadcastCanvasRef = useRef(null);
  const [broadcastPreviewFrame, setBroadcastPreviewFrame] = useState(null);
  const broadcastAnnotationLinesRef = useRef([]);
  useEffect(() => {
  broadcastAnnotationLinesRef.current = broadcastAnnotationLines;
}, [broadcastAnnotationLines]);

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

  
  const notifyStudentsBroadcast = async (command) => {
    try {
      const response = await fetch(`${API_URL}/computers/broadcast`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          command,
          data: {},
        }),
      });

      if (!response.ok) {
        console.error("Failed to notify students:", response.status);
      }
    } catch (error) {
      console.error("Could not notify students:", error);
    }
  };

  
  const startTeacherBroadcast = async () => {
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        frameRate: 5,
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    });

    teacherStreamRef.current = stream;
    setIsBroadcasting(true);

    notifyStudentsBroadcast("START_TEACHER_BROADCAST");

    const video = document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;

    await video.play();

    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");

    canvas.width = 1280;
    canvas.height = 720;

    broadcastCanvasRef.current = canvas;

    const sendFrame = async () => {
      if (!video.videoWidth || !video.videoHeight) return;

      // Draw the captured teacher screen.
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Include completed and currently drawn strokes.
      const linesToDraw = [
        ...broadcastAnnotationLinesRef.current,
        ...(currentBroadcastLineRef.current
          ? [currentBroadcastLineRef.current]
          : []),
      ];

      linesToDraw.forEach((line) => {
        if (!line.points || line.points.length < 2) return;

        context.beginPath();
        context.strokeStyle = line.color;
        context.lineWidth = 4;
        context.lineCap = "round";
        context.lineJoin = "round";

        line.points.forEach((point, index) => {
          const x = point.x * canvas.width;
          const y = point.y * canvas.height;

          if (index === 0) {
            context.moveTo(x, y);
          } else {
            context.lineTo(x, y);
          }
        });

        context.stroke();
      });

      // Update the teacher's preview with the composited frame.
      const imageData = canvas.toDataURL("image/jpeg", 0.6);
      setBroadcastPreviewFrame(imageData);

      // Send the same annotated frame to the backend.
      const frame = imageData.split(",")[1];

      try {
        await fetch(`${API_URL}/teacher/broadcast/frame`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ frame }),
        });
      } catch (error) {
        console.error("Failed to send teacher screen frame:", error);
      }
    };

    broadcastIntervalRef.current = setInterval(sendFrame, 1000);

    // Send an initial frame without waiting for the first interval.
    sendFrame();

    stream.getVideoTracks()[0].addEventListener("ended", () => {
      stopTeacherBroadcast();
    });
  } catch (error) {
    console.error("Failed to start teacher broadcast:", error);
    stopTeacherBroadcast();
    alert("Unable to start screen sharing. Please try again.");
  }
};

  const stopTeacherBroadcast = () => {
    if (broadcastIntervalRef.current) {
      clearInterval(broadcastIntervalRef.current);
      broadcastIntervalRef.current = null;
    }

    if (teacherStreamRef.current) {
      teacherStreamRef.current.getTracks().forEach((track) => track.stop());
      teacherStreamRef.current = null;
    }

    setIsBroadcasting(false);
    notifyStudentsBroadcast("STOP_TEACHER_BROADCAST");

    fetch(`${API_URL}/teacher/broadcast/frame`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: null }),
    }).catch((error) => {
      console.error("Failed to clear teacher broadcast frame:", error);
    });
  };


  const startAnnotation = (event, screenId) => {
    if (!annotationMode) return;

    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const point = {
      x: (event.clientX - rect.left) / rect.width,
      y: (event.clientY - rect.top) / rect.height,
    };

    const line = {
      screenId,
      color: annotationColor,
      points: [point],
    };

    currentLineRef.current = line;
    setCurrentLine(line);
  };

  const continueAnnotation = (event) => {
    const activeLine = currentLineRef.current;
    if (!activeLine) return;

    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const point = {
      x: (event.clientX - rect.left) / rect.width,
      y: (event.clientY - rect.top) / rect.height,
    };

    const updatedLine = {
      ...activeLine,
      points: [...activeLine.points, point],
    };

    currentLineRef.current = updatedLine;
    setCurrentLine(updatedLine);
  };

  const finishAnnotation = () => {
    const line = currentLineRef.current;
    if (!line) return;

    currentLineRef.current = null;

    if (line.points.length > 1) {
      setAnnotationLines((previous) => ({
        ...previous,
        [line.screenId]: [
          ...(previous[line.screenId] || []),
          line,
        ],
      }));
    }

    setCurrentLine(null);
  };


  const clearAnnotations = (screenId) => {
    setAnnotationLines((previous) => ({
      ...previous,
      [screenId]: [],
    }));

    setCurrentLine((previous) =>
      previous?.screenId === screenId ? null : previous
    );
  };

  const startBroadcastAnnotation = (event) => {
  if (!broadcastPenEnabled || !isBroadcasting) return;

  const rect = event.currentTarget.getBoundingClientRect();
  if (!rect.width || !rect.height) return;

  const point = {
    x: (event.clientX - rect.left) / rect.width,
    y: (event.clientY - rect.top) / rect.height,
  };

  const line = {
    color: broadcastPenColor,
    points: [point],
  };

  currentBroadcastLineRef.current = line;
  setCurrentBroadcastLine(line);

  event.preventDefault();
  event.currentTarget.setPointerCapture(event.pointerId);
};

const continueBroadcastAnnotation = (event) => {
  const activeLine = currentBroadcastLineRef.current;
  if (!activeLine) return;

  const rect = event.currentTarget.getBoundingClientRect();
  if (!rect.width || !rect.height) return;

  const point = {
    x: (event.clientX - rect.left) / rect.width,
    y: (event.clientY - rect.top) / rect.height,
  };

  const updatedLine = {
    ...activeLine,
    points: [...activeLine.points, point],
  };

  currentBroadcastLineRef.current = updatedLine;
  setCurrentBroadcastLine(updatedLine);
};

const finishBroadcastAnnotation = () => {
  const line = currentBroadcastLineRef.current;
  if (!line) return;

  currentBroadcastLineRef.current = null;

  if (line.points.length > 1) {
    setBroadcastAnnotationLines((previous) => [...previous, line]);
  }

  setCurrentBroadcastLine(null);
};

const clearBroadcastAnnotations = () => {
  currentBroadcastLineRef.current = null;
  setCurrentBroadcastLine(null);
  setBroadcastAnnotationLines([]);
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

  {isBroadcasting && (
    <div className="broadcast-annotation-panel">
      <div className="annotation-toolbar">
        <button
          className={broadcastPenEnabled ? "pen-active" : ""}
          onClick={() =>
            setBroadcastPenEnabled((previous) => !previous)
          }
        >
          {broadcastPenEnabled ? "Disable Pen" : "Enable Pen"}
        </button>

        <label>
          Pen color
          <input
            type="color"
            value={broadcastPenColor}
            onChange={(event) =>
              setBroadcastPenColor(event.target.value)
            }
          />
        </label>

        <button onClick={clearBroadcastAnnotations}>
          Clear Annotations
        </button>
      </div>

      <div className="broadcast-annotation-screen">
        {broadcastPreviewFrame ? (
          <img
            src={broadcastPreviewFrame}
            alt="Teacher broadcast preview"
            draggable={false}
          />
        ) : (
          <div className="expanded-screen-placeholder">
            Waiting for broadcast frame...
          </div>
        )}

        <svg
          className={`annotation-canvas ${
            broadcastPenEnabled ? "drawing-enabled" : ""
          }`}
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          onPointerDown={startBroadcastAnnotation}
          onPointerMove={continueBroadcastAnnotation}
          onPointerUp={finishBroadcastAnnotation}
          onPointerCancel={finishBroadcastAnnotation}
        >
          {[
            ...broadcastAnnotationLines,
            ...(currentBroadcastLine
              ? [currentBroadcastLine]
              : []),
          ].map((line, index) => (
            <polyline
              key={index}
              points={line.points
                .map((point) => `${point.x},${point.y}`)
                .join(" ")}
              fill="none"
              stroke={line.color}
              strokeWidth="0.004"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </svg>
      </div>
    </div>
  )}

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
  <div className="annotation-toolbar">
    <button
      onClick={() => setAnnotationMode((previous) => !previous)}
    >
      {annotationMode ? "Disable Pen" : "Enable Pen"}
    </button>

    <label>
      Pen color
      <input
        type="color"
        value={annotationColor}
        onChange={(event) => setAnnotationColor(event.target.value)}
      />
    </label>

    <button onClick={() => clearAnnotations(expandedComputer)}>
      Clear Annotations
    </button>
  </div>

  <div className="annotation-screen">
    {screenFrames[expandedComputer] ? (
      <img
        src={screenFrames[expandedComputer]}
        alt={`Enlarged screen of ${expandedComputer}`}
        draggable={false}
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

    <svg
      ref={annotationCanvasRef}
      className={`annotation-canvas ${annotationMode ? "drawing-enabled" : ""}`}
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
      onPointerDown={(event) => {
  console.log("Pen clicked", {
    annotationMode,
    screen: expandedComputer,
  });

  if (!annotationMode) return;

  event.preventDefault();
  event.currentTarget.setPointerCapture(event.pointerId);
  startAnnotation(event, expandedComputer);
}}
      onPointerMove={(event) => {
  console.log("Pointer moving", {
    drawingEnabled: annotationMode,
    hasActiveLine: Boolean(currentLineRef.current),
  });
  continueAnnotation(event);
}}
      onPointerUp={finishAnnotation}
      onPointerCancel={finishAnnotation}
    >
      {(annotationLines[expandedComputer] || [])
        .concat(
          currentLine?.screenId === expandedComputer ? [currentLine] : []
        )
        .map((line, index) => (
          <polyline
            key={index}
            points={line.points
              .map((point) => `${point.x},${point.y}`)
              .join(" ")}
            fill="none"
            stroke={line.color}
            strokeWidth="0.004"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
    </svg>
  </div>
</div>

          </section>
        </div>
      )}
    </div>
  );
}

export default App;
