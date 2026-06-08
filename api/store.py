"""In-memory per-client engagement store.

Holds the latest PipelineResult for each ingested client so the multi-engagement
sidebar, dashboards, chat and report endpoints can all read from one place.
State is per-process and resets on restart - acceptable for the showcase; a
production deployment would back this with a database / object store.
"""

import threading


class ClientStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._clients = {}  # client_id -> {result, name}

    def put(self, client_id, result):
        with self._lock:
            self._clients[client_id] = result

    def get(self, client_id):
        return self._clients.get(client_id)

    def remove(self, client_id):
        with self._lock:
            return self._clients.pop(client_id, None) is not None

    def list(self):
        out = []
        for cid, res in self._clients.items():
            k = res.get("kpis", {})
            out.append({
                "client_id": cid,
                "client_name": res.get("client_name", cid),
                "dq_overall": res.get("scorecard", {}).get("overall", 0),
                "reconciled_pct": k.get("reconciled_pct", 0),
                "material_breaks": k.get("material_breaks", 0),
                "dupes_flagged": k.get("dupes_flagged", 0),
                "gl_rows": k.get("gl_rows", 0),
            })
        return sorted(out, key=lambda c: c["client_name"])

    def __contains__(self, client_id):
        return client_id in self._clients


STORE = ClientStore()
