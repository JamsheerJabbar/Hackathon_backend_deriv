import asyncio
import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

from app.orchestration.workflow import app_graph

async def test_recommendations_v2():
    print("Verifying Actionable Recommendations...")
    
    # 1. A query that definitely has data
    # 2. A query that has valid SQL but 0 results (to test fallback)
    questions = [
        {
            "id": "Data Found Case",
            "query": "Show me usernames and their risk levels."
        },
        {
            "id": "Empty Data Fallback Case",
            "query": "Show me all transactions with amount greater than 1000000000."
        }
    ]
    
    for q in questions:
        print(f"\n[{q['id']}] Query: {q['query']}")
        state = {
            "user_question": q["query"],
            "domain": "risk",
            "conversation_history": [],
            "retry_count": 0
        }
        
        result = await app_graph.ainvoke(state)
        
        print(f"Status: {result.get('status')}")
        print("-" * 20)
        print("INSIGHT:")
        print(result.get("insight"))
        print("-" * 20)
        print("ACTIONABLE RECOMMENDATION:")
        print(result.get("recommendation"))
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(test_recommendations_v2())
