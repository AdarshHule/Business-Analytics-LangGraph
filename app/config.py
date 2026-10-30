"""All configuration comes from environment variables (set via .env + docker compose).
No credentials are written in source code."""
import os

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "business_analytics")

# The app (dashboard + AI) connects ONLY with the read-only role.
RO_DB_USER = os.getenv("RO_DB_USER", "analytics_ro")
RO_DB_PASSWORD = os.getenv("RO_DB_PASSWORD", "")

# LLM settings (provider-independent: "anthropic" or "openai").
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

AI_MAX_ROWS = int(os.getenv("AI_MAX_ROWS", "200"))     # LIMIT applied to AI queries
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "2"))  # SQL regeneration attempts
STATEMENT_TIMEOUT_MS = int(os.getenv("STATEMENT_TIMEOUT_MS", "5000"))
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "15"))

# Business rule: which order statuses count as recognised revenue.
REVENUE_STATUSES = ("processing", "shipped", "delivered")


def llm_configured() -> bool:
    if LLM_PROVIDER == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    if LLM_PROVIDER == "openai":
        return bool(OPENAI_API_KEY)
    return False
