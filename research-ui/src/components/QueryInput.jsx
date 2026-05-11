import { useState } from "react";

export default function QueryInput({ onSubmit, disabled }) {
  const [query, setQuery] = useState("");

  const handleSubmit = () => {
    if (query.trim()) {
      onSubmit(query);
      setQuery("");
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
      <button className="submit-btn" onClick={handleSubmit} disabled={disabled} style={{ marginTop: "0.5rem" }}>
        {disabled ? (
          <>
            <span className="loading-spinner" style={{ marginRight: "0.5rem" }} />
            Processing...
          </>
        ) : (
          "Submit Query"
        )}
      </button>
    </div>
  );
}
