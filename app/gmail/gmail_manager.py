import os
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
        import re
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
        Classifies incoming messages into human_reply, ooo (out of office), bounce, etc.
        """
        creds = cls.get_credentials()
        if not creds:
            return False, None, None
            
        try:
            service = build("gmail", "v1", credentials=creds)
            # Query incoming messages from this recipient or thread
            query = f"from:{to_email}"
            if thread_id:
                query = f"thread:{thread_id}"
                
            results = service.users().messages().list(userId='me', q=query, maxResults=5).execute()
            messages = results.get('messages', [])
            if not messages:
                return False, None, None
                
            for m in messages:
                msg_data = service.users().messages().get(userId='me', id=m['id']).execute()
                snippet = msg_data.get("snippet", "").lower()
                headers = {h['name'].lower(): h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
                sender = headers.get('from', '').lower()
                
                # Ignore messages sent by ourselves
                if "me" in sender or "ippilisaimani" in sender:
                    continue
                    
                # Classify response
                if any(k in snippet for k in ["out of office", "on leave", "automatic reply", "auto-reply", "away from"]):
                    return True, "ooo", snippet
                if any(k in snippet for k in ["unsubscribe", "remove me", "not interested", "stop emailing"]):
                    return True, "opt_out", snippet
                if any(k in snippet for k in ["delivery status notification", "failure", "undelivered", "mailer-daemon"]):
                    return True, "bounce", snippet
                    
                # Definite human reply
                return True, "human_reply", snippet
                
            return False, None, None
        except Exception as e:
            print(f"[GmailManager] Error checking replies: {e}")
            return False, None, None
