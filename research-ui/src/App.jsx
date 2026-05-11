import { useState, useEffect, useRef } from "react";
import QueryInput from "./components/QueryInput";
import ProgressTracker from "./components/progressTracker";
import ResultView from "./components/ResultView";
import { startTask, getTaskStatus, getTaskResult } from "./api/api";
import "./App.css";

const SESSION_KEY = "research_session_id";

export default function App() {
  const [taskId, setTaskId]       = useState(null);
  const [progress, setProgress]   = useState(null);
  const [results, setResults]     = useState([]);   // ← array of all results
  const [loading, setLoading]     = useState(false);
  const [darkMode, setDarkMode]   = useState(true);
  const bottomRef                 = useRef(null);

  const [sessionId, setSessionId] = useState(() => {
    return localStorage.getItem(SESSION_KEY) || null;
  });

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.remove("light-mode");
    } else {
      document.documentElement.classList.add("light-mode");
    }
  }, [darkMode]);

  // Auto-scroll to bottom when new result arrives
  useEffect(() => {
    if (results.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [results]);

  const saveSession = (sid) => {
    if (sid && sid !== sessionId) {
      setSessionId(sid);
      localStorage.setItem(SESSION_KEY, sid);
    }
  };

  const handleSubmit = async (query) => {
    setLoading(true);
    setProgress(null);

    const res = await startTask(query, sessionId);
    setTaskId(res.data.task_id);

    if (res.data?.session_id) {
      saveSession(res.data.session_id);
    }
  };

  useEffect(() => {
    if (!taskId) return;

    const interval = setInterval(async () => {
      const statusRes = await getTaskStatus(taskId);
      setProgress(statusRes.data.progress);

      if (statusRes.data.status === "completed") {
        clearInterval(interval);

        const resultRes = await getTaskResult(taskId);
        // Append new result to history
        setResults(prev => [...prev, resultRes.data]);

        const sid = resultRes.data?.result?.session_id;
        saveSession(sid);

        setLoading(false);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [taskId]);

  const handleNewSession = () => {
    localStorage.removeItem(SESSION_KEY);
    setSessionId(null);
    setResults([]);       // clear all results
    setProgress(null);
  };

  return (
    <div className="app-container">
      <div className="app-header">
        <h1>Research Assistant</h1>
        <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>

          {sessionId && (
            <span style={{
              fontSize: "0.7rem",
              color: "var(--text-muted)",
              fontFamily: "monospace",
              background: "var(--surface2)",
              padding: "0.2rem 0.6rem",
              borderRadius: "4px",
              border: "1px solid var(--border)"
            }}>
              {sessionId.slice(0, 8)}…
            </span>
          )}

          {sessionId && !loading && (
            <button
              onClick={handleNewSession}
              style={{
                fontSize: "0.75rem",
                padding: "0.25rem 0.7rem",
                background: "var(--surface2)",
                color: "var(--text-muted)",
                border: "1px solid var(--border)",
                borderRadius: "6px",
                cursor: "pointer"
              }}
            >
              New Session
            </button>
          )}

          <button
            className="dark-mode-toggle"
            onClick={() => setDarkMode(!darkMode)}
            title="Toggle theme"
          >
            {darkMode ? "☀️" : "🌙"}
          </button>
        </div>
      </div>

      <div className="layout-with-results">
        <div className="left-panel">
          <div className="section">
            <QueryInput onSubmit={handleSubmit} disabled={loading} />
          </div>
          <div className="section-divider" />
          <div className="section">
            <ProgressTracker progress={progress} />
          </div>
        </div>

        <div className="right-panel">
          {/* Chat-like scrollable history */}
          <ResultView results={results} loading={loading} />
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}