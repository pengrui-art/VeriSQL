"""
VeriSQL Configuration

Supports multiple LLM providers:
- OpenAI (GPT-4o, GPT-4-turbo)
- DeepSeek (deepseek-chat, deepseek-coder)
- Qwen (qwen-plus, qwen-turbo, qwen-max)
"""

import os
from dotenv import load_dotenv
from typing import Literal

load_dotenv()

# ============== LLM Provider Configuration ==============

# Supported providers
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai, deepseek, qwen
LLM_STREAMING = os.getenv("LLM_STREAMING", "false").lower() == "true"
LLM_STREAMING = False  # override to fix DashScope potential hanging

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")  # Qwen/通义千问

# API Base URLs (OpenAI-compatible)
API_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

# Model names per provider
DEFAULT_MODELS = {
    "openai": {"sql": "gpt-4o", "spec": "gpt-4o"},
    "deepseek": {"sql": "deepseek-chat", "spec": "deepseek-chat"},
    "qwen": {
        "sql": "qwen-plus",
        "spec": "qwen-plus",
    },  # 也可用 qwen-flash, qwen-turbo, qwen-max
}

# Get configured models
SQL_MODEL = os.getenv(
    "SQL_MODEL", DEFAULT_MODELS.get(LLM_PROVIDER, {}).get("sql", "gpt-4o")
)
SPEC_MODEL = os.getenv(
    "SPEC_MODEL", DEFAULT_MODELS.get(LLM_PROVIDER, {}).get("spec", "gpt-4o")
)


# Get the correct API key and base URL
def get_llm_config(provider: str = None):
    """Get LLM configuration for a provider"""
    provider = provider or LLM_PROVIDER

    config = {
        "openai": {
            "api_key": OPENAI_API_KEY,
            "base_url": API_BASE_URLS["openai"],
        },
        "deepseek": {
            "api_key": DEEPSEEK_API_KEY,
            "base_url": API_BASE_URLS["deepseek"],
        },
        "qwen": {
            "api_key": DASHSCOPE_API_KEY,
            "base_url": API_BASE_URLS["qwen"],
        },
    }
    return config.get(provider, config["openai"])


# ============== Verification Configuration ==============

MAX_REPAIR_ITERATIONS = int(os.getenv("MAX_REPAIR_ITERATIONS", "3"))
Z3_TIMEOUT_MS = int(os.getenv("Z3_TIMEOUT_MS", "5000"))
VERIFICATION_MODE = os.getenv("VERIFICATION_MODE", "strict")

# ============== Database Configuration ==============

DEFAULT_DIALECT = os.getenv("DEFAULT_DIALECT", "sqlite")

# ============== Schema Knowledge Base ==============

TEMPORAL_MAPPINGS = {
    "Q1": ("01-01", "03-31"),
    "Q2": ("04-01", "06-30"),
    "Q3": ("07-01", "09-30"),
    "Q4": ("10-01", "12-31"),
    "last_year": ("YEAR_MINUS_1-01-01", "YEAR_MINUS_1-12-31"),
    "this_year": ("CURRENT_YEAR-01-01", "CURRENT_YEAR-12-31"),
}

# Business Rule Templates (common implicit constraints)
IMPLICIT_BUSINESS_RULES = {
    "orders": [
        {
            "field": "status",
            "op": "!=",
            "value": "cancelled",
            "context": "valid orders",
        },
        {
            "field": "status",
            "op": "!=",
            "value": "refunded",
            "context": "completed orders",
        },
    ],
    "products": [
        {"field": "is_active", "op": "==", "value": True, "context": "active products"},
        {
            "field": "status",
            "op": "!=",
            "value": "discontinued",
            "context": "available products",
        },
    ],
    "employees": [
        {
            "field": "is_active",
            "op": "==",
            "value": True,
            "context": "current employees",
        },
    ],
    "customers": [
        {"field": "is_test", "op": "==", "value": False, "context": "real customers"},
    ],
}
