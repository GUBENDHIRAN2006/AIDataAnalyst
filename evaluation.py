"""
evaluation.py - Agent Evaluation Framework
===========================================
Provides functions to evaluate agent performance against benchmark questions.

Metrics collected:
- Task completion rate
- Tool-selection accuracy
- Numerical correctness (with tolerance)
- Chart generation correctness
- Error handling success
- Latency (median and P95)
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Benchmark item
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkItem:
    """A single evaluation test case."""

    id: str
    question: str
    expected_tools: list[str]           # Tools we expect the agent to call
    validation_fn: Optional[Callable]   # Function(agent_response) -> bool
    expected_error: bool = False        # True if this question should produce an error
    description: str = ""


@dataclass
class EvalResult:
    """Result of running a single benchmark item."""

    item_id: str
    question: str
    passed: bool
    latency_ms: float
    tools_called: list[str]
    expected_tools: list[str]
    tool_selection_correct: bool
    error_message: Optional[str] = None
    validation_detail: str = ""


@dataclass
class EvalReport:
    """Summary of a full evaluation run."""

    results: list[EvalResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def completion_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total * 100

    @property
    def tool_accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        correct = sum(1 for r in self.results if r.tool_selection_correct)
        return correct / self.total * 100

    @property
    def median_latency_ms(self) -> float:
        latencies = [r.latency_ms for r in self.results]
        return statistics.median(latencies) if latencies else 0.0

    @property
    def p95_latency_ms(self) -> float:
        latencies = sorted(r.latency_ms for r in self.results)
        if not latencies:
            return 0.0
        idx = math.ceil(0.95 * len(latencies)) - 1
        return latencies[max(0, idx)]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "completion_rate_pct": round(self.completion_rate, 1),
            "tool_accuracy_pct": round(self.tool_accuracy, 1),
            "median_latency_ms": round(self.median_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "results": [
                {
                    "id": r.item_id,
                    "question": r.question,
                    "passed": r.passed,
                    "latency_ms": r.latency_ms,
                    "tools_called": r.tools_called,
                    "expected_tools": r.expected_tools,
                    "tool_selection_correct": r.tool_selection_correct,
                    "error_message": r.error_message,
                    "validation_detail": r.validation_detail,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def check_numeric_answer(response, expected: float, tolerance: float = 0.01) -> bool:
    """
    Check if the agent's answer contains the expected numeric value
    within a relative tolerance.
    """
    answer_text = response.answer or ""
    # Extract numbers from answer text
    import re
    numbers = re.findall(r"[\d,]+\.?\d*", answer_text.replace(",", ""))
    for num_str in numbers:
        try:
            val = float(num_str.replace(",", ""))
            if expected == 0:
                if abs(val) < 1e-9:
                    return True
            elif abs(val - expected) / abs(expected) <= tolerance:
                return True
        except ValueError:
            continue
    return False


def check_tool_called(response, tool_name: str) -> bool:
    """Return True if the named tool was called in the agent response."""
    return any(
        tc.get("name") == tool_name
        for tc in (response.tool_calls_made or [])
    )


def check_no_error(response) -> bool:
    """Return True if the agent completed without an error."""
    return response.error is None


def check_tables_returned(response, min_tables: int = 1) -> bool:
    """Return True if the agent returned at least min_tables tables."""
    return len(response.tables) >= min_tables


def check_charts_returned(response, min_charts: int = 1) -> bool:
    """Return True if the agent returned at least min_charts charts."""
    return len(response.charts) >= min_charts


def check_answer_contains(response, keyword: str) -> bool:
    """Return True if the answer contains the keyword (case-insensitive)."""
    return keyword.lower() in (response.answer or "").lower()


# ---------------------------------------------------------------------------
# Benchmark loader
# ---------------------------------------------------------------------------


def load_benchmark_jsonl(path: str) -> list[dict]:
    """Load benchmark items from a JSONL file."""
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------


def run_benchmark(
    benchmark_items: list[BenchmarkItem],
    agent_fn: Callable,
    dataset_info,
) -> EvalReport:
    """
    Run the agent against all benchmark items and collect results.

    Parameters
    ----------
    benchmark_items : list[BenchmarkItem]
        The test cases to run.
    agent_fn : Callable
        Function(question, dataset_info) -> AgentResponse
    dataset_info : DatasetInfo
        Loaded dataset to analyse.
    """
    report = EvalReport()

    for item in benchmark_items:
        logger.info("Evaluating: [%s] %s", item.id, item.question)
        start = time.time()

        try:
            response = agent_fn(item.question, dataset_info)
            latency_ms = round((time.time() - start) * 1000, 1)

            tools_called = [tc.get("name") for tc in (response.tool_calls_made or [])]
            tool_correct = (
                all(t in tools_called for t in item.expected_tools)
                if item.expected_tools else True
            )

            # Run validation function
            passed = False
            detail = ""
            if item.expected_error:
                passed = response.error is not None
                detail = f"Expected error. Got error: {response.error is not None}"
            elif item.validation_fn:
                try:
                    passed = item.validation_fn(response)
                    detail = "Validation passed" if passed else "Validation failed"
                except Exception as exc:  # noqa: BLE001
                    passed = False
                    detail = f"Validation exception: {exc}"
            else:
                passed = response.error is None
                detail = "No error" if passed else f"Error: {response.error}"

            result = EvalResult(
                item_id=item.id,
                question=item.question,
                passed=passed,
                latency_ms=latency_ms,
                tools_called=tools_called,
                expected_tools=item.expected_tools,
                tool_selection_correct=tool_correct,
                validation_detail=detail,
            )

        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.time() - start) * 1000, 1)
            logger.exception("Exception evaluating item %s", item.id)
            result = EvalResult(
                item_id=item.id,
                question=item.question,
                passed=False,
                latency_ms=latency_ms,
                tools_called=[],
                expected_tools=item.expected_tools,
                tool_selection_correct=False,
                error_message=str(exc),
                validation_detail="Exception during evaluation",
            )

        report.results.append(result)
        status = "✅ PASS" if result.passed else "❌ FAIL"
        logger.info("%s [%s] %.0f ms", status, item.id, result.latency_ms)

    return report
