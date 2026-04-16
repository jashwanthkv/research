export default function ResultView({ results = [], loading = false }) {
  const formatContent = (content) => {
    if (!content) return "";
    let text =
      typeof content === "string"
        ? content
        : typeof content === "object"
        ? JSON.stringify(content, null, 2)
        : String(content);
    return text.replace(/\*\*/g, "").replace(/\*/g, "").trim();
  };

  // Empty state
  if (results.length === 0 && !loading) {
    return (
      <div className="result-container">
        <div className="result-header">
          <h3 className="result-title">🎯 Research Results</h3>
        </div>
        <div className="result-body result-body--empty">
          <div className="explanation-section">
            <h4 className="explanation-title">📝 Detailed Explanation</h4>
            <div className="explanation-text placeholder">
              Results and explanations will appear here after you submit a query.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="result-container">
      <div className="result-header">
        <h3 className="result-title">🎯 Research Results</h3>
        {results.length > 0 && (
          <span style={{
            fontSize: "0.72rem",
            color: "var(--text-muted)",
            background: "var(--surface3)",
            padding: "0.2rem 0.6rem",
            borderRadius: "20px"
          }}>
            {results.length} {results.length === 1 ? "result" : "results"}
          </span>
        )}
      </div>

      {/* Scrollable chat-style history */}
      <div className="result-body">

        {results.map((result, resultIdx) => {
          const inner       = result.result || result;
          const explanation = inner.explanation || result.explanation || "";
          const error       = inner.error      || result.error      || null;
          const papers      = result.papers || [];

          return (
            <div key={resultIdx} className="result-entry">
              {/* Entry separator label for multiple results */}
              {results.length > 1 && (
                <div className="entry-divider">
                  <span className="entry-label">Query #{resultIdx + 1}</span>
                </div>
              )}

              {/* Papers list */}
              {papers.length > 0 && (
                <div className="papers-section">
                  <h4 className="papers-title">📚 Reference Papers</h4>
                  <ul className="papers-list">
                    {papers.map((p, idx) => (
                      <li key={idx} className="paper-item">
                        <a
                          href={p.link || p.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="paper-link"
                        >
                          {p.title}
                        </a>
                        {p.year && <span className="paper-year">({p.year})</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Explanation */}
              {explanation ? (
                <div className="explanation-section">
                  <h4 className="explanation-title">📝 Detailed Explanation</h4>
                  <div className="explanation-text">
                    {formatContent(explanation)}
                  </div>
                </div>
              ) : (
                <div className="explanation-section">
                  <h4 className="explanation-title">📝 Detailed Explanation</h4>
                  <div className="explanation-text placeholder">
                    No explanation returned for this query.
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="explanation-section">
                  <h4 className="explanation-title" style={{ color: "var(--error)" }}>
                    ⚠️ Error
                  </h4>
                  <div
                    className="explanation-text"
                    style={{ borderLeftColor: "var(--error)", color: "var(--error)" }}
                  >
                    {formatContent(error)}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {/* Loading indicator for in-progress query */}
        {loading && (
          <div className="result-entry result-entry--loading">
            <div className="entry-divider">
              <span className="entry-label">Query #{results.length + 1}</span>
            </div>
            <div className="explanation-section">
              <h4 className="explanation-title">📝 Detailed Explanation</h4>
              <div className="explanation-text placeholder loading-pulse">
                Researching… please wait.
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}