from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.orchestration.workflow import app_graph
from app.orchestration.sentinel_agent import SentinelBrainstormer
from app.orchestration.risk_scorer import risk_scorer
from app.orchestration.deep_dive import deep_dive_generator
from app.orchestration.correlation_engine import correlation_engine
from app.orchestration.narrative_generator import narrative_generator
from app.orchestration.scan_memory import scan_memory, _get_redis
from app.services.slack_notifier import notify_slack, notify_slack_narrative
from app.core.config import settings
from app.core.logger import logger, _mission_log_buffer
from datetime import datetime
import asyncio
import json

router = APIRouter()
brainstormer = SentinelBrainstormer()

# Redis key for active scan progress (TTL 1 hour)
_PROGRESS_PREFIX = "sentinel:scan_progress:"
_PROGRESS_TTL = 3600


# ─── Redis progress helpers ─────────────────────────────────────────────────

def _update_progress(scan_id: str, data: dict):
    """Write current scan progress to Redis so the polling endpoint can read it."""
    r = _get_redis()
    if r is None:
        return
    try:
        r.set(f"{_PROGRESS_PREFIX}{scan_id}", json.dumps(data, default=str), ex=_PROGRESS_TTL)
    except Exception as e:
        logger.warning(f"Redis progress write failed for {scan_id}: {e}")


def _read_progress(scan_id: str) -> dict | None:
    """Read current scan progress from Redis."""
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(f"{_PROGRESS_PREFIX}{scan_id}")
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Redis progress read failed for {scan_id}: {e}")
        return None


# ─── Helper: execute a single mission through the NL2SQL graph ──────────────

async def run_mission(mission: dict) -> dict:
    log_buf: list = []
    _mission_log_buffer.set(log_buf)

    initial_state = {
        "user_question": mission["query"],
        "domain": mission["domain"],
        "conversation_history": [],
        "retry_count": 0,
    }

    try:
        result = await app_graph.ainvoke(initial_state)
        query_results = result.get("query_result") or []
        scoring = risk_scorer.score(mission, query_results)

        return {
            "mission_id": mission["id"],
            "mission_name": mission["name"],
            "domain": mission["domain"],
            "severity": scoring["severity"],
            "risk_score": scoring["risk_score"],
            "risk_factors": scoring["factors"],
            "sql": result.get("generated_sql"),
            "data_count": len(query_results),
            "results": query_results,
            "visualization_config": result.get("visualization_config"),
            "insight": result.get("insight"),
            "recommendation": result.get("recommendation"),
            "original_query": mission["query"],
            "depth": mission.get("depth", 0),
            "parent_mission_id": mission.get("parent_mission_id"),
            "rationale": mission.get("rationale", ""),
            "timestamp": "LIVE AUDIT",
            "logs": log_buf,
        }
    except Exception as e:
        logger.error(f"Sentinel Mission {mission['id']} Failed: {str(e)}")
        return {
            "mission_id": mission["id"],
            "mission_name": mission["name"],
            "domain": mission["domain"],
            "severity": mission.get("severity", "MEDIUM"),
            "risk_score": 0,
            "risk_factors": {},
            "error": str(e),
            "depth": mission.get("depth", 0),
            "parent_mission_id": mission.get("parent_mission_id"),
            "data_count": 0,
            "results": [],
            "logs": log_buf,
        }
    finally:
        _mission_log_buffer.set(None)


# ─── Background scan runner (event-driven) ──────────────────────────────────

async def _run_scan_background(scan_id: str):
    """Run the full Sentinel pipeline as a background task, updating Redis."""
    try:
        all_results: list[dict] = []
        base = {"scan_id": scan_id, "status": "running"}

        # ── Phase 1: Brainstorm ──────────────────────────────────────────
        logger.info(f"[{scan_id}] Phase 1: Brainstorming...")
        _update_progress(scan_id, {
            **base, "phase": "brainstorming",
            "progress": {"completed": 0, "total": 0},
            "missions": [], "detections": [], "clusters": [],
            "narrative": None, "adaptive_context": None,
        })

        missions = await brainstormer.brainstorm_missions(count_per_domain=2)
        if not missions:
            logger.warning(f"[{scan_id}] Brainstorm failed, using fallback.")
            missions = [
                {"id": "fall-001", "name": "Basic Security Audit",
                 "query": "Show users with risk_level HIGH and account_status ACTIVE",
                 "domain": "security", "severity": "HIGH"},
            ]

        adaptive_ctx = scan_memory.get_adaptive_context()
        mission_plan = [{"id": m["id"], "name": m["name"], "domain": m["domain"]} for m in missions]

        _update_progress(scan_id, {
            **base, "phase": "executing",
            "progress": {"completed": 0, "total": len(missions)},
            "missions": mission_plan, "detections": [],
            "clusters": [], "narrative": None,
            "adaptive_context": {
                "scan_count": adaptive_ctx["scan_count"],
                "domain_weights": adaptive_ctx["domain_weights"],
            },
        })

        # ── Phase 2: Execute missions ────────────────────────────────────
        logger.info(f"[{scan_id}] Phase 2: Executing {len(missions)} missions...")
        queue: asyncio.Queue = asyncio.Queue()

        async def run_and_queue(m):
            result = await run_mission(m)
            await queue.put(result)

        tasks = [asyncio.create_task(run_and_queue(m)) for m in missions]

        completed = 0
        total = len(missions)
        while completed < total:
            result = await queue.get()
            all_results.append(result)
            completed += 1
            asyncio.create_task(notify_slack(result))
            _update_progress(scan_id, {
                **base, "phase": "executing",
                "progress": {"completed": completed, "total": total},
                "missions": mission_plan, "detections": all_results,
                "clusters": [], "narrative": None,
                "adaptive_context": {
                    "scan_count": adaptive_ctx["scan_count"],
                    "domain_weights": adaptive_ctx["domain_weights"],
                },
            })

        await asyncio.gather(*tasks, return_exceptions=True)

        # ── Phase 3: Deep Dive ───────────────────────────────────────────
        if settings.DEEP_DIVE_ENABLED:
            _update_progress(scan_id, {
                **base, "phase": "deep_dive",
                "progress": {"completed": completed, "total": total},
                "missions": mission_plan, "detections": all_results,
                "clusters": [], "narrative": None,
                "adaptive_context": {
                    "scan_count": adaptive_ctx["scan_count"],
                    "domain_weights": adaptive_ctx["domain_weights"],
                },
            })

            deep_dive_missions = []
            for res in list(all_results):
                if await deep_dive_generator.should_deep_dive(res):
                    followups = await deep_dive_generator.generate_followups(res, depth=0)
                    if followups:
                        deep_dive_missions.extend(followups)
                        total += len(followups)

            if deep_dive_missions:
                logger.info(f"[{scan_id}] Phase 3: Running {len(deep_dive_missions)} deep-dive follow-ups...")
                dd_queue: asyncio.Queue = asyncio.Queue()

                async def run_dd(m):
                    r = await run_mission(m)
                    await dd_queue.put(r)

                dd_tasks = [asyncio.create_task(run_dd(m)) for m in deep_dive_missions]

                dd_completed = 0
                while dd_completed < len(deep_dive_missions):
                    result = await dd_queue.get()
                    all_results.append(result)
                    completed += 1
                    dd_completed += 1
                    asyncio.create_task(notify_slack(result))
                    _update_progress(scan_id, {
                        **base, "phase": "deep_dive",
                        "progress": {"completed": completed, "total": total},
                        "missions": mission_plan, "detections": all_results,
                        "clusters": [], "narrative": None,
                        "adaptive_context": {
                            "scan_count": adaptive_ctx["scan_count"],
                            "domain_weights": adaptive_ctx["domain_weights"],
                        },
                    })

                await asyncio.gather(*dd_tasks, return_exceptions=True)

        # ── Phase 4: Cross-Domain Correlation ────────────────────────────
        clusters: list = []
        if settings.CORRELATION_ENABLED:
            logger.info(f"[{scan_id}] Phase 4: Running cross-domain correlation...")
            _update_progress(scan_id, {
                **base, "phase": "correlating",
                "progress": {"completed": completed, "total": total},
                "missions": mission_plan, "detections": all_results,
                "clusters": [], "narrative": None,
                "adaptive_context": {
                    "scan_count": adaptive_ctx["scan_count"],
                    "domain_weights": adaptive_ctx["domain_weights"],
                },
            })
            clusters = await correlation_engine.correlate(all_results)

        # ── Phase 5: Executive Intelligence Brief ────────────────────────
        logger.info(f"[{scan_id}] Phase 5: Generating intelligence brief...")
        _update_progress(scan_id, {
            **base, "phase": "briefing",
            "progress": {"completed": completed, "total": total},
            "missions": mission_plan, "detections": all_results,
            "clusters": clusters, "narrative": None,
            "adaptive_context": {
                "scan_count": adaptive_ctx["scan_count"],
                "domain_weights": adaptive_ctx["domain_weights"],
            },
        })

        narrative = await narrative_generator.generate(
            detections=all_results,
            clusters=clusters,
            scan_metadata={"total_missions": len(all_results), "timestamp": "LIVE"},
        )
        asyncio.create_task(notify_slack_narrative(narrative))

        # ── Phase 6: Persist & mark complete ─────────────────────────────
        logger.info(f"[{scan_id}] Phase 6: Saving results...")
        scan_memory.record_scan(all_results)
        scan_memory.save_full_scan(scan_id, all_results, clusters, narrative)

        _update_progress(scan_id, {
            "scan_id": scan_id, "status": "complete", "phase": "complete",
            "progress": {"completed": completed, "total": total},
            "missions": mission_plan, "detections": all_results,
            "clusters": clusters, "narrative": narrative,
            "adaptive_context": {
                "scan_count": adaptive_ctx["scan_count"],
                "domain_weights": adaptive_ctx["domain_weights"],
            },
        })
        logger.info(f"[{scan_id}] Scan complete. {len(all_results)} detections recorded.")

    except Exception as e:
        logger.error(f"[{scan_id}] Background scan failed: {e}")
        _update_progress(scan_id, {
            "scan_id": scan_id, "status": "failed", "phase": "error",
            "error": str(e),
            "progress": {"completed": 0, "total": 0},
            "missions": [], "detections": [], "clusters": [],
            "narrative": None, "adaptive_context": None,
        })


# ─── Polling-based endpoints (API Gateway friendly) ─────────────────────────

@router.post("/scan/start")
async def start_scan():
    """
    Kick off a Sentinel scan as a background task.
    Returns immediately with a scan_id for polling.
    """
    scan_id = f"scan-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"
    logger.info(f"SENTINEL: Starting background scan {scan_id}")

    # Seed initial progress so the status endpoint works immediately
    _update_progress(scan_id, {
        "scan_id": scan_id, "status": "running", "phase": "brainstorming",
        "progress": {"completed": 0, "total": 0},
        "missions": [], "detections": [], "clusters": [],
        "narrative": None, "adaptive_context": None,
    })

    # Fire and forget the background task
    asyncio.create_task(_run_scan_background(scan_id))

    return {"scan_id": scan_id, "status": "running"}


@router.get("/scan/status/{scan_id}")
async def get_scan_status(scan_id: str):
    """
    Poll the current status of a running or completed scan.
    Returns progress, detections so far, and final results when complete.
    """
    # 1) Check active progress in Redis
    progress = _read_progress(scan_id)
    if progress is not None:
        return progress

    # 2) Fallback: check if it's a completed historical scan
    data = scan_memory.get_scan(scan_id)
    if data is not None:
        return {
            "scan_id": scan_id,
            "status": "complete",
            "phase": "complete",
            "progress": {
                "completed": data.get("stats", {}).get("total_missions", 0),
                "total": data.get("stats", {}).get("total_missions", 0),
            },
            "missions": [],
            "detections": data.get("detections", []),
            "clusters": data.get("clusters", []),
            "narrative": data.get("narrative"),
            "adaptive_context": None,
        }

    raise HTTPException(status_code=404, detail="Scan not found")


# ─── Original non-streaming endpoint (backward compatible) ──────────────────

@router.get("/scan")
async def run_sentinel_scan():
    """
    Original Sentinel scan — returns all results at once.
    Kept for backward compatibility.
    """
    logger.info("SENTINEL: Running non-streaming scan...")

    missions = await brainstormer.brainstorm_missions(count_per_domain=2)
    if not missions:
        missions = [
            {"id": "fall-001", "name": "Basic Security Audit",
             "query": "Show users with risk_level HIGH and account_status ACTIVE",
             "domain": "security", "severity": "HIGH"},
        ]

    tasks = [run_mission(m) for m in missions]
    results = await asyncio.gather(*tasks)

    for r in results:
        asyncio.create_task(notify_slack(r))

    results_list = list(results)
    scan_memory.record_scan(results_list)
    scan_id = f"scan-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"
    scan_memory.save_full_scan(scan_id, results_list)

    return {"status": "success", "detections": results_list}


# ─── Scan History Endpoints ─────────────────────────────────────────────────

@router.get("/history")
async def list_scan_history():
    """Return metadata for all persisted scans, newest first."""
    scans = scan_memory.list_scans()
    return {"scans": scans}


@router.get("/history/{scan_id}")
async def get_scan_history(scan_id: str):
    """Return full scan data for a specific scan ID."""
    data = scan_memory.get_scan(scan_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return data


# ─── SSE formatting helper (kept for backward compat) ───────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
