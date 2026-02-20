"""Scoring functions for the sema4-demo evals."""

import hashlib
import json
import re


def pass_at_k(rewards: list[float]) -> float:
    """Standard pass@k: fraction of K trials that succeeded."""
    if not rewards:
        return 0.0
    return sum(rewards) / len(rewards)


def pass_exp_k(rewards: list[float]) -> float:
    """Sierra pass^k metric: 1.0 only if ALL trials succeeded."""
    if not rewards:
        return 0.0
    return 1.0 if all(r == 1.0 for r in rewards) else 0.0


def sql_correctness(output, expected, **kwargs) -> float:
    """
    Score SQL agent output against expected results.

    Accepts output as:
      - dict with 'result' key containing query result string
      - plain string (raw result)

    Accepts expected as:
      - dict with 'expected_result_hash' key
      - dict with 'expected_sql' key (falls back to structural comparison)
      - None (returns 0.5 if the agent produced any non-empty result)
    """
    if output is None:
        return 0.0

    # Extract result string from agent output dict
    if isinstance(output, dict):
        result_str = output.get("result", "")
        sql_str = output.get("sql", "")
        error = output.get("error")
        if error:
            return 0.0
    else:
        result_str = str(output)
        sql_str = ""

    if not result_str or not result_str.strip():
        return 0.0

    # If expected has a result hash, compare against it
    if isinstance(expected, dict) and expected.get("expected_result_hash"):
        result_hash = hashlib.md5(result_str.strip().encode()).hexdigest()
        return 1.0 if result_hash == expected["expected_result_hash"] else 0.0

    # Structural SQL comparison: check key clauses appear
    if isinstance(expected, dict) and expected.get("expected_sql"):
        return _structural_sql_score(sql_str, expected["expected_sql"])

    # No expected — partial credit if we got a non-empty result
    return 0.5 if result_str.strip() else 0.0


def _structural_sql_score(generated: str, expected: str) -> float:
    """
    Rough structural comparison: check that key SQL clauses from expected
    appear in generated (case-insensitive). Returns 0.0–1.0.
    """
    if not generated:
        return 0.0

    gen_upper = generated.upper()
    exp_upper = expected.upper()

    # Extract table names from expected (words after FROM/JOIN)
    table_pattern = re.compile(r"(?:FROM|JOIN)\s+(\w+)", re.IGNORECASE)
    expected_tables = set(table_pattern.findall(exp_upper))
    generated_tables = set(table_pattern.findall(gen_upper))

    if not expected_tables:
        return 0.5

    table_overlap = len(expected_tables & generated_tables) / len(expected_tables)

    # Check for key structural keywords
    keywords = ["SELECT", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "JOIN"]
    exp_keywords = {kw for kw in keywords if kw in exp_upper}
    gen_keywords = {kw for kw in keywords if kw in gen_upper}

    keyword_score = 1.0
    if exp_keywords:
        keyword_score = len(exp_keywords & gen_keywords) / len(exp_keywords)

    return round((table_overlap * 0.6 + keyword_score * 0.4), 2)
