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
    
    @classmethod
    def _find_file(cls, filename: str) -> Optional[str]:
        # 1. Direct local path
        if os.path.exists(filename):
            return filename
        # 2. Render Docker secret files mount path (/etc/secrets/<filename>)
        render_path = os.path.join("/etc/secrets", filename)
        if os.path.exists(render_path):
            return render_path
        # 3. /app directory path
        app_path = os.path.join("/app", filename)
        if os.path.exists(app_path):
            return app_path
        return None

    @classmethod
    def get_credentials(cls) -> Optional[Credentials]:
        token_path = cls._find_file(TOKEN_FILE)
        if not token_path:
            # Check environment variable fallback
            token_env = os.environ.get("GMAIL_TOKEN_JSON") or os.environ.get("TOKEN_JSON")
            if token_env:
                try:
                    token_info = json.loads(token_env)
                    creds = Credentials.from_authorized_user_info(token_info, SCOPES)
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    return creds if (creds and creds.valid) else None
                except Exception as e:
                    print(f"[GmailManager] Error parsing GMAIL_TOKEN_JSON env var: {e}", flush=True)
            print(f"[GmailManager] token.json not found in ., /etc/secrets, or /app", flush=True)
            return None
            
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    try:
                        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
                            token.write(creds.to_json())
                    except Exception:
                        pass
                except RefreshError as e:
                    print(f"[GmailManager] Refresh token expired or revoked: {e}", flush=True)
                    return None
            return creds if (creds and creds.valid) else None
        except Exception as e:
            print(f"[GmailManager] Error reading token file {token_path}: {e}", flush=True)
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
        
        try:
            service = build("gmail", "v1", credentials=creds)
            message = EmailMessage()
            message.set_content(body)
            message["To"] = to_email
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
