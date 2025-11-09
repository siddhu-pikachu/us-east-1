from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() == "true"
    jira_base_url: str = os.getenv("JIRA_BASE_URL", "")
    jira_email: str = os.getenv("JIRA_EMAIL", "")
    jira_api_token: str = os.getenv("JIRA_API_TOKEN", "")
    jira_project_key: str = os.getenv("JIRA_PROJECT_KEY", "OPS")
    app_secret_key: str = os.getenv("APP_SECRET_KEY", "dev")


settings = Settings()

