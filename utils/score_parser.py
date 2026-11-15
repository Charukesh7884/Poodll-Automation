"""
Score Parser Utility for Poodle LMS Automation.

Extracts and evaluates numeric grades and percentages from LMS attempt records,
attempt summary tables, and evaluation text blocks.
"""

import re
from typing import Optional


def parse_score_value(score: any) -> Optional[float]:
    """
    Extracts a numeric percentage or score (0 - 100) from various LMS score strings.
    Returns a float (e.g. 85.0, 0.0) or None if no numeric score can be determined.

    Examples:
        - "ACCURACY\\n92" -> 92.0
        - "ACCURACY\\n0" -> 0.0
        - "Accuracy: 0%" -> 0.0
        - "Accuracy: 75% | WPM: 80" -> 75.0
        - "Grade: 0 / 100" -> 0.0
        - "Grade: 0" -> 0.0
        - "Grade: 0.00 / 100.00" -> 0.0
        - "Grade: 8 / 10" -> 80.0
        - "Score: 2/3 (67%)" -> 67.0
        - "16/16 (100%)" -> 100.0
        - "Total Score 100%" -> 100.0
        - "0" -> 0.0
        - "Completed" -> None
    """
    if score is None:
        return None

    s = str(score).strip()
    if not s or s.lower() in ("completed", "pending", "done", "none"):
        return None

    # 1. PoodLL ReadAloud standard ACCURACY block: 'ACCURACY\n92' or 'ACCURACY: 0'
    acc_match = re.search(r"accuracy[:\s\n]*(\d+(?:\.\d+)?)", s, re.IGNORECASE)
    if acc_match:
        return float(acc_match.group(1))

    # 2. Percentage notation: e.g. '80%', '0%', '67.5%'
    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", s)
    if pct_match:
        return float(pct_match.group(1))

    # 3. Ratio notation: e.g. '0 / 100', '8 / 10', '16/16'
    ratio_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:/|out of)\s*(\d+(?:\.\d+)?)", s, re.IGNORECASE)
    if ratio_match:
        num = float(ratio_match.group(1))
        denom = float(ratio_match.group(2))
        if denom > 0:
            return (num / denom) * 100.0

    # 4. Explicit Grade / Marks / Score prefix: e.g. 'Grade: 0', 'Marks: 0.00', 'Score: 75'
    labeled_match = re.search(r"(?:grade|score|marks?|points?)[:\s]+(\d+(?:\.\d+)?)", s, re.IGNORECASE)
    if labeled_match:
        return float(labeled_match.group(1))

    # 5. Pure numeric string: e.g. '0', '0.00', '85'
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)

    # 6. Any number immediately following a colon
    colon_match = re.search(r":\s*(\d+(?:\.\d+)?)", s)
    if colon_match:
        return float(colon_match.group(1))

    return None


def is_passing_readaloud_score(score: any, min_score: float = 80.0) -> bool:
    """Returns True if score meets or exceeds the minimum score threshold."""
    val = parse_score_value(score)
    if val is None:
        return True
    return val >= min_score


def is_passing_solo_score(score: any, min_score: float = 70.0) -> bool:
    """Returns True if score meets or exceeds the minimum score threshold for Solo."""
    val = parse_score_value(score)
    if val is None:
        return True
    return val >= min_score


def extract_live_page_marks(page, act_type: str = "") -> dict:
    """
    Inspects the live Moodle activity or quiz page DOM to extract the actual marks/grade achieved,
    the number of previous attempts, whether an attempt is in progress, and any page-defined passing grade.

    Returns dict:
        {
            "has_attempts": bool,
            "marks_pct": Optional[float],
            "score_str": str,
            "page_pass_threshold": Optional[float],
            "attempts_count": int,
            "is_in_progress": bool
        }
    """
    result = {
        "has_attempts": False,
        "marks_pct": None,
        "score_str": "",
        "page_pass_threshold": None,
        "attempts_count": 0,
        "is_in_progress": False
    }

    try:
        url_lower = page.url.lower()
        main_loc = page.locator("#region-main")
        main_text = main_loc.inner_text() if main_loc.count() > 0 else ""
        main_text_lower = main_text.lower()

        # Check if currently mid-attempt (e.g. stepno, attempt.php, in-progress)
        if any(kw in url_lower for kw in ["attempt.php", "stepno=", "manageattempts.php"]):
            result["is_in_progress"] = True

        # Check for explicit "Grade to pass: X / Y" or "Grade to pass: X%"
        pass_match = re.search(r"grade to pass[:\s]+([\d\.]+(?:\s*(?:/|out of)\s*[\d\.]+)?%?)", main_text, re.IGNORECASE)
        if pass_match:
            p_val = parse_score_value(pass_match.group(1))
            if p_val is not None:
                result["page_pass_threshold"] = p_val

        # 1. Inspect generaltable / quiz attempt summary table
        tables = page.locator("table.generaltable, .quizattemptsummary, .mod_readaloud_attemptsummary, .attempts-table, table.grades").all()
        extracted_scores: list[float] = []
        raw_score_strings: list[str] = []

        for tbl in tables:
            try:
                if not tbl.is_visible():
                    continue
                rows = tbl.locator("tbody tr").all()
                if not rows:
                    continue

                headers = [h.inner_text().strip().lower() for h in tbl.locator("th").all()]
                result["has_attempts"] = True
                result["attempts_count"] += len(rows)

                for r in rows:
                    cells = [c.inner_text().strip() for c in r.locator("td").all()]
                    row_text = " ".join(cells).lower()

                    if "in progress" in row_text:
                        result["is_in_progress"] = True

                    # Search cell by cell for grade/mark/score/accuracy
                    row_grade_found = False
                    row_parts = []
                    for idx, h in enumerate(headers):
                        if idx < len(cells) and cells[idx]:
                            if any(kw in h for kw in ["grade", "mark", "score", "accuracy"]):
                                val = parse_score_value(cells[idx])
                                if val is not None:
                                    extracted_scores.append(val)
                                    row_parts.append(f"{h.capitalize()}: {cells[idx]}")
                                    row_grade_found = True

                    if row_parts:
                        raw_score_strings.append(" | ".join(row_parts))

                    if not row_grade_found:
                        for cell in cells:
                            val = parse_score_value(cell)
                            if val is not None:
                                extracted_scores.append(val)
                                raw_score_strings.append(cell)
                                break
            except Exception:
                pass

        # 2. Check for explicit "Highest grade: X / Y" or "Overall grade: X / Y" or "Final grade"
        summary_grade_match = re.search(
            r"(?:highest grade|overall grade|final grade|your final grade for this (?:quiz|activity) is)[:\s]+([\d\.]+(?:\s*(?:/|out of)\s*[\d\.]+)?%?)",
            main_text,
            re.IGNORECASE
        )
        if summary_grade_match:
            result["has_attempts"] = True
            val = parse_score_value(summary_grade_match.group(1))
            if val is not None:
                extracted_scores.append(val)
                raw_score_strings.insert(0, summary_grade_match.group(0).strip())

        # 3. PoodLL ReadAloud evaluation text blocks
        if "your latest attempt has been received" in main_text_lower or "evaluation is shown below" in main_text_lower:
            result["has_attempts"] = True
            acc_m = re.search(r"accuracy[:\s\n]*(\d+(?:\.\d+)?)", main_text, re.IGNORECASE)
            wpm_m = re.search(r"wpm[:\s\n]*(\d+)", main_text, re.IGNORECASE)
            parts = []
            if acc_m:
                val = float(acc_m.group(1))
                extracted_scores.append(val)
                parts.append(f"Accuracy: {val}%")
            if wpm_m:
                parts.append(f"WPM: {wpm_m.group(1)}")
            if parts:
                raw_score_strings.insert(0, " | ".join(parts))

        # 4. PoodLL Solo evaluation blocks
        if "your speech details" in main_text_lower or "results of your speech below" in main_text_lower or "automatic evaluation" in main_text_lower:
            result["has_attempts"] = True
            pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%", main_text)
            if pct_m:
                val = float(pct_m.group(1))
                extracted_scores.append(val)
                raw_score_strings.insert(0, f"Score: {val}%")
            ratio_m = re.search(r"(\d+)\s*/\s*(\d+)", main_text)
            if ratio_m and not pct_m:
                val = parse_score_value(ratio_m.group(0))
                if val is not None:
                    extracted_scores.append(val)
                    raw_score_strings.insert(0, f"Score: {ratio_m.group(0)}")

        # 5. Results Screen containers (WordCards / HVP)
        results_loc = page.locator("#wordcards-results, #results-inner, .mod_wordcards_congrats, .h5p-interactive-video-endscreen-score")
        if results_loc.count() > 0 and results_loc.first.is_visible():
            result["has_attempts"] = True
            res_txt = results_loc.first.inner_text().strip()
            val = parse_score_value(res_txt)
            if val is not None:
                extracted_scores.append(val)
                raw_score_strings.insert(0, f"Score: {res_txt}")

        # Determine highest achieved score
        if extracted_scores:
            result["has_attempts"] = True
            result["marks_pct"] = max(extracted_scores)
            best_str = raw_score_strings[0] if raw_score_strings else f"{result['marks_pct']:.1f}%"
            result["score_str"] = best_str
        elif result["has_attempts"]:
            result["score_str"] = "Attempt recorded (Grade not parsed)"

    except Exception as e:
        print(f"[Score Parser Warning] Error extracting live page marks: {e}")

    return result


def is_page_score_passing(page, act_type: str = "") -> tuple[bool, str, Optional[float], float]:
    """
    Evaluates live page completion status by comparing extracted marks against the threshold.

    Returns:
        (is_passing: bool, score_str: str, marks_pct: Optional[float], threshold_pct: float)

    Rules:
        - If marks_pct is None or no attempt exists -> (False, score_str, None, threshold) [Must do/solve]
        - If marks_pct >= threshold -> (True, score_str, marks_pct, threshold) [Passing -> Skip]
        - If marks_pct < threshold -> (False, score_str, marks_pct, threshold) [Failing -> Re-Do]
    """
    from config import Config

    page_info = extract_live_page_marks(page, act_type)
    configured_threshold = Config.get_threshold(act_type)

    # If page specifies a strict "Grade to pass", prioritize it if reasonable
    threshold = page_info["page_pass_threshold"] if page_info["page_pass_threshold"] is not None else configured_threshold

    marks_pct = page_info["marks_pct"]
    score_str = page_info["score_str"]

    if page_info["is_in_progress"]:
        # Activity attempt in progress -> must resume and re-do
        return False, score_str or "Attempt in progress", marks_pct, threshold

    if not page_info["has_attempts"] or marks_pct is None:
        return False, score_str or "Not attempted", None, threshold

    is_passing = marks_pct >= threshold
    return is_passing, score_str, marks_pct, threshold

