from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from app.database.models import Outreach, ScheduledFollowup, Founder, Company, Opportunity, ActiveUser
from app.matching.project_registry import get_project, VerifiedProject
from app.outreach.email_generator import EmailGenerator
from app.gmail.gmail_manager import GmailManager
from app.config import config

class FollowupService:
    """Manages the creation, reconciliation, and delivery of automated follow-ups.
    Follow-up Sequence:
      Step 1 (Day 3): Technical value-add and concrete project hook.
      Step 2 (Day 7): Polite, respectful soft break-up.
    """
    
    @classmethod
    def schedule_sequence(cls, db: Session, outreach: Outreach, best_project: VerifiedProject) -> None:
        """Called immediately after initial email is sent to persist Day 3 and Day 7 actions."""
        now = outreach.sent_at or datetime.utcnow()
        day3_time = now + timedelta(days=config.followup_day_1)
        day7_time = now + timedelta(days=config.followup_day_2)
        
        # Check if already scheduled
        existing = db.query(ScheduledFollowup).filter(ScheduledFollowup.outreach_id == outreach.id).all()
        if existing:
            return
            
        action_1 = ScheduledFollowup(
            outreach_id=outreach.id,
            step_number=1,
            scheduled_time=day3_time,
            idempotency_key=f"outreach_{outreach.id}_step_1",
            status="PENDING"
        )
        action_2 = ScheduledFollowup(
            outreach_id=outreach.id,
            step_number=2,
            scheduled_time=day7_time,
            idempotency_key=f"outreach_{outreach.id}_step_2",
            status="PENDING"
        )
        db.add(action_1)
        db.add(action_2)
        
        outreach.next_followup_at = day3_time
        db.commit()
        print(f"[FollowupService] Scheduled Step 1 for {day3_time} and Step 2 for {day7_time} for outreach #{outreach.id}")

    @classmethod
    def cancel_all_followups(cls, db: Session, outreach_id: int, reason: str = "replied") -> int:
        """Cancels all pending follow-ups for a given outreach."""
        actions = db.query(ScheduledFollowup).filter(
            ScheduledFollowup.outreach_id == outreach_id,
            ScheduledFollowup.status == "PENDING"
        ).all()
        
        count = 0
        for act in actions:
            act.status = "CANCELLED"
            act.last_error = f"Cancelled due to: {reason}"
            count += 1
            
        outreach = db.query(Outreach).filter(Outreach.id == outreach_id).first()
        if outreach:
            outreach.status = reason
            outreach.next_followup_at = None
            
        db.commit()
        print(f"[FollowupService] Cancelled {count} pending follow-up action(s) for outreach #{outreach_id}")
        return count

    @classmethod
    async def process_due_followups(cls, db: Session) -> int:
        """Scans database for due follow-up actions and sends them if eligible."""
        if config.global_pause:
            print("[FollowupService] Global pause is active. Skipping follow-up execution.")
            return 0
            
        now = datetime.utcnow()
        due_actions = db.query(ScheduledFollowup).filter(
            ScheduledFollowup.status == "PENDING",
            ScheduledFollowup.scheduled_time <= now
        ).all()
        
        sent_count = 0
        for action in due_actions:
            outreach = db.query(Outreach).filter(Outreach.id == action.outreach_id).first()
            if not outreach:
                action.status = "SKIPPED"
                continue
                
            opp = db.query(Opportunity).filter(Opportunity.id == outreach.opportunity_id).first()
            founder = db.query(Founder).filter(Founder.id == opp.founder_id).first() if opp else None
            company = db.query(Company).filter(Company.id == opp.company_id).first() if opp else None
            
            if not founder or not company:
                action.status = "SKIPPED"
                continue
                
            # 1. Eligibility Check: Check if recipient already replied
            has_reply, classification, _ = GmailManager.check_for_replies(
                to_email=founder.email,
                thread_id=outreach.gmail_thread_id
            )
            if has_reply:
                if classification in ["human_reply", "opt_out"]:
                    cls.cancel_all_followups(db, outreach.id, reason="replied" if classification == "human_reply" else "opt_out")
                    continue
                elif classification == "bounce":
                    cls.cancel_all_followups(db, outreach.id, reason="bounced")
                    founder.is_suppressed = True
                    founder.suppression_reason = "hard_bounce"
                    db.commit()
                    continue
            
            # 2. Check if outreach was skipped, bounced, or suppressed
            if outreach.status in ["replied", "bounced", "skipped", "cancelled", "completed"]:
                action.status = "CANCELLED"
                db.commit()
                continue
                
            # 3. Generate personalized follow-up content
            import json
            selected_ids = []
            try:
                selected_ids = json.loads(outreach.selected_project_ids or "[]")
            except:
                pass
            proj_id = selected_ids[0] if selected_ids else "datachat"
            project = get_project(proj_id) or get_project("datachat")
            
            user = db.query(ActiveUser).first()
            cand_name = user.candidate_name if user and user.candidate_name else "Saimani Ippili"
            target_role = opp.potential_role if opp and opp.potential_role else "Data Science / ML Engineer"

            subject, body = await EmailGenerator.generate_followup(
                step_number=action.step_number,
                company_name=company.name,
                founder_name=founder.name,
                original_subject=outreach.email_subject,
                best_project=project,
                candidate_name=cand_name,
                target_role=target_role
            )
            
            action.generated_subject = subject
            action.generated_body = body
            action.attempts += 1
            
            # 4. Dispatch Email
            if config.dry_run:
                print(f"[FollowupService DRY-RUN] Would send Step {action.step_number} to {founder.email}")
                action.status = "SENT"
                action.executed_at = datetime.utcnow()
                outreach.followup_count += 1
                if action.step_number >= 2:
                    outreach.status = "completed"
                sent_count += 1
                db.commit()
                continue
                
            send_res = GmailManager.send_email(
                to_email=founder.email,
                subject=subject,
                body=body,
                thread_id=outreach.gmail_thread_id
            )
            
            if send_res:
                action.status = "SENT"
                action.executed_at = datetime.utcnow()
                outreach.followup_count += 1
                if action.step_number >= 2:
                    outreach.status = "completed"
                    outreach.next_followup_at = None
                else:
                    # Update next follow-up target
                    next_act = db.query(ScheduledFollowup).filter(
                        ScheduledFollowup.outreach_id == outreach.id,
                        ScheduledFollowup.step_number == 2
                    ).first()
                    if next_act:
                        outreach.next_followup_at = next_act.scheduled_time
                sent_count += 1
                db.commit()
                print(f"[FollowupService] Successfully sent Step {action.step_number} to {founder.email}")
            else:
                action.last_error = "Gmail sending failed or unauthorized"
                if action.attempts >= 3:
                    action.status = "FAILED"
                db.commit()
                
        return sent_count
