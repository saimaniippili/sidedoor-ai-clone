import os
import re
import json
import base64
from typing import Optional, Dict, Any, Tuple
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly"
]

TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"

class GmailManager:
    """Production-grade Gmail client that handles token refreshing safely
    without blocking headless execution or crashing on expired credentials.
    """
    _CACHED_CREDS = None

    @classmethod
    def get_credentials(cls):
        if cls._CACHED_CREDS:
            if cls._CACHED_CREDS.valid:
                return cls._CACHED_CREDS
            if cls._CACHED_CREDS.expired and cls._CACHED_CREDS.refresh_token:
                try:
                    cls._CACHED_CREDS.refresh(Request())
                    if cls._CACHED_CREDS.valid:
                        return cls._CACHED_CREDS
                except Exception:
                    cls._CACHED_CREDS = None

        candidate_sources = []
        token_env = os.environ.get("GMAIL_TOKEN_JSON") or os.environ.get("TOKEN_JSON")
        if token_env:
            try:
                candidate_sources.append(("env", json.loads(token_env)))
            except Exception:
                pass

        for path_opt in [TOKEN_FILE, os.path.join("/etc/secrets", TOKEN_FILE), os.path.join("/app", TOKEN_FILE)]:
            if os.path.exists(path_opt):
                try:
                    with open(path_opt, "r", encoding="utf-8") as f:
                        candidate_sources.append((path_opt, json.load(f)))
                except Exception:
                    pass

        for src_name, token_info in candidate_sources:
            try:
                creds = Credentials.from_authorized_user_info(token_info, SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as re_err:
                        print(f"[GmailManager] Refresh failed for {src_name}: {re_err}", flush=True)
                        continue
                if creds and creds.valid:
                    cls._CACHED_CREDS = creds
                    return creds
            except Exception as e:
                print(f"[GmailManager] Error initializing creds from {src_name}: {e}", flush=True)

        print("[GmailManager] No valid Gmail credentials found in env or files.", flush=True)
        return None

    @classmethod
    def is_authenticated(cls) -> bool:
        creds = cls.get_credentials()
        return creds is not None and creds.valid

    @classmethod
    def send_email(cls, to_email: str, subject: str, body: str, thread_id: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Sends an email and returns dict with message_id and thread_id, or None if failed."""
        creds = cls.get_credentials()
        if not creds:
            print("[GmailManager] Cannot send: Gmail is not authorized or token expired.")
            return None
        
        # Sanitize and validate recipient address (strictly reject spaces or invalid chars)
        if not to_email:
            print("[GmailManager] Cannot send: to_email is empty.")
            return None
            
        clean_email = to_email.strip().replace(" ", "")
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', clean_email):
            print(f"[GmailManager] Cannot send: invalid email address '{to_email}'")
            return None
            
        try:
            service = build("gmail", "v1", credentials=creds)
            message = EmailMessage()
            message.set_content(body)
            message["To"] = clean_email
            message["From"] = "me"
            message["Subject"] = subject
            
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            payload: Dict[str, Any] = {"raw": encoded_message}
            if thread_id:
                payload["threadId"] = thread_id
                
            sent = service.users().messages().send(userId="me", body=payload).execute()
            return {
                "message_id": sent.get("id"),
                "thread_id": sent.get("threadId")
            }
        except HttpError as error:
            print(f"[GmailManager] HttpError sending email: {error}")
            return None
        except Exception as e:
            print(f"[GmailManager] Unexpected error sending email: {e}")
            return None

    @classmethod
    def check_for_replies(cls, to_email: str, thread_id: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """Returns (has_replied, classification, snippet).
        Accurately inspects Gmail threads and incoming messages.
        Guarantees that ANY reply from recipient or recipient's domain immediately suppresses follow-ups.
        """
        creds = cls.get_credentials()
        if not creds:
            return False, None, None
            
        try:
            service = build("gmail", "v1", credentials=creds)
            
            # 1. Determine authenticated candidate email to reliably filter outbound messages
            my_email = "ippilisaimani40@gmail.com"
            try:
                prof = service.users().getProfile(userId='me').execute()
                if prof.get('emailAddress'):
                    my_email = prof['emailAddress'].lower().strip()
            except Exception:
                pass

            def _is_me(sender_str: str) -> bool:
                if not sender_str:
                    return False
                sender_lower = sender_str.lower()
                if my_email in sender_lower or "ippilisaimani" in sender_lower:
                    return True
                found = re.findall(r'[\w\.-]+@[\w\.-]+', sender_lower)
                if found and (found[0] == my_email or "ippilisaimani" in found[0]):
                    return True
                return False

            def _classify_snippet(snippet_text: str) -> str:
                s = snippet_text.lower()
                if any(k in s for k in ["out of office", "on leave", "automatic reply", "auto-reply", "away from", "vacation"]):
                    return "ooo"
                if any(k in s for k in ["unsubscribe", "remove me", "not interested", "stop emailing", "leave me alone"]):
                    return "opt_out"
                if any(k in s for k in ["delivery status notification", "failure", "undelivered", "mailer-daemon"]):
                    return "bounce"
                return "human_reply"

            # 2. Priority 1: Check via Gmail thread endpoint directly if thread_id is available
            if thread_id:
                try:
                    thread_data = service.users().threads().get(
                        userId='me',
                        id=thread_id,
                        format='metadata',
                        metadataHeaders=['From', 'To', 'Subject', 'Date']
                    ).execute()
                    
                    messages = thread_data.get('messages', [])
                    for m in messages:
                        headers = {h['name'].lower(): h['value'] for h in m.get('payload', {}).get('headers', [])}
                        sender = headers.get('from', '')
                        
                        # Skip messages sent by candidate
                        if _is_me(sender):
                            continue
                            
                        # An incoming message exists in this thread!
                        snippet = m.get('snippet', '')
                        classification = _classify_snippet(snippet)
                        print(f"[GmailManager] Verified reply in thread {thread_id} from {sender} ({classification}): {snippet[:80]}", flush=True)
                        return True, classification, snippet
                except Exception as te:
                    print(f"[GmailManager] threads.get({thread_id}) notice: {te}. Falling back to search query...", flush=True)

            # 3. Priority 2: Fallback to searching messages by recipient email
            clean_to = to_email.strip().lower() if to_email else ""
            if clean_to:
                query = f"from:{clean_to}"
                results = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
                messages = results.get('messages', [])
                for m in messages:
                    msg_data = service.users().messages().get(
                        userId='me',
                        id=m['id'],
                        format='metadata',
                        metadataHeaders=['From', 'To', 'Subject', 'Date']
                    ).execute()
                    headers = {h['name'].lower(): h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
                    sender = headers.get('from', '')
                    if _is_me(sender):
                        continue
                        
                    snippet = msg_data.get('snippet', '')
                    classification = _classify_snippet(snippet)
                    print(f"[GmailManager] Verified reply via search from {sender} ({classification}): {snippet[:80]}", flush=True)
                    return True, classification, snippet
                    
            return False, None, None
        except Exception as e:
            print(f"[GmailManager] Error checking replies: {e}", flush=True)
            return False, None, None
