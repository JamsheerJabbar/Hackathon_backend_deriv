import asyncio
import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

from app.orchestration.workflow import app_graph

async def final_verification():
    print("🚀 Running Final Hackathon Question Verification...\n")
    
    questions = [
        {"domain": "operations", "query": "What is the total transaction volume in USD for each user?"},
        {"domain": "operations", "query": "What is the distribution of transaction statuses across the platform?"},
        {"domain": "risk", "query": "Show me all users and their risk levels."},
        {"domain": "security", "query": "Show me failed login attempts including the failure reason and IP address."},
        {"domain": "compliance", "query": "How many users are flagged as Politically Exposed Persons (PEP)?"},
        {"domain": "compliance", "query": "List all transactions that are currently in 'FLAGGED' status."},
        {"domain": "operations", "query": "Which countries have the highest number of active users?"},
        {"domain": "operations", "query": "Show the average transaction amount for each payment method."}
    ]
    
    success_count = 0
    results_log = []

    for i, q in enumerate(questions, 1):
        print(f"[{i}/8] Testing: {q['query']}")
        state = {
            "user_question": q["query"],
            "domain": q["domain"],
            "conversation_history": [],
            "retry_count": 0
        }
        
        try:
            result = await app_graph.ainvoke(state)
            
            status = result.get("status")
            insight = result.get("insight")
            rec = result.get("recommendation")
            sql = result.get("generated_sql")
            
            is_valid = status == "success" and insight is not None and rec is not None
            
            if is_valid:
                success_count += 1
                print(f"   ✅ SUCCESS")
            else:
                print(f"   ❌ FAILED (Status: {status}, Insight: {'OK' if insight else 'None'}, Rec: {'OK' if rec else 'None'})")

            results_log.append({
                "query": q["query"],
                "status": status,
                "sql": sql,
                "insight": insight,
                "recommendation": rec
            })
                
        except Exception as e:
            print(f"   💥 ERROR: {e}")

    print(f"\nVerification Finished: {success_count}/8 passed.")
    
    with open("final_demo_results.json", "w") as f:
        json.dump(results_log, f, indent=2)
    print("Detailed log saved to final_demo_results.json")

if __name__ == "__main__":
    asyncio.run(final_verification())
