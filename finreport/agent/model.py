"""Shared Gemini client and model name."""

import os

from dotenv import load_dotenv
from google import genai

from finreport import ROOT

# Load .env from the project root (via ROOT) so it works regardless of the
# working directory the app is launched from (CLI or Streamlit).
load_dotenv(os.path.join(ROOT, ".env"))

# The model used for every call: name->ticker, the search synthesis, and the
# writer. Uses "flash" (not "flash-lite"), which follows the number-format
# rules. Override with RISK_AGENT_MODEL.
MODEL = os.environ.get("RISK_AGENT_MODEL", "gemini-3.6-flash")

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
