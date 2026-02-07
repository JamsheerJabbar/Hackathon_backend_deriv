import asyncio
import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

from app.orchestration.workflow import app_graph

async def verify_demo_questions():
    print("Verifying Hackathon Demo Questions...")
    
    test_cases = [
        {
            "domain": "security",
            "query": "Show me all failed logins from the last week including failure reason, ip_address and username."
        },
        {
            "domain": "compliance",
            "query": "Show me all transactions greater than $10,000 made by users who are flagged as PEP (Politically Exposed Person)."
        },
        {
            "domain": "risk",
            "query": "Calculate the total transaction amount in USD for users grouped by their risk_level."
        },
        {
            "domain": "operations",
            "query": "What is the success rate of transactions broken down by payment method?"
        }
    ]
    
    final_report = []

    for case in test_cases:
        print(f"\nTESTING [{case['domain'].upper()}]: {case['query']}")
        initial_state = {
            "user_question": case["query"],
            "domain": case["domain"],
            "conversation_history": [],
            "retry_count": 0
        }
        
        try:
            result = await app_graph.ainvoke(initial_state)
            
            report_entry = {
                "domain": case["domain"],
                "query": case["query"],
                "status": result.get("status"),
                "sql": result.get("generated_sql"),
                "insight": result.get("insight"),
                "recommendation": result.get("recommendation"),
                "has_results": len(result.get("query_result", [])) > 0 if result.get("query_result") else False
            }
            final_report.append(report_entry)
            print(f"Result Status: {result.get('status')}")
            if result.get("status") == "success":
                print(f"SQL Generated: {result.get('generated_sql')[:100]}...")
            else:
                print(f"FAIL/CLARIFY: {result.get('clarification_question')}")
                
        except Exception as e:
            print(f"ERROR: {e}")

    with open("verification_report.json", "w") as f:
        json.dump(final_report, f, indent=2)
    
    print("\nVerification complete. Report saved to verification_report.json")

if __name__ == "__main__":
    asyncio.run(verify_demo_questions())
