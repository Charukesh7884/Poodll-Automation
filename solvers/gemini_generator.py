import os
import re
import json
import urllib.request
import urllib.error
from config import Config


def generate_speech_paragraph(topic: str, mandatory_words: list[str], target_words: int = 100, full_context: str = "") -> str:
    """
    Generates a natural, spoken paragraph about `topic` incorporating all `mandatory_words`.
    Uses Gemini API if GEMINI_API_KEY is available in .env/Config,
    otherwise uses an intelligent local template synthesizer.
    """
    api_key = Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "").strip()

    if api_key:
        print(f"[Gemini] Contacting Gemini API to compose speech paragraph for topic: '{topic}'...")
        try:
            return _call_gemini_api(api_key, topic, mandatory_words, target_words, full_context)
        except Exception as e:
            print(f"[Gemini Warning] API call failed: {e}. Falling back to local synthesizer.")

    print("[Gemini] No GEMINI_API_KEY or fallback triggered. Using local paragraph synthesizer.")
    return _local_synthesize(topic, mandatory_words, target_words)


def _call_gemini_api(api_key: str, topic: str, mandatory_words: list[str], target_words: int, full_context: str = "") -> str:
    # Build prompt
    # Clean mandatory words
    clean_words = []
    for w in mandatory_words:
        cw = w.replace("\ufffd", "'").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").strip()
        if cw:
            clean_words.append(cw)

    words_str = ", ".join(f'"{w}"' for w in clean_words) if clean_words else "relevant terminology"
    context_section = f"Activity Page Details:\n{full_context.strip()[:1500]}\n\n" if full_context and full_context.strip() else ""

    prompt = (
        f"You are a student speaking for an academic evaluation.\n"
        f"Topic: {topic}\n"
        f"{context_section}"
        f"Target length: exactly around {target_words} words (between {max(50, target_words - 15)} and {target_words + 20} words).\n"
        f"Mandatory words and phrases that MUST be included verbatim: {words_str}.\n\n"
        f"Instructions:\n"
        f"1. Write a single, fluent, coherent spoken paragraph discussing the topic.\n"
        f"2. Every mandatory word and phrase listed above MUST be included in the text.\n"
        f"3. Do NOT include bullet points, headings, labels, introductory remarks, or surrounding quotes.\n"
        f"4. Output ONLY the raw spoken paragraph text ready to be read aloud."
    )

    # Models confirmed active and responsive on this API key
    candidate_models = [
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
    ]

    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.5,
                "maxOutputTokens": 600
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "").strip()
                        text = re.sub(r"[\*#_`]", "", text)
                        clean_result = " ".join(text.split())
                        if len(clean_result.split()) >= 30:
                            print(f"[Gemini] Successfully generated {len(clean_result.split())} words using {model_name}.")
                            return clean_result
        except Exception as e:
            print(f"[Gemini Warning] Model {model_name} failed: {e}. Trying next model...")

    raise RuntimeError("All Gemini models failed to generate valid speech paragraph.")


def _local_synthesize(topic: str, mandatory_words: list[str], target_words: int) -> str:
    """Intelligent rule-based paragraph synthesizer for when offline or no API key."""
    clean_topic = topic.replace("SPEAK ABOUT", "").strip().title()
    sentences = [
        f"Today I will discuss the fundamentals of {clean_topic}."
    ]

    # Combine mandatory words in pairs or triplets into coherent sentences
    for i in range(0, len(mandatory_words), 2):
        w1 = mandatory_words[i]
        if i + 1 < len(mandatory_words):
            w2 = mandatory_words[i + 1]
            sentences.append(f"In this context, {w1} plays a central role alongside {w2}.")
        else:
            sentences.append(f"Furthermore, understanding {w1} is essential for optimal behavior.")

    sentences.append(
        f"In conclusion, studying {clean_topic} provides crucial insights into intelligent systems."
    )

    return " ".join(sentences)


def answer_multiple_choice_question(question: str, choices: list[str], single_choice: bool = False) -> list[int]:
    """
    Determines the correct choice indices (0-based) for a question using Gemini API.
    Returns a list of integer indices, e.g. [0] or [0, 1, 2, 3].
    """
    if not choices:
        return []

    api_key = Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[Gemini Warning] No GEMINI_API_KEY available. Defaulting to first choice [0].")
        return [0]

    choices_formatted = "\n".join([f"{i}: {c}" for i, c in enumerate(choices)])
    type_instruction = "Select the single best choice index (0-based)." if single_choice else "Select ALL correct choice indices (0-based)."

    prompt = (
        f"You are an expert academic assistant solving an interactive quiz.\n"
        f"Question: {question}\n\n"
        f"Choices:\n{choices_formatted}\n\n"
        f"Instructions:\n"
        f"1. {type_instruction}\n"
        f"2. Return ONLY a JSON array of integers representing the 0-based indices, for example: [0] or [1, 2].\n"
        f"3. Do NOT include markdown code fences, explanations, or any other text."
    )

    candidate_models = [
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
    ]

    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 100
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        raw_text = parts[0].get("text", "").strip()
                        # Extract JSON array
                        match = re.search(r"\[[\d\s,]*\]", raw_text)
                        if match:
                            indices = json.loads(match.group(0))
                            valid_indices = [idx for idx in indices if isinstance(idx, int) and 0 <= idx < len(choices)]
                            if valid_indices:
                                print(f"[Gemini] Selected answer indices {valid_indices} for question '{question[:40]}...' using {model_name}.")
                                return valid_indices
        except Exception as e:
            print(f"[Gemini Warning] Model {model_name} failed for question answering: {e}. Trying next model...")

    print("[Gemini Warning] All models failed. Defaulting to first choice [0].")
    return [0]


def answer_fill_in_the_blanks(question_context: str, blank_count: int = 1) -> list[str]:
    """
    Determines the correct text words/phrases to fill in blanks using Gemini API.
    Returns a list of strings, one for each blank in sequential order.
    """
    api_key = Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[Gemini Warning] No GEMINI_API_KEY available for fill-in-the-blanks.")
        return [""] * blank_count

    prompt = (
        f"You are an expert academic assistant solving a fill-in-the-blanks exercise.\n"
        f"Context with blanks:\n{question_context}\n\n"
        f"Instructions:\n"
        f"1. Identify the exact word or short phrase that belongs in each blank.\n"
        f"2. There are {blank_count} blank(s) to fill.\n"
        f"3. Return ONLY a JSON array of strings in order, for example: [\"word1\"] or [\"word1\", \"word2\"].\n"
        f"4. Do NOT include explanations, markup, or surrounding text."
    )

    candidate_models = [
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
    ]

    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 200
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        raw_text = parts[0].get("text", "").strip()
                        # Extract JSON array of strings
                        match = re.search(r"\[[\s\S]*?\]", raw_text)
                        if match:
                            parsed = json.loads(match.group(0))
                            if isinstance(parsed, list):
                                str_list = [str(x).strip() for x in parsed]
                                print(f"[Gemini] Filled blanks with {str_list} using {model_name}.")
                                return str_list
        except Exception as e:
            print(f"[Gemini Warning] Model {model_name} failed for fill-in-the-blanks: {e}. Trying next...")

    return [""] * blank_count
