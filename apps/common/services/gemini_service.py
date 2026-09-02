import logging
from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are Marmot Copilot, an institutional-grade quantitative trading and derivative intelligence AI. "
    "You assist prop traders, quantitative analysts, and retail traders with market regime detection, "
    "Smart Money Concepts (SMC), 0DTE Gamma exposure, Option Greeks (Delta, Theta, Vega), strategy backtesting, "
    "and risk management. Keep responses analytical, precise, concise, and formatted with markdown."
)


class GeminiAIService:
    """Service to interact with Google Gemini API via official PyPI google-genai SDK."""

    @classmethod
    def generate_chat_response(cls, message: str, history: list = None) -> dict:
        """Send prompt to Gemini 1.5 Flash via google-genai SDK."""
        api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''

        if not api_key:
            return {
                "success": False,
                "reply": "❌ `GEMINI_API_KEY` is missing in settings / `.env`. Please add your key to enable live AI reasoning.",
                "model": "gemini-1.5-flash",
                "is_fallback": False,
                "error": "Missing GEMINI_API_KEY"
            }

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)

            # Build multi-turn contents list
            contents = []
            if history:
                for item in history[-6:]:
                    role = "user" if item.get("role") == "user" else "model"
                    text = item.get("text", "")
                    if text:
                        contents.append(
                            types.Content(
                                role=role,
                                parts=[types.Part.from_text(text=text)]
                            )
                        )

            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=message)]
                )
            )

            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.3,
                top_p=0.85,
                top_k=40,
                max_output_tokens=800,
            )

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=contents,
                config=config,
            )

            reply_text = response.text or ""
            if reply_text:
                return {
                    "success": True,
                    "reply": reply_text,
                    "model": "gemini-3.6-flash",
                    "is_fallback": False
                }

            return {
                "success": False,
                "reply": "⚠️ Gemini returned an empty response.",
                "model": "gemini-3.6-flash",
                "is_fallback": False
            }

        except Exception as e:
            logger.error(f"Error invoking Gemini via google-genai SDK: {str(e)}", exc_info=True)
            return {
                "success": False,
                "reply": f"⚠️ Gemini API Error: {str(e)}",
                "model": "gemini-1.5-flash",
                "is_fallback": False,
                "error": str(e)
            }
