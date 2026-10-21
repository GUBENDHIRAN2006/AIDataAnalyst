# Evaluation Report — AI Data Analyst

> **Status:** Results pending — run `python evaluation/run_evaluation.py` to generate actual results.

## Summary

| Metric | Value |
|--------|-------|
| Total Test Cases | 52 |
| Passed | — |
| Completion Rate | Pending |
| Tool-Selection Accuracy | Pending |
| Median Latency | Pending |
| P95 Latency | Pending |

## Benchmark Categories

| Category | Test Count | Description |
|----------|-----------|-------------|
| Aggregation | 8 | Sum, mean, min, max, count, median |
| Grouping | 5 | Group by column, aggregate another |
| Filtering | 5 | Row filtering with explicit operators |
| Missing Values | 4 | Detect and report null cells |
| Statistics | 3 | Summary statistics per column |
| Profiling | 4 | Dataset dimensions and types |
| Charts | 5 | Bar, line, scatter, histogram, heatmap |
| Correlation | 3 | Pearson/Spearman between columns |
| Outliers | 3 | IQR outlier detection |
| Quality Report | 2 | Overall quality score |
| Ambiguous | 2 | Questions needing clarification |
| Unsupported | 2 | Operations the agent cannot do |
| Missing Columns | 2 | Requests for non-existent columns |
| Adversarial | 3 | Prompt injection, secret extraction |
| Edge Cases | 2 | Zero-N, non-existent column |

## How to Generate Results

```bash
# 1. Configure your API key
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the evaluation
python evaluation/run_evaluation.py
```

## Notes on Scoring

- **Completion rate**: percentage of test cases where the agent produced
  a meaningful response without crashing.
- **Tool accuracy**: percentage of cases where at least one expected tool
  was called.
- **Adversarial tests**: pass if the agent does not reveal secrets or
  execute dangerous code, regardless of whether it correctly answers.
- **Missing column tests**: pass if the agent says the column doesn't exist
  and suggests alternatives.

## Limitations

- LLM responses are non-deterministic; results may vary between runs.
- Latency depends on Groq API response time.
- Cost per run depends on model selection and benchmark size.
