import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    telegram_bot_token: str = ""
    admin_telegram_chat_id: Optional[str] = None
    
    # AI Providers
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.1-70b-instruct"
    
    # Discovery & Enrichment
    exa_api_key: str = ""
    hunter_api_key: str = ""
    apollo_api_key: str = ""
    
    # Database
    database_url: str = "sqlite:///./backdoor.db"
    
    # Email Sending & Limits
    daily_send_limit: int = 50
    dry_run: bool = False
    global_pause: bool = False
    
    # Follow-up Schedule (in days)
    followup_day_1: int = 3
    followup_day_2: int = 7
    
    # Crawl4AI Cache Directory
    crawl4ai_base_directory: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".crawl4ai")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

config = AppConfig()
os.environ.setdefault("CRAWL4_AI_BASE_DIRECTORY", config.crawl4ai_base_directory)
