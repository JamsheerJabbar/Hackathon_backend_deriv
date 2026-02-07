import asyncio
import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

from app.orchestration.workflow import app_graph

async def test_recommendations():
    print("Testing Recommendation Engine Status...")
    
    questions = [
        {
            "id": "Q1 (Data Available)",
            "domain": "risk",
            "query": "Show me all users and their risk scores."
        },
        {
            "id": "Q2 (Aggregated)",
            "domain": "operations",
            "query": "What is the total transaction volume in USD per day?"
        },
        {
            "id": "Q3 (No Data Case)",
            "domain": "security",
            "query": "Show me users who logged in from Antarctica today."
        }
    ]
    
    for q in questions:
        print(f"\n--- Testing {q['id']} ---")
        print(f"Query: {q['query']}")
        
        state = {
            "user_question": q["query"],
            "domain": q["domain"],
            "conversation_history": [],
            "retry_count": 0
        }
        
        try:
            result = await app_graph.ainvoke(state)
            
            print(f"Status: {result.get('status')}")
            
            insight = result.get("insight")
            rec = result.get("recommendation")
            
            if insight:
                print(f"Insight Found: YES (Length: {len(insight)})")
                # print(f"Preview: {insight[:100]}...")
            else:
                print("Insight Found: NO")
                
            if rec:
                print(f"Recommendation Found: YES (Length: {len(rec)})")
                print(f"Recommendation Text: {rec}")
            else:
                print("Recommendation Found: NO")
                
            if result.get("status") == "success" and rec and len(rec) > 20:
                print(">>> VERIFICATION: PASSED")
            elif not result.get("query_result") and rec == "Try broadening your search criteria or checking if the data for this period is available.":
                print(">>> VERIFICATION: PASSED (Correct fallback for empty data)")
            else:
                print(">>> VERIFICATION: FAILED")
                
        except Exception as e:
            print(f"ERROR executing {q['id']}: {e}")

if __name__ == "__main__":
    asyncio.run(test_recommendations())
