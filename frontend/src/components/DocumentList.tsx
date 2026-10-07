import type { Document } from "../api/client";

interface Props {
  documents: Document[];
  selectedId: number | null;
  onSelect: (doc: Document) => void;
  onDelete: (id: number) => void;
}

function statusLabel(doc: Document): string {
  if (doc.status === "ready") return `${doc.chunk_count ?? 0} chunks`;
  if (doc.status === "failed") return doc.error_message ?? "Failed";
  return "Processing…";
}

export function DocumentList({ documents, selectedId, onSelect, onDelete }: Props) {
  if (documents.length === 0) {
    return <p className="muted">No documents yet.</p>;
  }

  return (
    <ul className="doc-list">
      {documents.map((doc) => (
        <li
          key={doc.id}
          className={doc.id === selectedId ? "selected" : ""}
          onClick={() => onSelect(doc)}
        >
          <div className="doc-row">
            <span className="doc-name">{doc.filename}</span>
            <button
              type="button"
              className="icon-btn"
              aria-label="Delete document"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(doc.id);
              }}
            >
              ×
            </button>
          </div>
          <span className={`status status-${doc.status}`}>{statusLabel(doc)}</span>
        </li>
      ))}
    </ul>
  );
}
