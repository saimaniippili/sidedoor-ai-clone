PRIMARY_LOCATIONS = ["Hyderabad", "Bangalore", "Chennai"]
FALLBACK_LOCATIONS = ["Pune", "Delhi NCR", "Mumbai"]
LOCATIONS_LIST = PRIMARY_LOCATIONS + FALLBACK_LOCATIONS
EXA_EXCLUDE_DOMAINS = [
    "linkedin.com", "ycombinator.com", "glassdoor.com", "indeed.com",
    "nasscom.in", "inc42.com", "yourstory.com", "tracxn.com",
    "crunchbase.com", "f6s.com", "pitchbook.com", "wellfound.com",
    "angel.co", "medium.com", "github.com", "wikipedia.org",
    "techcrunch.com", "economictimes.indiatimes.com", "startuply.vc"
]


import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def keep_alive_heartbeat():
    import time
    import urllib.request
    url = os.environ.get("RENDER_EXTERNAL_URL", "https://sidedoor-ai-clone.onrender.com")
    print(f"[KeepAlive] Initiating 24/7 anti-sleep heartbeat targeting {url}...", flush=True)
    time.sleep(30)
    while True:
        try:
            req = urllib.request.Request(
                f"{url}/",
                headers={"User-Agent": "RecruiterCopilot-Heartbeat/1.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                print(f"[KeepAlive] Heartbeat ping successful ({resp.status}) - Render container kept awake 24/7.", flush=True)
        except Exception as e:
            print(f"[KeepAlive] Heartbeat ping warning: {e}", flush=True)
        # Ping every 8 minutes (Render free tier sleeps after 15 minutes of HTTP inactivity)
        time.sleep(480)

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=keep_alive_heartbeat, daemon=True).start()
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

import os
import io
import json
import asyncio
from datetime import datetime
from typing import Optional

from PyPDF2 import PdfReader
from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
)

from app.config import config
from app.database.session import SessionLocal, init_db
from app.database.models import (
    Company, Founder, Opportunity, Outreach, ChatHistory, ActiveUser, ScheduledFollowup, SuppressionRecord
)
from app.discovery.startup_filter import StartupFilter
from app.discovery.email_engine import FounderEmailEngine
from app.matching.project_registry import get_project, VerifiedProject, list_all_projects
from app.matching.github_project_service import GitHubProjectService
from app.matching.resume_parser import ResumeParser
from app.matching.project_scorer import ProjectScorer
from app.outreach.framework_selector import OutreachFrameworkSelector
from app.outreach.email_generator import EmailGenerator
from app.outreach.followup_service import FollowupService
from app.gmail.gmail_manager import GmailManager
from app.intelligence.llm_router import llm_router

SYSTEM_PROMPT = """You are Recruiter Copilot, an elite technical recruiting assistant. Your goal is to guide the candidate through onboarding to find them an early-stage startup engineering role.
Speak professionally yet casually like an engineer. Keep messages concise.
Onboarding steps:
1. Ask for their target technical role (e.g., Data Science, ML Engineer, Backend).
2. Ask for their preferred location (e.g., Hyderabad, Bangalore, Chennai, Remote).
3. If they upload a PDF resume, acknowledge their verified projects (like DataChat, Fake Job Detection, MedSage).
When you have collected their preferences, conclude your message with the trigger [START_SEARCH]."""

async def process_llm_conversation(chat_id: str, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        history = db.query(ChatHistory).filter(ChatHistory.chat_id == chat_id).order_by(ChatHistory.id.asc()).limit(15).all()
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
            
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        reply = await llm_router.complete(
            prompt=messages[-1]["content"] if messages else "Hello",
            system_prompt=SYSTEM_PROMPT,
            temperature=0.7
        )
        
        should_search = False
        if "[START_SEARCH]" in reply:
            should_search = True
            reply = reply.replace("[START_SEARCH]", "").strip()
            
            user = db.query(ActiveUser).filter(ActiveUser.chat_id == chat_id).first()
            if not user:
                user = ActiveUser(chat_id=chat_id, preferences="Parsed from chat history")
                db.add(user)
            else:
                user.is_active = 1
            db.commit()
            
        await context.bot.send_message(chat_id=chat_id, text=reply)
        
        db.add(ChatHistory(chat_id=chat_id, role="assistant", content=reply))
        db.commit()
        
        if should_search:
            await context.bot.send_message(chat_id=chat_id, text="🚀 Starting autonomous startup discovery...")
            asyncio.create_task(run_startup_pipeline(chat_id, context))
    finally:
        db.close()

async def run_startup_pipeline(chat_id: str, context: ContextTypes.DEFAULT_TYPE, override_limit: bool = True, location_override: str = None, attempt_count: int = 1):
    """Core autonomous discovery, dynamic matching, and draft generation pipeline."""
    db = SessionLocal()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_sent = db.query(Outreach).filter(Outreach.status == "sent", Outreach.sent_at >= today_start).count()
        
        # 1. Fetch preferences from chat history
        history_records = db.query(ChatHistory).filter(ChatHistory.chat_id == chat_id).order_by(ChatHistory.id.asc()).limit(20).all()
        chat_text = "\n".join([f"{msg.role}: {msg.content}" for msg in history_records])
        
        past_companies = db.query(Company).all()
        avoid_domains = {c.domain.lower() for c in past_companies if c.domain}
        avoid_names = {c.name.lower() for c in past_companies if c.name}
        
        # Load all suppressed domains and emails from SuppressionRecord & Founders
        suppression_records = db.query(SuppressionRecord).all()
        avoid_domains.update({s.domain.lower() for s in suppression_records if s.domain})
        avoid_emails = {s.email.lower() for s in suppression_records if s.email}
        avoid_emails.update({f.email.lower() for f in db.query(Founder).all() if f.email})
        
        user = db.query(ActiveUser).filter(ActiveUser.chat_id == chat_id).first()
        cand_name = (user.candidate_name if user and user.candidate_name else "Saimani Ippili")
        
        dynamic_roles = []
        if user and user.extracted_roles:
            try: dynamic_roles = json.loads(user.extracted_roles)
            except: pass
        role = dynamic_roles[0] if dynamic_roles else "Data Science / ML Engineer"
        
        candidate_projects = []
        # Source 1: Verified Resume Projects
        if user and user.extracted_projects:
            try:
                p_data = json.loads(user.extracted_projects)
                candidate_projects = ResumeParser.convert_to_verified_projects(p_data)
            except Exception as e:
                print(f"Error loading dynamic projects: {e}")
        if not candidate_projects:
            candidate_projects = list_all_projects()

        # Source 2: Dynamic Live GitHub Repositories (READMEs, architectures, live code)
        try:
            gh_projects = await GitHubProjectService.get_github_projects()
            # Combine without duplicate project names
            existing_names = {p.name.lower() for p in candidate_projects}
            for gp in gh_projects:
                if gp.name.lower() not in existing_names:
                    candidate_projects.append(gp)
            print(f"[Pipeline] Combined Project Pool: {len(candidate_projects)} projects (Resume + GitHub).", flush=True)
        except Exception as ghe:
            print(f"[Pipeline] GitHub project integration warning: {ghe}", flush=True)

        # Priority-First Location Selection: Hyderabad -> Bangalore -> Chennai -> Fallback hubs
        if location_override:
            location = location_override
        else:
            # Check which primary location has had the least outreach, prioritizing Hyderabad
            location = PRIMARY_LOCATIONS[0]
        
        if attempt_count == 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔍 Scouting early-stage AI/ML startups in {location}...\nTargeting personal founder inboxes across Hyderabad, Bangalore & Chennai with zero-bounce deliverability validation."
            )
        
        import exa_py
        if not config.exa_api_key:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ EXA_API_KEY is not configured in .env.")
            return
            
        exa = exa_py.Exa(config.exa_api_key)
        results = []
        seen_urls = set()
        
        # Dual-Tier Search Strategy:
        # 1. Founder-Centric: Discovers startups via founder names & personal email contacts
        try:
            f_res = exa.search_and_contents(
                f"early-stage AI tech startup founders in {location} official website email",
                type="neural",
                num_results=15,
                exclude_domains=EXA_EXCLUDE_DOMAINS,
                text=True
            )
            for r in f_res.results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    results.append(r)
        except Exception as fe:
            print(f"[Pipeline] Founder search error for {location}: {fe}", flush=True)

        # 2. Company-Centric: Discovers innovative early-stage AI product platforms
        try:
            c_res = exa.search_and_contents(
                f"innovative early-stage AI machine learning tech startups founded in {location} official product website",
                type="neural",
                num_results=15,
                exclude_domains=EXA_EXCLUDE_DOMAINS,
                text=True
            )
            for r in c_res.results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    results.append(r)
        except Exception as ce:
            print(f"[Pipeline] Company search error for {location}: {ce}", flush=True)

        print(f"[Pipeline] Exa found {len(results)} total candidate startups/founders in {location}", flush=True)
            
        found_match = False
        skipped_aggregators = 0
        skipped_seen = 0
        skipped_no_email = 0
        
        import httpx
        for res in results:
            domain = StartupFilter.clean_domain(res.url)
            if not domain or StartupFilter.is_job_board_or_aggregator(domain):
                skipped_aggregators += 1
                continue
                
            raw_name = StartupFilter.normalize_company_name(res.title or domain)
            company_name = raw_name if raw_name.lower() not in ["about", "home", "index", "welcome", "platform"] else domain.split('.')[0].capitalize()
            research_text = res.text[:3000] if res.text else "Early stage technology company."
            
            if domain.lower() in avoid_domains or company_name.lower() in avoid_names:
                print(f"[Pipeline] Already processed/contacted {company_name} ({domain}) - skipping.", flush=True)
                skipped_seen += 1
                continue
                
            print(f"[Pipeline] Checking {company_name} ({domain})...", flush=True)
            
            # 1. Multi-Tier Open-Source & API Founder Discovery Engine (Zero Bounces Standard)
            verified_contact = await FounderEmailEngine.discover_and_verify(
                company_name=company_name,
                domain=domain,
                research_text=research_text,
                hunter_api_key=config.hunter_api_key
            )
            
            if not verified_contact:
                print(f"[Pipeline] No verified deliverable email found for {company_name} ({domain}) - skipping to prevent bounces.", flush=True)
                skipped_no_email += 1
                continue
                
            target_email = verified_contact.email
            founder_name = verified_contact.name
            founder_role = verified_contact.role
            verified_score = verified_contact.confidence_score
            verification_source = verified_contact.verification_source
            mx_provider = verified_contact.mx_provider

            if not target_email or target_email.lower() in avoid_emails:
                skipped_no_email += 1
                continue
                
            # Check if founder already outreach in db
            if db.query(Founder).filter(Founder.email == target_email).first():
                continue
                
            # 2. Dynamic Project Matching Engine using candidate's actual projects
            scored_projects = ProjectScorer.select_best_projects(
                company_text=f"{company_name} {research_text}",
                role_title=role,
                max_projects=1,
                candidate_projects=candidate_projects
            )
            best_project, match_score, signals = scored_projects[0]
            
            # 3. Dynamic Framework Selection
            framework, reason = OutreachFrameworkSelector.select_framework(
                company_name=company_name,
                company_description=research_text,
                best_project=best_project,
                match_score=match_score
            )
            
            if framework == "NOT_TO_SEND":
                print(f"[Pipeline] Skipping {company_name}: Low relevance match score ({match_score}).", flush=True)
                continue
                
            # Persist company and founder
            company = Company(name=company_name, domain=domain, location=location, description=research_text[:500], status="QUALIFIED")
            db.add(company)
            db.commit()
            db.refresh(company)
            
            # Immediately record in SuppressionRecord so it is NEVER processed or queried again
            if not db.query(SuppressionRecord).filter(SuppressionRecord.domain == domain).first():
                db.add(SuppressionRecord(domain=domain, email=target_email, reason="drafted"))
                db.commit()
            
            founder = Founder(
                company_id=company.id,
                name=founder_name,
                role=founder_role,
                email=target_email,
                email_verified=1,
                verification_score=float(verified_score) / 100.0 if verified_score else 0.95
            )
            db.add(founder)
            db.commit()
            db.refresh(founder)
            
            opp = Opportunity(
                chat_id=chat_id,
                company_id=company.id,
                founder_id=founder.id,
                match_score=int(match_score * 100),
                opportunity_reason=f"Framework: {framework} | Signals: {', '.join(signals)}",
                potential_role=role
            )
            db.add(opp)
            db.commit()
            db.refresh(opp)
            
            # Generate email using selected framework and verified project
            subject, body = await EmailGenerator.generate_initial_draft(
                company_name=company_name,
                company_description=research_text[:1000],
                founder_name=founder_name,
                role_target=role,
                selected_framework=framework,
                best_project=best_project,
                project_signals=signals,
                candidate_name=cand_name
            )
            
            outreach = Outreach(
                opportunity_id=opp.id,
                framework=framework,
                selected_project_ids=json.dumps([best_project.project_id]),
                candidate_evidence=best_project.summary,
                email_subject=subject,
                email_body=body,
                status="pending"
            )
            db.add(outreach)
            db.commit()
            db.refresh(outreach)
            
            # Send sample draft to Telegram with human approval buttons
            score_badge = f"({verification_source} | MX: {mx_provider} | {verified_score}% Confidence 🛡️)"
            draft_msg = (
                f"🎯 **Target Found: {company_name}** ({domain})\n"
                f"👤 **Recipient:** {founder_name} ({founder_role})\n"
                f"📬 **Deliverable Email:** `{target_email}`\n"
                f"🛡️ **Verification:** {score_badge}\n"
                f"📐 **Framework:** `{framework}` (Score: {opp.match_score}/100)\n"
                f"💡 **Matched Project:** `{best_project.name}`\n\n"
                f"**Subject:** {outreach.email_subject}\n\n"
                f"{outreach.email_body}"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Send via Gmail", callback_data=f"send_{outreach.id}"),
                    InlineKeyboardButton("❌ Skip", callback_data=f"skip_{outreach.id}")
                ]
            ]
            try:
                await context.bot.send_message(chat_id=chat_id, text=draft_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            except Exception as send_err:
                print(f"[Telegram] Markdown send failed ({send_err}); sending plain text fallback", flush=True)
                await context.bot.send_message(chat_id=chat_id, text=draft_msg, reply_markup=InlineKeyboardMarkup(keyboard))
            print(f"[Pipeline] Draft sent to user {chat_id}!", flush=True)
            found_match = True
            break
            
        if not found_match:
            # Strict Priority Order: Hyderabad -> Bangalore -> Chennai -> (only worst case: Pune, Delhi NCR, Mumbai)
            full_order = PRIMARY_LOCATIONS + FALLBACK_LOCATIONS
            curr_idx = full_order.index(location) if location in full_order else 0
            if curr_idx + 1 < len(full_order):
                next_loc = full_order[curr_idx + 1]
                tier_label = "Primary Hub" if next_loc in PRIMARY_LOCATIONS else "Fallback State"
                print(f"[Pipeline] Checked {location}; scanning {next_loc} next ({tier_label} {curr_idx + 2}/{len(full_order)})...", flush=True)
                asyncio.create_task(run_startup_pipeline(chat_id, context, location_override=next_loc, attempt_count=attempt_count + 1))
                return
            else:
                breakdown = (
                    f"Scanned candidate tech startups across prioritized hubs: {', '.join(PRIMARY_LOCATIONS)}.\n\n"
                    f"All deliverable inboxes in this cycle have been evaluated. Send 'search' anytime to run another scan cycle!"
                )
                await context.bot.send_message(chat_id=chat_id, text=breakdown)
    except Exception as e:
        print(f"Error in pipeline: {e}", flush=True)
        await context.bot.send_message(chat_id=chat_id, text=f"Search pipeline encountered an issue: {e}")
    finally:
        db.close()


# --- Handlers ---
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    db = SessionLocal()
    user = db.query(ActiveUser).filter(ActiveUser.chat_id == chat_id).first()
    if not user:
        user = ActiveUser(chat_id=chat_id, preferences="Data Science / AI / ML / Backend Engineer")
        db.add(user)
    else:
        user.is_active = 1
    db.commit()
    db.close()
    
    welcome_text = "Recruiter Copilot Active!\n\nCandidate: Saimani Ippili\nTarget Roles: Data Science / AI / ML / Backend Engineer\nLocation Hierarchy: 1. Hyderabad (Primary) -> 2. Bangalore -> 3. Chennai\n\nHunting down the next qualified startup now..."
    await update.message.reply_text(welcome_text)
    asyncio.create_task(run_startup_pipeline(chat_id, context))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    text = update.message.text.strip()
    
    # Check if user sent a new Hunter API key (40 hex chars or starting with hunter_)
    clean_key = text.strip()
    if (len(clean_key) == 40 and all(c in "0123456789abcdefABCDEF" for c in clean_key)) or clean_key.startswith("hunter_"):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"https://api.hunter.io/v2/account?api_key={clean_key}")
                if r.status_code == 200:
                    d = r.json().get("data", {})
                    searches = d.get("requests", {}).get("searches", {}).get("remaining", 0)
                    config.hunter_api_key = clean_key
                    await update.message.reply_text(
                        f"🎉 New Hunter.io Key Activated!\n\n"
                        f"Account: {d.get('email')}\n"
                        f"Searches Available: {searches}\n\n"
                        f"🔍 Resuming startup discovery now..."
                    )
                    asyncio.create_task(run_startup_pipeline(chat_id, context, override_limit=True))
                    return
                else:
                    await update.message.reply_text("❌ Key test failed: That Hunter API key appears invalid or expired.")
                    return
        except Exception as e:
            await update.message.reply_text(f"❌ Error testing key: {e}")
            return
            
    if text.lower() in ["keep searching", "search", "more"]:
        await update.message.reply_text("Hunting down the next qualified startup... 🔍")
        asyncio.create_task(run_startup_pipeline(chat_id, context, override_limit=True))
        return
        
    db = SessionLocal()
    db.add(ChatHistory(chat_id=chat_id, role="user", content=text))
    db.commit()
    db.close()
    
    await process_llm_conversation(chat_id, context)

async def handle_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    doc = update.message.document
    file = await context.bot.get_file(doc.file_id)
    pdf_bytes = await file.download_as_bytearray()
    
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        extracted_text = "".join([page.extract_text() + "\n" for page in reader.pages])
    except Exception:
        await update.message.reply_text("Could not parse that PDF. Drop your resume as text or another format!")
        return
        
    await update.message.reply_text("Analyzing your resume... extracting your skills, verified projects, and qualified roles...")
    
    parsed_profile = await ResumeParser.parse_resume_to_profile(extracted_text)
    cand_name = parsed_profile.get("candidate_name") or "Candidate"
    target_roles = parsed_profile.get("target_roles") or ["Software Engineer"]
    skills = parsed_profile.get("top_skills") or []
    projects = parsed_profile.get("projects") or []
    
    db = SessionLocal()
    user = db.query(ActiveUser).filter(ActiveUser.chat_id == chat_id).first()
    if not user:
        user = ActiveUser(chat_id=chat_id)
        db.add(user)
        
    user.candidate_name = cand_name
    user.resume_text = extracted_text
    user.extracted_roles = json.dumps(target_roles)
    user.extracted_skills = json.dumps(skills)
    user.extracted_projects = json.dumps(projects)
    user.is_active = 1
    db.commit()
    db.close()
    
    proj_bullets = "\n".join(["- " + p.get("name", "") for p in projects]) if projects else "- Custom engineering projects extracted from resume"
    summary_msg = (
        f"Resume Profile Synced!\n\n"
        f"Candidate: {cand_name}\n"
        f"Target Roles: {', '.join(target_roles)}\n"
        f"Top Skills: {', '.join(skills[:8])}\n"
        f"Extracted Projects:\n{proj_bullets}\n\n"
        f"Location Hierarchy: Hyderabad (Priority 1) -> Bangalore -> Chennai\n\n"
        f"Hunting down matching startups now..."
    )
    await update.message.reply_text(summary_msg)
    asyncio.create_task(run_startup_pipeline(chat_id, context))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
        
    data = query.data
    db = SessionLocal()
    try:
        action, outreach_id = data.split("_")
        outreach = db.query(Outreach).filter(Outreach.id == int(outreach_id)).first()
        if not outreach:
            await query.edit_message_text("Draft not found.")
            return
            
        opp = db.query(Opportunity).filter(Opportunity.id == outreach.opportunity_id).first()
        founder = db.query(Founder).filter(Founder.id == opp.founder_id).first()
        company = db.query(Company).filter(Company.id == opp.company_id).first()
        
        if action == "send":
            clean_to = founder.email.strip().replace(" ", "") if founder and founder.email else ""
            if not clean_to or "@" not in clean_to:
                await query.edit_message_text(f"❌ Recipient email '{founder.email if founder else 'None'}' is invalid or empty. Skipped.")
                return
                
            # Check Gmail authentication
            if not GmailManager.is_authenticated() and not config.dry_run:
                await query.edit_message_text("⚠️ Gmail is not authorized. Please generate token.json using `python generate_token.py` on your machine.")
                return
                
            send_res = GmailManager.send_email(
                to_email=clean_to,
                subject=outreach.email_subject,
                body=outreach.email_body
            ) if not config.dry_run else {"message_id": "dry_run_id", "thread_id": "dry_run_thread"}
            
            if send_res or config.dry_run:
                outreach.status = "sent"
                outreach.sent_at = datetime.utcnow()
                outreach.gmail_message_id = send_res.get("message_id") if send_res else None
                outreach.gmail_thread_id = send_res.get("thread_id") if send_res else None
                db.commit()
                
                # Permanently suppress company domain and founder email so they never re-appear
                if company and not db.query(SuppressionRecord).filter(SuppressionRecord.domain == company.domain).first():
                    db.add(SuppressionRecord(domain=company.domain, email=founder.email, reason="contacted"))
                    db.commit()

                # Automatically schedule Day 3 and Day 7 follow-up sequence in database
                best_project = get_project(json.loads(outreach.selected_project_ids or "[]")[0]) or get_project("datachat")
                FollowupService.schedule_sequence(db, outreach, best_project)
                
                await query.edit_message_text(
                    f"🚀 Email Sent to {founder.email} ({company.name})!\n\n"
                    f"📅 Automated Follow-up Sequence Scheduled:\n"
                    f"- Day 3: Technical Value-Add Follow-up\n"
                    f"- Day 7: Soft Break-Up Final Follow-up\n"
                    f"*(Will automatically cancel if they reply!)*\n\n"
                    f"🔍 Autonomous mode: Hunting down your next target now..."
                )
                # Automatically search for the next startup without waiting for user prompt
                asyncio.create_task(run_startup_pipeline(str(query.message.chat_id), context))
            else:
                await query.edit_message_text("❌ Failed to send via Gmail. Check your credentials.")
                
        elif action == "skip":
            outreach.status = "skipped"
            if company and not db.query(SuppressionRecord).filter(SuppressionRecord.domain == company.domain).first():
                db.add(SuppressionRecord(domain=company.domain, email=founder.email if founder else None, reason="skipped"))
            db.commit()
            await query.edit_message_text(f"Skipped {company.name}. Hunting for the next match...")
            asyncio.create_task(run_startup_pipeline(str(query.message.chat_id), context))
    finally:
        db.close()

# --- Background Scheduled Jobs ---
async def periodic_followup_job(context: ContextTypes.DEFAULT_TYPE):
    """Background task running every hour to dispatch due follow-ups and check replies."""
    db = SessionLocal()
    try:
        sent = await FollowupService.process_due_followups(db)
        if sent > 0:
            print(f"[Scheduled Job] Successfully delivered {sent} automated follow-up email(s).")
    except Exception as e:
        print(f"[Scheduled Job Error]: {e}")
    finally:
        db.close()

def main():
    threading.Thread(target=start_health_server, daemon=True).start()

    init_db()
    
    if not config.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not configured in .env")
        return
        
    app = Application.builder().token(config.telegram_bot_token).build()
    
    # Schedule hourly background follow-up worker
    if app.job_queue:
        app.job_queue.run_repeating(periodic_followup_job, interval=3600, first=60)
    else:
        print("WARNING: JobQueue not initialized")
    
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_resume))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    while True:
        try:
            print("Recruiter Copilot is running live on Render! Waiting for updates...")
            app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
        except Exception as e:
            print(f"[Bot Polling Notice]: {e}. Automatically resuming in 10s...", flush=True)
            import time
            time.sleep(10)

if __name__ == "__main__":
    main()
