import json
from typing import List, Tuple
from app.intelligence.llm_router import llm_router, OutreachGenerationOutput
from app.outreach.framework_selector import OutreachFrameworkSelector
from app.matching.project_registry import VerifiedProject

class EmailGenerator:
    """Generates personalized cold emails grounded strictly in verified candidate evidence
    and selected strategic frameworks.
    """
    
    @classmethod
    async def generate_initial_draft(
        cls,
        company_name: str,
        company_description: str,
        founder_name: str,
        role_target: str,
        selected_framework: str,
        best_project: VerifiedProject,
        project_signals: List[str],
        candidate_name: str = "Saimani Ippili"
    ) -> Tuple[str, str]:
        
        framework_instructions = OutreachFrameworkSelector.get_framework_instructions(selected_framework)
        
        system_prompt = (
            "You are an expert technical recruiting outreach strategist. You write authentic, "
            "concise, zero-fluff cold emails for an early-career engineer reaching out directly to startup founders or tech leads. "
            "Write strictly like an engineer. Never use corporate marketing fluff, fake praise, or boilerplate buzzwords."
        )
        
        prompt = f"""
Write a high-converting cold email based on these exact verified facts:

TARGET COMPANY: {company_name}
WHAT THEY DO: {company_description}
RECIPIENT NAME: {founder_name}
TARGET ROLE: {role_target}

SELECTED OUTREACH FRAMEWORK:
{framework_instructions}

CANDIDATE'S VERIFIED PROJECT TO HIGHLIGHT:
Name: {best_project.name}
Summary: {best_project.summary}
Key Technologies: {", ".join(best_project.technologies)}
Accomplishment/Metric: {best_project.verifiable_accomplishments}
Relevant Signals Identified: {", ".join(project_signals) if project_signals else "General technical alignment"}

CANDIDATE PROFILE:
Name: {candidate_name}
Background: B.Tech CSE (2026), strong hands-on experience across Python, ML pipelines, LangChain/RAG, and full-stack integration.

MANDATORY STRUCTURE & FORMATTING RULES (DO NOT WRITE A WALL OF TEXT):
1. Format as 3 concise, visually clean paragraphs separated by blank lines:
   - Paragraph 1 (The Hook): 1 sentence showing genuine, specific understanding of what {company_name} is building.
   - Paragraph 2 (Proof of Work): 2 sentences highlighting candidate's verified project ("{best_project.name.split(':')[0]}"): what it does, key technologies ({", ".join(best_project.technologies[:4])}), and key achievement/capability.
   - Paragraph 3 (Call to Action & Portfolio): 1 sentence asking for a quick 15-minute conversation, with candidate's live portfolio attached.
2. Greeting: "Hey {founder_name.split()[0] if founder_name and founder_name.lower() != 'team' else 'Team'},"
3. Length: 75 to 95 words maximum.
4. Truthfulness: Never claim candidate worked at {company_name}.
5. Sign-off: Must include candidate name, role, and portfolio link:
Best,
{candidate_name}
Portfolio: https://personal-portfolio-chi-bay-62.vercel.app/

DO NOT OUTPUT JSON. DO NOT OUTPUT CODE BLOCKS.
Follow this EXACT template structure:

Subject: <Clear, relevant subject line mentioning {role_target} or key tech>

Hey {founder_name.split()[0] if founder_name and founder_name.lower() != 'team' else 'Team'},

<1-sentence observation about {company_name}'s product or technical mission.>

<2-sentence punchy highlight of candidate's project "{best_project.name.split(':')[0]}", tech used, and how it directly maps to this domain.>

<1-sentence asking if they have 15 minutes to chat about potential {role_target} roles.>

Best,
{candidate_name}
Portfolio: https://personal-portfolio-chi-bay-62.vercel.app/
"""
        raw_res = await llm_router.complete(prompt, system_prompt=system_prompt, temperature=0.3)
        import re
        
        text = raw_res.strip()
        
        # Strip any accidental JSON or markdown encapsulation
        if '"body":' in text:
            # Extract subject
            s_match = re.search(r'"subject":\s*"([^"]+)"', text)
            subj = s_match.group(1).strip() if s_match else f"Exploring {role_target} opportunities at {company_name}"
            
            # Extract body
            b_match = re.search(r'"body":\s*"(.*)', text, re.DOTALL)
            if b_match:
                b = b_match.group(1).strip()
                for suffix in ['"}', '"\n}', '"}', '"', '}']:
                    if b.endswith(suffix):
                        b = b[:-len(suffix)].strip()
                b = b.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
                return subj, b
                
        # Handle clean text output: Subject: ... 

        lines = text.splitlines()
        subj = f"Exploring {role_target} opportunities at {company_name}"
        body_lines = []
        for line in lines:
            if line.strip().lower().startswith("subject:"):
                subj = line.split(":", 1)[1].strip()
            else:
                body_lines.append(line)
                
        body = "\n".join(body_lines).strip()
        # Strip conversational AI filler like 'Here is the email:'
        import re
        body = re.sub(r"(?i)^Here is .*?:\s*", "", body).strip()
        # Clean any remaining JSON brackets if any exist
        if body.startswith("{"): body = body[1:].strip()
        if body.endswith("}"): body = body[:-1].strip()
        
        return subj, body

    @classmethod
    async def generate_followup(
        cls,
        step_number: int,
        company_name: str,
        founder_name: str,
        original_subject: str,
        best_project: VerifiedProject,
        candidate_name: str = "Saimani Ippili",
        target_role: str = "Data Science / ML Engineer"
    ) -> Tuple[str, str]:
        """Generates Day 3 (technical value-add) or Day 7 (polite break-up) follow-ups strictly from the candidate's job-seeking perspective."""
        first_name = founder_name.split()[0] if founder_name and founder_name.lower() != 'team' else 'Team'
        clean_project_name = best_project.name.split(':')[0].strip()
        key_tech = best_project.technologies[0] if best_project.technologies else "Python"
        domain = best_project.domains[0] if best_project.domains else "software engineering"

        system_prompt = (
            f"You are {candidate_name}, an early-career software/ML engineer writing a follow-up email "
            f"to {founder_name}, a founder/leader at {company_name}. "
            f"CRITICAL PERSPECTIVE RULE: You are a CANDIDATE seeking to join their team as a {target_role}. "
            f"You are NOT a recruiter, you are NOT hiring them, and you do not have roles to give. "
            f"You are reaching out to ask if they have open roles or engineering needs at {company_name} "
            f"where your skills could help. Keep the tone humble, proactive, and concise."
        )

        if step_number == 1:
            # Step 1: Day 3 Value Add
            prompt = f"""
Write a short, natural Day 3 follow-up email from candidate {candidate_name} to {founder_name} at {company_name}.
Original Subject: {original_subject}

CANDIDATE: {candidate_name} (Job seeker applying for {target_role})
RECIPIENT: {founder_name} (Founder / Leader at {company_name})
KEY PROJECT TO HIGHLIGHT: {clean_project_name} (built with {key_tech})

MANDATORY RULES:
1. PERSPECTIVE: You are asking to join THEIR team for {target_role} roles. Never say "I have a role for you" or "align with our needs".
2. Briefly reference candidate's hands-on project ({clean_project_name}) using {key_tech} as proof of capability.
3. Max 45-55 words.
4. Polite call to action: ask if they have 10-15 minutes to chat about potential {target_role} opportunities at {company_name}.
5. Sign off:
Best,
{candidate_name}
Portfolio: https://personal-portfolio-chi-bay-62.vercel.app/

RETURN CLEAN JSON ONLY:
{{
  "subject": "Re: {original_subject}",
  "body": "<clean formatted email body>"
}}
"""
        else:
            # Step 2: Day 7 Soft Break-Up
            prompt = f"""
Write a polite, zero-pressure final follow-up email (Day 7) from candidate {candidate_name} to {founder_name} at {company_name}.
Original Subject: {original_subject}

CANDIDATE: {candidate_name} (Job seeker applying for {target_role})
RECIPIENT: {founder_name} (Founder / Leader at {company_name})

MANDATORY RULES:
1. PERSPECTIVE: You are an applicant acknowledging they are busy and timing may not align for open roles right now.
2. Extremely short (under 40 words).
3. Leave the door open for future {target_role} openings.
4. Sign off:
Best,
{candidate_name}
Portfolio: https://personal-portfolio-chi-bay-62.vercel.app/

RETURN CLEAN JSON ONLY:
{{
  "subject": "Re: {original_subject}",
  "body": "<clean formatted email body>"
}}
"""
        raw_res = await llm_router.complete(prompt, system_prompt=system_prompt, temperature=0.2)
        try:
            import re
            cleaned_json = raw_res.strip()
            if "```" in cleaned_json:
                cleaned_json = re.sub(r"^```[a-zA-Z]*\n", "", cleaned_json)
                cleaned_json = re.sub(r"\n```$", "", cleaned_json)
            data = json.loads(cleaned_json)
            subj = data.get("subject", f"Re: {original_subject}")
            body = data.get("body", "")
            if body and candidate_name in body and "Best," in body:
                return subj, body
        except Exception as e:
            print(f"[EmailGenerator] JSON parse warning in followup: {e}")

        # Fallback template strictly in candidate perspective
        if step_number == 1:
            body = (
                f"Hey {first_name},\n\n"
                f"Following up on my note regarding {target_role} opportunities at {company_name}. "
                f"I've recently worked with {key_tech} building {clean_project_name} and would love to bring that hands-on execution to your engineering team.\n\n"
                f"Would you have 10-15 minutes to chat about potential openings?\n\n"
                f"Best,\n"
                f"{candidate_name}\n"
                f"Portfolio: https://personal-portfolio-chi-bay-62.vercel.app/"
            )
        else:
            body = (
                f"Hey {first_name},\n\n"
                f"Wanted to send one last quick note. I understand you're busy and timing might not align right now. "
                f"If an engineering or {target_role} role opens up down the road, I'd welcome the chance to connect.\n\n"
                f"Wishing you and {company_name} continued success!\n\n"
                f"Best,\n"
                f"{candidate_name}\n"
                f"Portfolio: https://personal-portfolio-chi-bay-62.vercel.app/"
            )
        return f"Re: {original_subject}", body
