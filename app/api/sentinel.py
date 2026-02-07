from fastapi import APIRouter
from app.orchestration.workflow import app_graph
from app.core.logger import logger
import asyncio
from app.orchestration.sentinel_agent import SentinelBrainstormer

router = APIRouter()
brainstormer = SentinelBrainstormer()

@router.get("/scan")
async def run_sentinel_scan():
    """
    Autonomous Sentinel Scan:
    Brainstorms dynamic missions using the Sentinel Agent and executes them.
    """
    logger.info("INITIATING DYNAMIC AGENTIC SENTINEL SCAN...")
    
    # 1. Brainstorm dynamic missions based on current schema and business goals
    missions = await brainstormer.brainstorm_missions(count_per_domain=2)
    if not missions:
        logger.warning("Agent failed to brainstorm missions, using fallback.")
        missions = [
            {"id": "fall-001", "name": "Basic Security Audit", "query": "Check for high risk logins", "domain": "security", "severity": "HIGH"}
        ]
    
    # 2. Run missions in parallel
    tasks = [run_mission(m) for m in missions]
    results = await asyncio.gather(*tasks)
    
    return {"status": "success", "detections": results}

async def run_mission(mission):
    """Executes a single brainstormed mission through the NL2SQL graph."""
    initial_state = {
        "user_question": mission["query"],
        "domain": mission["domain"],
        "conversation_history": [],
        "retry_count": 0
    }
    
    try:
        result = await app_graph.ainvoke(initial_state)
        return {
            "mission_id": mission["id"],
            "mission_name": mission["name"],
            "domain": mission["domain"],
            "severity": mission["severity"],
            "sql": result.get("generated_sql"),
            "data_count": len(result.get("query_result", [])) if result.get("query_result") else 0,
            "results": result.get("query_result"),
            "visualization_config": result.get("visualization_config"),
            "insight": result.get("insight"),
            "recommendation": result.get("recommendation"),
            "timestamp": "LIVE AUDIT"
        }
    except Exception as e:
        logger.error(f"Sentinel Mission {mission['id']} Failed: {str(e)}")
        return {
            "mission_id": mission["id"], 
            "mission_name": mission["name"], 
            "domain": mission["domain"],
            "error": str(e)
        }
