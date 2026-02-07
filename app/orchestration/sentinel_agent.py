from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from app.core.config import settings
import json

class SentinelBrainstormer:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=settings.DISCOVERY_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.8
        )
        
        self.schema_context = """
        ACTUAL TABLES:
        - users (user_id, username, age, kyc_status, risk_level, risk_score, is_pep, account_status)
        - transactions (txn_id, user_id, txn_type, instrument, amount, currency, amount_usd, status, flag_reason, payment_method)
        - login_events (event_id, user_id, email_attempted, status, country, city, device_type, failure_reason)
        """

    async def brainstorm_missions(self, count_per_domain=2):
        prompt = ChatPromptTemplate.from_template("""
            You are the "Sentinel Brain", an autonomous security and compliance agent for a financial platform.
            Your task is to brainstorm dynamic, high-impact "Deep Audit Missions" based on the database schema.
            
            SCHEMA:
            {schema}
            
            DOMAINS:
            1. security: Focus on threats, fraud, unusual logins, and account takeovers.
            2. compliance: Focus on regulatory violations, KYC gaps, PEP monitoring, and anti-money laundering (AML).
            3. operations: Focus on payment failures, system health, and user performance.
            4. risk: Focus on high-risk user exposure and portfolio imbalances.
            
            GOAL:
            Generate a list of {total_count} distinct audit questions (missions).
            The questions should be sophisticated, seeking hidden patterns or critical risks.
            
            RESPONSE FORMAT:
            Provide ONLY a JSON list of objects:
            [
                {{
                    "id": "unique_string",
                    "name": "Short Mission Name",
                    "query": "The natural language question for the AI to solve",
                    "domain": "one of the domains above",
                    "severity": "CRITICAL, HIGH, or MEDIUM"
                }}
            ]
        """)
        
        chain = prompt | self.llm
        total_count = count_per_domain * 4
        response = await chain.ainvoke({
            "schema": self.schema_context,
            "total_count": total_count
        })
        
        try:
            # Clean response text if it has markdown blocks
            text = response.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            return json.loads(text)
        except Exception as e:
            print(f"Failed to parse brainstormed missions: {e}")
            return []
