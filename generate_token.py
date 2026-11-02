import os
import json
import requests
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly"
]

RENDER_API_KEY = "rnd_PDUs1aAmTfp3IUfLLJjYCOygTg8e"
RENDER_SERVICE_ID = "srv-dbfdncqvcj2c73fojj60"

def sync_to_render(token_str: str) -> bool:
    print("\n[Sync] Uploading fresh token to Render cloud service...")
    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = [
        {"key": "GMAIL_TOKEN_JSON", "value": token_str}
    ]
    try:
        resp = requests.put(
            f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars",
            headers=headers,
            json=payload,
            timeout=15.0
        )
        if resp.status_code in (200, 201):
            print("[Sync] SUCCESS! Render environment variable GMAIL_TOKEN_JSON updated.")
            print("[Sync] Sidedoor bot on Render is restarting with your new credentials!")
            return True
        else:
            print(f"[Sync] Render update returned HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"[Sync] Failed to upload to Render: {e}")
        return False

def main():
    if not os.path.exists("credentials.json"):
        print("ERROR: credentials.json is missing in current directory.", flush=True)
        return
        
    print("\n==========================================", flush=True)
    print("      SIDEDOOR GMAIL AUTHENTICATION       ", flush=True)
    print("==========================================", flush=True)
    print("Opening your browser to authenticate your Gmail account...", flush=True)
    print("Please select your Google account and click 'Allow'.\n", flush=True)
    
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    try:
        # prompt='consent' forces Google to issue a brand new refresh token
        creds = flow.run_local_server(port=0, open_browser=True, prompt="consent", access_type="offline")
        token_str = creds.to_json()
        
        with open("token.json", "w", encoding="utf-8") as f:
            f.write(token_str)
        print("\n[Local] SUCCESS: token.json created locally!", flush=True)
        
        # Automatically sync to Render
        sync_to_render(token_str)
        
        print("\nAll done! You can now send emails via your Telegram bot.", flush=True)
    except Exception as e:
        print(f"\nError during authorization: {e}", flush=True)

if __name__ == "__main__":
    main()
