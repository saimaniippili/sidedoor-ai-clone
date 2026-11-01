from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class VerifiedProject(BaseModel):
    project_id: str
    name: str
    summary: str
    domains: List[str] # e.g. ["nlp", "text_classification", "fraud_detection", "data_engineering"]
    capabilities: List[str] # e.g. ["RAG pipelines", "Local LLM inference", "EDA & dynamic charting"]
    technologies: List[str] # e.g. ["Python", "LangChain", "Ollama", "Pandas", "Scikit-Learn"]
    implemented_features: List[str]
    verifiable_accomplishments: str
    implementation_status: str = "Implemented" # Implemented, Partially implemented, In progress
    evidence_notes: str

# Concrete Project Registry strictly derived from Saimani Ippili's verified resume
PROJECT_REGISTRY: Dict[str, VerifiedProject] = {
    "sidedoor_ai_agent": VerifiedProject(
        project_id="sidedoor_ai_agent",
        name="Sidedoor: Autonomous AI Job Search Agent",
        summary="An end-to-end autonomous agentic system engineered to scout, research, verify, and match early-stage tech startup founders. Features multi-tier DNS-over-HTTPS MX deliverability validation (Zero Bounces standard), neural search entity extraction via Exa API, dynamic multi-modal LLM routing, Telegram bot command and notification interface, and automated Gmail outreach workflows.",
        domains=["genai", "llm_apps", "agentic_systems", "autonomous_agents", "recruiting_tech", "data_engineering", "full_stack"],
        capabilities=[
            "Autonomous agentic pipeline discovering and evaluating technical startups",
            "Multi-tier deliverability gatekeeper with DNS-over-HTTPS MX resolution and Zero Bounces validation",
            "LLM intelligence routing for real-time leadership extraction, company technical profiling, and personalized outreach",
            "Telegram bot asynchronous webhook & polling controller for real-time human-in-the-loop candidate approvals",
            "Gmail API integration with automated Day 3 / Day 7 follow-up sequence reconciliation"
        ],
        technologies=["Python", "FastAPI", "Exa AI", "PostgreSQL", "LangChain", "Telegram API", "Gmail API", "Docker", "LLM Agents"],
        implemented_features=[
            "Multi-tier founder email discovery and DNS MX verification preventing bounces",
            "Autonomous 24/7 background scheduler delivering structured startup matches and candidate pitches",
            "Dynamic candidate portfolio matching combining resume evidence and public GitHub projects"
        ],
        verifiable_accomplishments="Engineered end-to-end agentic workflow delivering high-accuracy founder discovery and verified outreach with 0% bounce rate.",
        implementation_status="Implemented",
        evidence_notes="Live production autonomous agent deployed on Render and connected to Telegram and Gmail."
    ),
    "datachat": VerifiedProject(
        project_id="datachat",
        name="DataChat: Conversational Data Analysis Tool",
        summary="A full-stack conversational data analytics application enabling natural language querying and dynamic charting on CSV/Excel files using LangChain agents and local LLMs via Ollama.",
        domains=["data_analytics", "llm_apps", "rag", "natural_language_to_sql_or_pandas", "full_stack"],
        capabilities=[
            "Natural language querying of tabular CSV and Excel datasets",
            "Dynamic chart and statistical distribution generation",
            "Modular LangChain tool architecture connecting LLM inference to Pandas operations"
        ],
        technologies=["Python", "LangChain", "Ollama", "Llama3", "Mistral", "Pandas", "JavaScript", "Flask"],
        implemented_features=[
            "Dynamic histogram and summary statistics generation without manual SQL or code",
            "Local LLM runtime integration via Ollama for multi-model selection (2B to 8B parameter models)"
        ],
        verifiable_accomplishments="Built end-to-end tool allowing non-technical users to execute complex analytical queries across datasets naturally.",
        implementation_status="Implemented",
        evidence_notes="Documented in candidate B.Tech portfolio and resume."
    ),
    "fake_job_detection": VerifiedProject(
        project_id="fake_job_detection",
        name="Fake Job Postings Classification System",
        summary="An NLP and machine learning pipeline that classifies fraudulent vs. legitimate job postings using text preprocessing, TF-IDF feature extraction, and supervised classification models hitting 90% accuracy.",
        domains=["nlp", "fraud_detection", "text_classification", "machine_learning", "recruiting_tech"],
        capabilities=[
            "Text normalization, stop-word removal, and TF-IDF feature representation",
            "Imbalanced dataset handling using SMOTE",
            "Supervised binary classification reaching 90% validation accuracy"
        ],
        technologies=["Python", "Scikit-learn", "TF-IDF", "Logistic Regression", "Random Forest", "SMOTE"],
        implemented_features=[
            "Data preprocessing pipeline handling dirty real-world text corpora",
            "Multi-model benchmark comparing Logistic Regression vs Random Forest vs SVM"
        ],
        verifiable_accomplishments="Achieved 90% classification accuracy on imbalanced recruitment dataset.",
        implementation_status="Implemented",
        evidence_notes="Resume verified project for data science & NLP."
    ),
    "medsage_healthcare_chatbot": VerifiedProject(
        project_id="medsage_healthcare_chatbot",
        name="MedSage: AI Healthcare Assistant",
        summary="An AI-powered conversational healthcare assistant utilizing RAG pipelines, local vector embeddings, and domain-constrained medical QA.",
        domains=["genai", "rag", "healthcare_tech", "vector_search"],
        capabilities=[
            "RAG (Retrieval-Augmented Generation) pipeline over medical documents",
            "Vector search embeddings and contextual response generation"
        ],
        technologies=["Python", "LangChain", "Vector Search", "Ollama", "RAG"],
        implemented_features=[
            "Document chunking and semantic vector similarity retrieval",
            "Hallucination guardrails ensuring answers stay strictly grounded in retrieved evidence"
        ],
        verifiable_accomplishments="Engineered grounded retrieval pipeline preventing hallucinations on domain-specific medical documents.",
        implementation_status="Implemented",
        evidence_notes="Candidate resume verified project."
    ),
    "toxic_comment_classifier": VerifiedProject(
        project_id="toxic_comment_classifier",
        name="Toxic Comment & Content Moderation Classifier",
        summary="A text classification engine for identifying toxic language and cyber-harassment in user-generated content.",
        domains=["nlp", "content_moderation", "cybersecurity", "text_classification"],
        capabilities=[
            "Multi-label toxic text classification",
            "Real-time text scoring API integration"
        ],
        technologies=["Python", "Scikit-Learn", "TF-IDF", "Flask"],
        implemented_features=[
            "Feature vectorization pipeline for social media and comment streams",
            "REST API endpoint for real-time toxicity scoring"
        ],
        verifiable_accomplishments="Built fast text scoring engine suitable for moderation microservices.",
        implementation_status="Implemented",
        evidence_notes="Verified coursework and portfolio repository."
    )
}

def get_project(project_id: str) -> Optional[VerifiedProject]:
    return PROJECT_REGISTRY.get(project_id)

def list_all_projects() -> List[VerifiedProject]:
    return list(PROJECT_REGISTRY.values())
