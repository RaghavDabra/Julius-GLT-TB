"""Append-only audit trail.

Auditability is the whole point of the case study: an assurance team must be able
to trace every figure in the final report back to a transformation on the raw
data. Each pipeline stage appends one or more entries here; the trail is never
mutated, only appended to, and serializes straight into the machine-readable
deliverable (``/api/report/<id>.json``).
"""

from datetime import datetime, timezone


class AuditTrail:
    def __init__(self):
        self._entries = []
        self._seq = 0

    def add(self, stage, action, rows_affected=0, ai_used=False, details=None,
            inputs=None, outputs=None):
        """Record one transformation. Returns the entry (also stored)."""
        self._seq += 1
        entry = {
            "seq": self._seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "action": action,
            "rows_affected": int(rows_affected),
            "ai_used": bool(ai_used),
            "inputs": inputs or {},
            "outputs": outputs or {},
            "details": details or "",
        }
        self._entries.append(entry)
        return entry

    def to_list(self):
        return list(self._entries)

    def __len__(self):
        return len(self._entries)
