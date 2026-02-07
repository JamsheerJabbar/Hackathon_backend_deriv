"""
Scan Memory - Persistent scan history for adaptive mission intelligence.
Tracks past missions, domain severity distribution, and critical findings
so the brainstormer can adapt future scans.

Also provides full scan persistence for the history viewer.

Storage layers (in priority order):
  1. Redis/Valkey – fast, shared across instances
  2. Local JSON files – durable fallback
Reads try Redis first; writes go to both.
"""
import json
import os
import glob as globmod
from datetime import datetime
from collections import Counter

import redis
from app.core.config import settings
from app.core.logger import logger

MEMORY_FILE = "sentinel_scan_history.json"
SCAN_HISTORY_DIR = "scan_history"

# Redis key constants
REDIS_SCAN_HISTORY_KEY = "sentinel:scan_history"       # JSON-encoded list (summary records)
REDIS_SCAN_INDEX_KEY = "sentinel:scan_index"            # JSON-encoded list of scan metadata
REDIS_SCAN_PREFIX = "sentinel:scan:"                    # Per-scan full data, e.g. sentinel:scan:scan-20260207T113157
REDIS_SCAN_TTL = 60 * 60 * 24 * 30                     # 30 days TTL for individual scans


# ─── Module-level Redis client (lazy singleton) ─────────────────────────────

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    """Return a shared Redis client, or None if connection fails."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable for scan memory – falling back to JSON: {e}")
            _redis_client = None
    return _redis_client


class ScanMemory:

    MAX_HISTORY = 50

    def __init__(self):
        self.history = self._load()

    # ─── Summary History (_load / _save) ────────────────────────────────────

    def _load(self) -> list:
        """Load summary history: try Redis first, fall back to JSON file."""
        # 1) Try Redis
        r = _get_redis()
        if r is not None:
            try:
                raw = r.get(REDIS_SCAN_HISTORY_KEY)
                if raw:
                    data = json.loads(raw)
                    logger.debug("Scan history loaded from Redis.")
                    return data
            except Exception as e:
                logger.warning(f"Redis read failed for scan history: {e}")

        # 2) Fallback: JSON file
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r") as f:
                    data = json.load(f)
                # Back-fill Redis if it was empty
                self._save_history_to_redis(data)
                return data
            except Exception:
                return []
        return []

    def _save(self):
        """Persist summary history to both JSON file and Redis."""
        trimmed = self.history[-self.MAX_HISTORY:]

        # JSON file (existing behaviour)
        try:
            with open(MEMORY_FILE, "w") as f:
                json.dump(trimmed, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save scan memory to JSON: {e}")

        # Redis
        self._save_history_to_redis(trimmed)

    def _save_history_to_redis(self, data: list):
        """Helper: push summary history into Redis."""
        r = _get_redis()
        if r is None:
            return
        try:
            r.set(REDIS_SCAN_HISTORY_KEY, json.dumps(data, default=str))
        except Exception as e:
            logger.warning(f"Redis write failed for scan history: {e}")

    def record_scan(self, detections: list):
        scan_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "missions": [],
            "domain_scores": {},
            "critical_domains": [],
        }

        domain_scores = {}
        for det in detections:
            domain = det.get("domain", "general")
            risk_score = det.get("risk_score", 0)

            scan_record["missions"].append(
                {
                    "name": det.get("mission_name"),
                    "query": det.get("original_query", ""),
                    "domain": domain,
                    "risk_score": risk_score,
                    "severity": det.get("severity"),
                    "data_count": det.get("data_count", 0),
                }
            )

            if domain not in domain_scores:
                domain_scores[domain] = []
            domain_scores[domain].append(risk_score)

            if det.get("severity") == "CRITICAL":
                if domain not in scan_record["critical_domains"]:
                    scan_record["critical_domains"].append(domain)

        scan_record["domain_scores"] = {
            d: round(sum(s) / len(s)) for d, s in domain_scores.items()
        }

        self.history.append(scan_record)
        self._save()

    def get_adaptive_context(self) -> dict:
        if not self.history:
            return {
                "domain_weights": {"security": 2, "compliance": 2, "risk": 2, "operations": 2},
                "avoid_queries": [],
                "focus_areas": [],
                "scan_count": 0,
            }

        recent = self.history[-5:]

        # Domain weights: higher risk → more missions (base 2, max 4)
        domain_avg_scores = Counter()
        domain_counts = Counter()
        for scan in recent:
            for d, score in scan.get("domain_scores", {}).items():
                domain_avg_scores[d] += score
                domain_counts[d] += 1

        domain_weights = {}
        for domain in ["security", "compliance", "risk", "operations"]:
            avg = domain_avg_scores.get(domain, 0) / max(domain_counts.get(domain, 1), 1)
            domain_weights[domain] = min(4, max(1, round(2 + avg / 40)))

        # Avoid repeating recent queries
        recent_queries = []
        for scan in recent[-3:]:
            for m in scan.get("missions", []):
                q = m.get("query", "")
                if q and q not in recent_queries:
                    recent_queries.append(q)

        # Focus areas from critical findings in last scan
        focus_areas = []
        if recent:
            last_scan = recent[-1]
            for m in last_scan.get("missions", []):
                if m.get("severity") == "CRITICAL":
                    focus_areas.append(
                        f"CRITICAL finding in {m['domain']}: '{m['name']}' "
                        f"(risk score {m['risk_score']}). Generate deeper variations."
                    )

        return {
            "domain_weights": domain_weights,
            "avoid_queries": recent_queries[-15:],
            "focus_areas": focus_areas,
            "scan_count": len(self.history),
        }

    # ─── Full Scan Persistence (for history viewer) ──────────────────────────

    def save_full_scan(self, scan_id: str, detections: list,
                       clusters: list = None, narrative: dict = None):
        """Persist complete scan results to JSON file **and** Redis."""
        os.makedirs(SCAN_HISTORY_DIR, exist_ok=True)

        critical_count = sum(1 for d in detections if d.get("severity") == "CRITICAL")
        high_count = sum(1 for d in detections if d.get("severity") == "HIGH")
        top_scores = sorted([d.get("risk_score", 0) for d in detections], reverse=True)
        overall_risk = round(sum(top_scores[:3]) / max(len(top_scores[:3]), 1))

        if narrative and narrative.get("overall_risk"):
            overall_risk = narrative["overall_risk"]

        overall_severity = "LOW"
        if critical_count > 0:
            overall_severity = "CRITICAL"
        elif high_count > 0:
            overall_severity = "HIGH"

        data = {
            "scan_id": scan_id,
            "timestamp": datetime.utcnow().isoformat(),
            "stats": {
                "total_missions": len(detections),
                "critical_count": critical_count,
                "high_count": high_count,
                "overall_risk": overall_risk,
                "overall_severity": overall_severity,
            },
            "detections": detections,
            "clusters": clusters or [],
            "narrative": narrative,
        }

        # ── JSON file (existing behaviour) ────────────────────────────────
        filepath = os.path.join(SCAN_HISTORY_DIR, f"{scan_id}.json")
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save full scan to JSON: {e}")

        # ── Redis ─────────────────────────────────────────────────────────
        self._save_full_scan_to_redis(scan_id, data)

        # ── Update scan index in Redis ────────────────────────────────────
        self._update_scan_index_in_redis(data)

        # Enforce cap (JSON files)
        self._prune_old_scans()

    def _save_full_scan_to_redis(self, scan_id: str, data: dict):
        """Store full scan data in Redis under sentinel:scan:<scan_id>."""
        r = _get_redis()
        if r is None:
            return
        try:
            key = f"{REDIS_SCAN_PREFIX}{scan_id}"
            r.set(key, json.dumps(data, default=str), ex=REDIS_SCAN_TTL)
            logger.debug(f"Full scan {scan_id} saved to Redis.")
        except Exception as e:
            logger.warning(f"Redis write failed for full scan {scan_id}: {e}")

    def _update_scan_index_in_redis(self, data: dict):
        """Append scan metadata to the Redis scan index list."""
        r = _get_redis()
        if r is None:
            return
        try:
            # Load existing index
            raw = r.get(REDIS_SCAN_INDEX_KEY)
            index: list = json.loads(raw) if raw else []

            # Append new entry
            entry = {
                "scan_id": data["scan_id"],
                "timestamp": data["timestamp"],
                **data.get("stats", {}),
            }
            index.append(entry)

            # Trim to MAX_HISTORY
            index = index[-self.MAX_HISTORY:]

            r.set(REDIS_SCAN_INDEX_KEY, json.dumps(index, default=str))
        except Exception as e:
            logger.warning(f"Redis write failed for scan index: {e}")

    def _prune_old_scans(self):
        """Keep only the most recent MAX_HISTORY scan files."""
        files = sorted(globmod.glob(os.path.join(SCAN_HISTORY_DIR, "scan-*.json")))
        if len(files) > self.MAX_HISTORY:
            for old in files[: len(files) - self.MAX_HISTORY]:
                try:
                    os.remove(old)
                except Exception:
                    pass

    # ─── Read methods (Redis-first, JSON fallback) ────────────────────────────

    def list_scans(self) -> list:
        """Return metadata for all persisted scans, newest first.
        Tries Redis index first, falls back to scanning JSON files."""

        # 1) Try Redis
        r = _get_redis()
        if r is not None:
            try:
                raw = r.get(REDIS_SCAN_INDEX_KEY)
                if raw:
                    index = json.loads(raw)
                    index.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
                    logger.debug("Scan index loaded from Redis.")
                    return index
            except Exception as e:
                logger.warning(f"Redis read failed for scan index: {e}")

        # 2) Fallback: JSON files
        if not os.path.isdir(SCAN_HISTORY_DIR):
            return []

        scans = []
        for filepath in globmod.glob(os.path.join(SCAN_HISTORY_DIR, "scan-*.json")):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                scans.append({
                    "scan_id": data["scan_id"],
                    "timestamp": data["timestamp"],
                    **data.get("stats", {}),
                })
            except Exception:
                continue

        scans.sort(key=lambda s: s["timestamp"], reverse=True)

        # Back-fill Redis index so future reads are fast
        self._backfill_scan_index_to_redis(scans)

        return scans

    def get_scan(self, scan_id: str) -> dict | None:
        """Load full scan data by ID. Tries Redis first, falls back to JSON."""

        # 1) Try Redis
        r = _get_redis()
        if r is not None:
            try:
                raw = r.get(f"{REDIS_SCAN_PREFIX}{scan_id}")
                if raw:
                    logger.debug(f"Scan {scan_id} loaded from Redis.")
                    return json.loads(raw)
            except Exception as e:
                logger.warning(f"Redis read failed for scan {scan_id}: {e}")

        # 2) Fallback: JSON file
        filepath = os.path.join(SCAN_HISTORY_DIR, f"{scan_id}.json")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            # Back-fill Redis for next time
            self._save_full_scan_to_redis(scan_id, data)
            return data
        except Exception:
            return None

    def _backfill_scan_index_to_redis(self, scans: list):
        """Write the full scan index to Redis when it was missing."""
        r = _get_redis()
        if r is None:
            return
        try:
            r.set(REDIS_SCAN_INDEX_KEY, json.dumps(scans, default=str))
            logger.debug("Back-filled scan index to Redis from JSON files.")
        except Exception as e:
            logger.warning(f"Redis back-fill for scan index failed: {e}")


scan_memory = ScanMemory()
