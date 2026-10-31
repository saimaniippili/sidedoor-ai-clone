from typing import Dict, Any, Tuple
from app.matching.project_registry import VerifiedProject

class OutreachFrameworkSelector:
    """Selects one of 4 proven cold email outreach frameworks:
    1. PAIN_POINT: Documented engineering requirement / challenge observed
    2. PRODUCT_ANALYSIS: Deep observation about an existing public artifact/tool
    3. PROOF_OF_WORK: High technical relevance project demonstration
    4. CASUAL_INTRODUCTION: Early-stage introduction with verified interest
    or NOT_TO_SEND if relevance is below safety thresholds.
    """
    
    @classmethod
    def select_framework(
        cls,
        company_name: str,
        company_description: str,
        best_project: VerifiedProject,
        match_score: float,
        has_specific_tech_challenge: bool = False,
        has_public_product_artifact: bool = False
    ) -> Tuple[str, str]:
        
        # Guardrail: If project relevance is near-zero, do not send cold spam
        if match_score < 0.25:
            return "NOT_TO_SEND", "Relevance score between candidate portfolio and company is below threshold (0.25)."
        
        if has_specific_tech_challenge and match_score >= 0.50:
            return "PAIN_POINT", f"Documented technical signal in {best_project.domains[0]} aligned with candidate capabilities."
        
        if has_public_product_artifact and match_score >= 0.45:
            return "PRODUCT_ANALYSIS", f"Public product artifact observed aligning with candidate's practical tool building experience."
            
        if match_score >= 0.35:
            return "PROOF_OF_WORK", f"Direct proof of work available via candidate's verified project '{best_project.name}'."
            
        return "CASUAL_INTRODUCTION", "Target company is an early-stage startup in target geography; general engineering introduction."

    @classmethod
    def get_framework_instructions(cls, framework: str) -> str:
        instructions = {
            "PAIN_POINT": """
Framework: PAIN_POINT
Structure:
1. One precise, verified observation about the company's real engineering challenge or architecture.
2. Directly bridge to how you tackled a similar problem in your verified project.
3. Explicitly name-drop the project and actual technical stack used.
4. One low-friction question (e.g. 15-minute sync).
Rules: Do NOT invent bugs, bottlenecks, or internal issues.
""",
            "PRODUCT_ANALYSIS": """
Framework: PRODUCT_ANALYSIS
Structure:
1. Mention the specific public feature, API, or data product the company built.
2. Share a thoughtful, appreciative engineering observation on why that product architecture is compelling.
3. State your hands-on experience building parallel tools, mentioning your specific project by name.
4. One low-friction conversation invitation.
""",
            "PROOF_OF_WORK": """
Framework: PROOF_OF_WORK
Structure:
1. Direct, concise hook on the company's product domain.
2. Highlight your verified project by name: what it does, how it works, and key metrics/capabilities (e.g., 90% accuracy, local LLM Ollama integration).
3. Connect the transferable skill directly to their engineering team.
4. Low-friction ask.
""",
            "CASUAL_INTRODUCTION": """
Framework: CASUAL_INTRODUCTION
Structure:
1. Honest, concise introduction as an AI / ML Engineer at StyloWorld focused on Data Science / ML / AI systems.
2. Highlight genuine interest in their product mission with one verified fact about what they build.
3. Reference your strongest relevant project and skills.
4. Ask if they have open bandwidth for a quick chat or internship/junior engineering role.
"""
        }
        return instructions.get(framework, instructions["CASUAL_INTRODUCTION"])
