"""Shared Gemini client, model, and research-agent names."""

import os

from dotenv import load_dotenv
from google import genai

# Load .env from this file's directory so it works regardless of the
# working directory the app is launched from (CLI or Streamlit).
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Ordinary model — used for the structured-findings extraction and the
# name->ticker call. Uses "flash", not "flash-lite": lite mis-applies the
# thousands-separator rules on Vietnamese prose figures (reading "11.232 tỷ"
# as 11.232 not 11232), which flash gets right. Override with RISK_AGENT_MODEL.
MODEL = os.environ.get("RISK_AGENT_MODEL", "gemini-3.6-flash")

# Deep research agent — plans, searches, and synthesizes server-side.
RESEARCH_AGENT = os.environ.get(
    "RISK_AGENT_RESEARCH_AGENT", "deep-research-preview-04-2026"
)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
