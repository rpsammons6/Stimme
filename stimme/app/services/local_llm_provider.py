"""
Local LLM Provider — translates via a locally-hosted LLM server
(Ollama, vLLM, or any OpenAI-compatible endpoint).

Pure service layer: no Flet imports, no UI widgets.
"""

import json
import requests


class LocalLLMProvider:
    """Sends translation requests to a local LLM using the
    OpenAI-compatible /v1/chat/completions endpoint."""

    BASE_INSTRUCTIONS = (
        "You are a world-class Philologist and Translator. "
        "You specialize in historical, academic, and philosophical German.\n\n"
        "RULES:\n"
        "1. OUTPUT ONLY MARKDOWN or JSON as requested.\n"
        "2. DO NOT include conversational filler.\n"
        "3. Prioritize the register and vocabulary found in the 'SPECIALIZED CONTEXT'.\n"
        "4. If the researcher provides a 'THEMATIC FOCUS', prioritize that interpretation.\n"
        "5. If providing a technical 'terminus technicus', provide the English "
        "followed by German in [].\n"
        "6. IGNORE obvious OCR noise, page numbers, margin artifacts, or line "
        "numbers. Focus only on the semantic German text.\n"
        "7. If you encounter text fragments like \"124/b\" or similar artifacts "
        "mixed with German text, ignore them and translate only the meaningful "
        "German content.\n"
        "8. Tone: Match the detected emotional signature of the German source.\n"
        "9. When USER CORRECTION context is present for similar passages, prefer "
        "the user's corrected translation style over general context."
    )

    MODE_COMMENTARY = (
        "Return response in RAW JSON format only. Do not use markdown blocks. "
        "Format: {\"translation\": \"...\", \"commentary\": \"...\"}."
    )

    MODE_NO_COMMENTARY = "OUTPUT ONLY THE RAW TRANSLATION STRING. No JSON."

    @classmethod
    def _build_system_prompt(cls, provide_commentary: bool) -> str:
        mode = cls.MODE_COMMENTARY if provide_commentary else cls.MODE_NO_COMMENTARY
        return f"{cls.BASE_INSTRUCTIONS}\n\n{mode}"

    def __init__(self, settings):
        """
        Parameters
        ----------
        settings : SettingsManager
            Used to read endpoint, model, and timeout configuration.
        """
        self.settings = settings

    def translate(
        self,
        text: str,
        model_id: str = None,
        user_instructions: str = "",
        provide_commentary: bool = True,
        log_callback=None,
        cache_control: bool = False,
        api_key: str = None,
        glossary_block: str = "",
    ) -> tuple:
        """Translate *text* via the local LLM server.

        Returns
        -------
        tuple of (str, str | None, dict | None)
            (translation, commentary_or_None, metrics_or_None)
            — matches ``TranslationBrain.translate`` signature.
        """

        def _log(msg: str):
            print(msg)
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass

        endpoint = self.settings.get_local_llm_endpoint()
        model = model_id or self.settings.get_local_llm_model()
        timeout = self.settings.get_local_llm_timeout()

        _log(f"🤖 LOCAL LLM: Using model {model} at {endpoint}")

        # Build user message — mirrors TranslationBrain's user content layout
        parts: list[str] = []
        if glossary_block:
            parts.append(glossary_block)
            _log("📖 LOCAL LLM: Glossary block attached")
        if user_instructions:
            parts.append(f"FOCUS: {user_instructions}")
            _log(f"🎯 LOCAL LLM: Thematic focus — {user_instructions[:80]}")
        parts.append(f"TEXT:\n{text}")
        user_content = "\n".join(parts)

        system_prompt = self._build_system_prompt(provide_commentary)
        mode_label = "JSON (translation + commentary)" if provide_commentary else "raw translation"
        _log(f"⚙️ LOCAL LLM: Mode — {mode_label}")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.3,
        }

        url = f"{endpoint.rstrip('/')}/v1/chat/completions"
        _log(f"📡 LOCAL LLM: Sending request to {url}")

        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            _log(f"❌ LOCAL LLM: Connection failed — {endpoint}")
            raise ConnectionError(
                f"Could not reach local LLM server at {endpoint}: {exc}"
            ) from exc
        except requests.Timeout as exc:
            _log(f"❌ LOCAL LLM: Request timed out after {timeout}s — {endpoint}")
            raise TimeoutError(
                f"Request to local LLM server at {endpoint} timed out "
                f"after {timeout}s: {exc}"
            ) from exc
        except requests.HTTPError as exc:
            _log(f"❌ LOCAL LLM: HTTP error — {exc}")
            raise RuntimeError(
                f"Local LLM server at {endpoint} returned an error: {exc}"
            ) from exc
        except requests.RequestException as exc:
            _log(f"❌ LOCAL LLM: Request failed — {endpoint}: {exc}")
            raise RuntimeError(
                f"Request to local LLM server at {endpoint} failed: {exc}"
            ) from exc

        data = resp.json()
        raw_output = data["choices"][0]["message"]["content"]

        _log("✅ LOCAL LLM: Response received")

        usage = data.get("usage", {})
        in_t = usage.get("prompt_tokens", 0)
        out_t = usage.get("completion_tokens", 0)
        _log(f"📊 LOCAL LLM: Tokens — {in_t} in / {out_t} out (cost: $0.00)")

        metrics = {
            "input_tokens": in_t,
            "output_tokens": out_t,
            "model_used": model,
            "estimated_cost": 0.0,
            "backend": "local",
        }

        if provide_commentary:
            try:
                clean = raw_output.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(clean)
                translation = parsed.get("translation", "")
                commentary = parsed.get("commentary", "")
                _log("📝 LOCAL LLM: Parsed JSON — translation + commentary extracted")
                return translation, commentary, metrics
            except (json.JSONDecodeError, KeyError):
                _log("⚠️ LOCAL LLM: JSON parse failed — returning raw output")
                return raw_output, None, metrics
        else:
            return raw_output, None, metrics
