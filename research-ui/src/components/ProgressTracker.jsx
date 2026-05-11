export default function ProgressTracker({ progress }) {
  if (!progress) return null;

  const getStatusIcon = (state) => {
    switch (state) {
      case "pending":
        return "⏳";
      case "running":
        return "⚙️";
      case "done":
        return "✅";
      case "skipped":
        return "⏭️";
      case "error":
        return "";
      default:
        return "○";
    }
  };

  return (
    <div className="progress-container">
      <h3 className="progress-title">
        Live Progress
      </h3>
      <ul className="progress-list">
        {progress.map((p) => (
          <li key={p.step} className="progress-item">
            <div className={`status-badge ${p.state}`}>
              {getStatusIcon(p.state)}
            </div>
            <span className="progress-step">{p.step.charAt(0).toUpperCase() + p.step.slice(1)}</span>
            <span className={`progress-state ${p.state}`}>{p.state}</span>
            {/* Progress bar area (shows animated fill while pending/running) */}
            <div className={`progress-bar ${p.state}`}>
              <div className={`progress-fill ${p.state}`} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
