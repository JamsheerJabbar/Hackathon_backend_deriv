# 🦅 InsightOS: The Virtual CIO for Real-Time Financial Intelligence

[![Demo Verification](https://img.shields.io/badge/Demo-Verified_100%25-brightgreen.svg)]()
[![Orchestration](https://img.shields.io/badge/Orchestration-LangGraph-blue.svg)]()
[![Intelligence](https://img.shields.io/badge/Engine-Gemini_2.5_Flash-orange.svg)]()

> **InsightOS** transforms complex natural language into actionable executive-level business intelligence. It’s not just an NL2SQL tool; it’s an AI-driven decision engine that reasons across your entire database to provide strategic recommendations.

---

## 🏗️ System Architecture

Our engine utilizes a **Multi-Agent Orchestration Flow** powered by **LangGraph**. This ensures every natural language request is not just translated, but validated, executed, and synthesized into strategic advice.

```mermaid
graph TD
    subgraph Client ["Interface"]
        A([Executive Query]) --> B[FastAPI Endpoint]
    end

    subgraph NL2SQL_Pipeline ["NL2SQL Orchestration Layer (LangGraph)"]
        B --> C[Intent Classifier & Domain Router]
        
        %% Domain Logic
        C -.-> |Domains| D{Operations | Risk | Security | Compliance}
        D -.-> |Inject Context| E[Schema & Few-Shot Retriever]
        
        E --> F[SQL Generation Agent]
        F --> G{SQL Validator}
        
        %% Self-Repair Loop
        G -- "Invalid" --> H[Self-Repair Node]
        H -- "Retry with Error" --> F
        
        G -- "Success" --> I[Secure Query Execution]
    end

    subgraph Reasoning ["The Virtual CIO Engine"]
        I --> J[Visualization Discovery]
        J --> K[Executive Insight Generator]
        K --> L[Strategic Recommendation Engine]
    end

    L --> M([Final Executive Briefing])
    M --> B

    %% Styling
    style A fill:#f9f,stroke:#333,stroke-width:2px
    style C fill:#6b5b95,stroke:#fff,color:#fff
    style F fill:#f96,stroke:#333
    style G fill:#feb236,stroke:#333
    style I fill:#d64161,stroke:#fff,color:#fff
    style L fill:#00d2ff,stroke:#333,stroke-width:2px
    style M fill:#3ff,stroke:#333,stroke-width:4px
```

---

### **Pipeline Breakdown**
1.  **Intent Classifier & Domain Router**: Determines the request type (Selection, Aggregation, Comparison) and maps it to one of our target domains: **Operations**, **Risk**, **Security**, or **Compliance**.
2.  **Few-Shot Retriever**: Pulls domain-specific SQLite examples and schema metadata to provide "in-context learning" for the LLM.
3.  **Self-Healing Logic**: If a generated SQL query fails validation or execution, the system captures the SQLite error, analyzes it, and performs a "hot-fix" to ensure continuity.
4.  **Virtual CIO Node**: Instead of returning raw JSON, the final stage synthesizes data into human-readable **Insights** (what happened) and **Recommendations** (what to do next).

---

## ✨ Key Features

### 🧠 Strategic Synthesis (CIO Reasoning)
Unlike standard query tools, InsightOS doesn't just return tables. It analyzes trends and provides two-step actionable advice for every result.
*   *Example:* "We detected a 25% failure rate in Japanese logins. **Recommendation:** Audit the Tokyo gateway and implement adaptive MFA."

### 🛡️ Multi-Domain Expertise
InsightOS has specialized intelligence nodes for:
*   **Operations:** Transaction volumes, volumes-by-country, and payment method efficiency.
*   **Risk:** Real-time identification of 'Critical' and 'High' risk user profiles.
*   **Compliance:** PEP tracking, AML alerts, and Sanctions matching.
*   **Security:** Failed login patterns and brute-force detection.

### ⚡ Self-Healing SQL Pipeline
High-precision SQL generation powered by Gemini with a feedback loop that automatically repairs queries if execution fails.

---

## 🚀 Getting Started

### 1. Prerequisite Setup
```bash
python -m venv venv
./venv/Scripts/activate  # Windows
pip install -r requirements.txt
```

### 2. Environment Variables
Create a `.env` file with your credentials:
```env
GOOGLE_API_KEY=your_gemini_key
REDIS_URL=optional_for_alerts
DB_PATH=./derivinsightnew.db
```

### 3. Launch the Backend
```bash
python -m uvicorn app.main:app --reload --port 8080
```

---

## 💎 Demo Verification (Try These Queries)

InsightOS is stress-tested and verified for the following high-value executive questions:

| Category | Question | Value Proposition |
| :--- | :--- | :--- |
| **Growth** | *"Which countries have the highest number of active users?"* | Strategic Market Analysis |
| **Risk** | *"Show me all users and their risk levels."* | Exposure Management |
| **Ops** | *"What is the distribution of transaction statuses?"* | Processing Efficiency |
| **Fraud** | *"List all transactions in 'FLAGGED' status."* | AML Compliance |
| **Security** | *"Show me failed logins by failure reason and IP."* | Threat Intelligence |

---

## 🛠️ Tech Stack
*   **Orchestration:** [LangGraph](https://www.langchain.com/langgraph)
*   **Intelligence:** [Google Gemini 2.5 Flash / 3-Flash-Preview](https://deepmind.google/technologies/gemini/)
*   **API:** [FastAPI](https://fastapi.tiangolo.com/)
*   **Database:** SQLAlchemy / SQLite
*   **Frontend:** Vanilla JS / HTML5 (optimized for real-time dashboards)

---

Developed for the **Deriv Hackathon** – *Empowering Executives with Data-First Decisioning.*
