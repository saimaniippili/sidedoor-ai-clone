import re
import json
import base64
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from app.matching.project_registry import VerifiedProject

GITHUB_USERNAME = "saimaniippili"
CACHE_EXPIRY_SECONDS = 3600  # 1 hour cache

# In-memory cache to avoid rate limits
_GITHUB_PROJECTS_CACHE: List[VerifiedProject] = []
_LAST_SYNC_TIME: float = 0.0

# Tech keyword patterns for auto-tagging
TECH_MAP = {
    "python": "Python",
    "langchain": "LangChain",
    "ollama": "Ollama",
    "rag": "RAG",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "docker": "Docker",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "scikit-learn": "Scikit-Learn",
    "sklearn": "Scikit-Learn",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "opencv": "OpenCV",
    "react": "React",
    "three.js": "Three.js",
    "threejs": "Three.js",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "telegram": "Telegram API",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "nlp": "NLP",
    "llm": "LLMs",
    "generative ai": "Generative AI",
    "genai": "GenAI"
}

DOMAIN_MAP = {
    "ai": "genai",
    "llm": "llm_apps",
    "rag": "rag",
    "chat": "conversational_ai",
    "agent": "agentic_systems",
    "vision": "computer_vision",
    "health": "healthcare_tech",
    "medical": "healthcare_tech",
    "fraud": "fraud_detection",
    "security": "cybersecurity",
    "data": "data_analytics",
    "analytics": "data_analytics",
    "dashboard": "business_intelligence",
    "portfolio": "full_stack",
    "web": "web_development"
}

EXCLUDED_REPOS = {
    "github-profile", "saimaniippili.github.io", "saimani_portfolio",
    "2200031044_jfsd_semend_exam", "prodigy_wd_01", "prodigy_wd_02",
    "prodigy_wd_03", "prodigy_wd_04", "prodigy_wd_05"
}


class GitHubProjectService:
    """Fetches, parses, and converts public GitHub repositories and their README files
    into VerifiedProject objects for seamless multi-source matching.
    """

    @classmethod
    async def get_github_projects(cls, force_refresh: bool = False) -> List[VerifiedProject]:
        global _GITHUB_PROJECTS_CACHE, _LAST_SYNC_TIME
        import time
        now = time.time()

        if _GITHUB_PROJECTS_CACHE and not force_refresh and (now - _LAST_SYNC_TIME < CACHE_EXPIRY_SECONDS):
            return _GITHUB_PROJECTS_CACHE

        headers = {
            "User-Agent": "Sidedoor-Agent/1.0",
            "Accept": "application/vnd.github.v3+json"
        }

        projects: List[VerifiedProject] = []
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?per_page=50&sort=updated"
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f"[GitHubService] Failed to fetch repos (HTTP {resp.status_code})", flush=True)
                    return _GITHUB_PROJECTS_CACHE

                repos = resp.json()
                for repo in repos:
                    if repo.get("fork"):
                        continue
                    name = repo.get("name", "")
                    if name.lower() in EXCLUDED_REPOS:
                        continue

                    # STARRED FILTER: Only include repositories you have explicitly starred (starred >= 1)
                    # All unstarred repositories are automatically ignored.
                    stargazers = repo.get("stargazers_count", 0)
                    if stargazers < 1:
                        continue

                    # Fetch README for rich context
                    readme_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{name}/readme"
                    readme_text = ""
                    try:
                        r_resp = await client.get(readme_url)
                        if r_resp.status_code == 200:
                            content_b64 = r_resp.json().get("content", "")
                            readme_text = base64.b64decode(content_b64).decode("utf-8", errors="ignore")
                    except Exception:
                        pass

                    desc = repo.get("description") or ""
                    lang = repo.get("language") or ""
                    html_url = repo.get("html_url") or f"https://github.com/{GITHUB_USERNAME}/{name}"

                    # Clean markdown to get readable summary
                    clean_readme = re.sub(r"[#*`\[\]!_]", " ", readme_text)
                    clean_readme = " ".join(clean_readme.split())
                    
                    summary = desc
                    if not summary or len(summary) < 20:
                        # Extract first 2 meaningful sentences from README
                        sentences = [s.strip() for s in clean_readme.split(".") if len(s.strip()) > 20]
                        summary = ". ".join(sentences[:2]) if sentences else f"Open-source {lang} project on GitHub."

                    # Extract technologies
                    combined_text = f"{name} {desc} {lang} {readme_text}".lower()
                    technologies = []
                    if lang and lang not in technologies:
                        technologies.append(lang)
                    for k, v in TECH_MAP.items():
                        if k in combined_text and v not in technologies:
                            technologies.append(v)

                    # Extract domains
                    domains = []
                    for k, v in DOMAIN_MAP.items():
                        if k in combined_text and v not in domains:
                            domains.append(v)
                    if not domains:
                        domains = ["software_engineering", "open_source"]

                    # Extract capabilities / features
                    capabilities = [
                        f"Open-source implementation hosted at {html_url}",
                        f"Architected with {', '.join(technologies[:3]) if technologies else lang}"
                    ]

                    # Clean display name
                    display_name = name.replace("-", " ").replace("_", " ").title()

                    vp = VerifiedProject(
                        project_id=f"gh_{name.lower().replace('-', '_')}",
                        name=f"{display_name} (GitHub: {name})",
                        summary=f"{summary} | Repository: {html_url}",
                        domains=domains,
                        capabilities=capabilities,
                        technologies=technologies[:6] if technologies else ["Python"],
                        implemented_features=[
                            f"Live public repository: {html_url}",
                            f"Documented technical specifications in README"
                        ],
                        verifiable_accomplishments=f"Open-source implementation with complete documentation on GitHub at {html_url}",
                        implementation_status="Implemented",
                        evidence_notes=f"Verified directly from public GitHub repository {html_url}"
                    )
                    projects.append(vp)

                print(f"[GitHubService] Successfully indexed {len(projects)} active GitHub projects for {GITHUB_USERNAME}.", flush=True)
                _GITHUB_PROJECTS_CACHE = projects
                _LAST_SYNC_TIME = now
                return projects
        except Exception as e:
            print(f"[GitHubService] Error syncing GitHub repositories: {e}", flush=True)
            return _GITHUB_PROJECTS_CACHE
