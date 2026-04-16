import { useState } from "react";

export default function QueryInput({ onSubmit, disabled }) {
  const [query, setQuery] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");

  const handleSubmit = () => {
    if (query.trim()) {
      onSubmit(query, yearFrom, yearTo);
      setQuery("");
      setYearFrom("");
      setYearTo("");
    }
  };

  const handleKeyDown = (e) => {
    if (e.ctrlKey && e.key === "Enter") {
      handleSubmit();
    }
  };

  return (
    <div className="query-input-wrapper">
      <textarea
        className="query-textarea"
        placeholder="Ask your research question... (e.g., 'Recent advances in machine learning for NLP')"
        value={query}
        disabled={disabled}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: "0.9rem", display: "block", marginBottom: "0.25rem" }}>
            Year From (Optional)
          </label>
          <input
            type="number"
            min="1900"
            max="2100"
            value={yearFrom}
            disabled={disabled}
            onChange={(e) => setYearFrom(e.target.value)}
            placeholder="e.g., 2020"
            style={{ width: "100%", padding: "0.5rem" }}
          />
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: "0.9rem", display: "block", marginBottom: "0.25rem" }}>
            Year To (Optional)
          </label>
          <input
            type="number"
            min="1900"
            max="2100"
            value={yearTo}
            disabled={disabled}
            onChange={(e) => setYearTo(e.target.value)}
            placeholder="e.g., 2025"
            style={{ width: "100%", padding: "0.5rem" }}
          />
        </div>
      </div>
      <button className="submit-btn" onClick={handleSubmit} disabled={disabled} style={{ marginTop: "0.5rem" }}>
        {disabled ? (
          <>
            <span className="loading-spinner" style={{ marginRight: "0.5rem" }} />
            Processing...
          </>
        ) : (
          "🚀 Submit Query"
        )}
      </button>
    </div>
  );
}
