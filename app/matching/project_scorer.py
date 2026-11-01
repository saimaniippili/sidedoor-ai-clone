from typing import List, Tuple, Optional
from app.matching.project_registry import VerifiedProject, list_all_projects

class ProjectScorer:
    """Deterministic candidate-to-company project scoring engine.
    R = 0.35D + 0.30K + 0.15T + 0.10E + 0.10I
    Where:
      D = Domain relevance
      K = Capability overlap
      T = Technology overlap
      E = Evidence strength (portfolio/status)
      I = Implementation completeness
    """
    
    # Controlled domain synonyms and semantic affinities
    DOMAIN_TAXONOMY = {
        "fraud_detection": ["fraud", "risk", "anomaly", "cybersecurity", "security", "threat", "trust", "verification", "compliance", "fake"],
        "data_analytics": ["analytics", "bi", "business intelligence", "dashboard", "reporting", "visualization", "pandas", "data pipeline", "attribution", "metrics"],
        "nlp": ["nlp", "text", "language", "sentiment", "speech", "llm", "search", "token", "parsing", "information extraction"],
        "rag": ["rag", "retrieval", "vector", "embeddings", "knowledge base", "document search", "semantic search"],
        "recruiting_tech": ["hiring", "recruiting", "talent", "hr", "candidate", "job", "staffing"],
        "healthcare_tech": ["health", "medical", "clinical", "patient", "pharma", "biotech"],
        "content_moderation": ["moderation", "toxic", "content safety", "brand safety", "compliance"],
        "llm_apps": ["genai", "generative ai", "copilot", "assistant", "agent", "llm", "chatbot", "prompt"],
        "agentic_systems": ["agent", "agentic", "autonomous", "workflow", "automation", "orchestration", "multi-agent", "action", "pipeline"],
        "computer_vision": ["computer vision", "vision", "image", "video", "detection", "segmentation", "opencv", "visual", "inspection", "camera"],
        "full_stack": ["backend", "api", "fastapi", "flask", "docker", "cloud", "database", "postgres", "redis", "rest"]
    }
    
    @classmethod
    def score_project(cls, project: VerifiedProject, company_text: str, role_title: str) -> Tuple[float, List[str]]:
        text_lower = f"{company_text} {role_title}".lower()
        matched_signals = []
        
        # 1. Domain relevance (0.0 to 1.0)
        domain_hits = 0
        for domain in project.domains:
            keywords = cls.DOMAIN_TAXONOMY.get(domain, [domain])
            for kw in keywords:
                if kw in text_lower:
                    domain_hits += 1
                    matched_signals.append(f"Domain overlap: {kw}")
                    break
        D = min(1.0, domain_hits / max(1, len(project.domains) * 0.5))
        
        # 2. Capability overlap (0.0 to 1.0)
        cap_hits = 0
        for cap in project.capabilities:
            words = [w.lower() for w in cap.split() if len(w) > 3]
            for w in words:
                if w in text_lower:
                    cap_hits += 1
                    matched_signals.append(f"Capability: {w}")
                    break
        K = min(1.0, cap_hits / max(1, len(project.capabilities)))
        
        # 3. Technology overlap (0.0 to 1.0)
        tech_hits = 0
        for tech in project.technologies:
            if tech.lower() in text_lower:
                tech_hits += 1
                matched_signals.append(f"Tech: {tech}")
        T = min(1.0, tech_hits / 3.0)
        
        # 4. Evidence strength
        E = 1.0 if project.evidence_notes else 0.7
        
        # 5. Implementation status
        I = 1.0 if project.implementation_status == "Implemented" else 0.5
        
        R = 0.35 * D + 0.30 * K + 0.15 * T + 0.10 * E + 0.10 * I
        return round(R, 3), list(set(matched_signals))
    
    @classmethod
    def select_best_projects(cls, company_text: str, role_title: str, max_projects: int = 2, candidate_projects: Optional[List[VerifiedProject]] = None) -> List[Tuple[VerifiedProject, float, List[str]]]:
        scored = []
        pool = candidate_projects if candidate_projects else list_all_projects()
        for project in pool:
            score, signals = cls.score_project(project, company_text, role_title)
            scored.append((project, score, signals))
        
        # Rank descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:max_projects]
