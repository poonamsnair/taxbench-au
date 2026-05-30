# Agent Instructions

When asked to run, grade, or report TaxBench-AU, read `skills/taxbench-au/SKILL.md` first.

Keep the evaluation mode explicit: say whether retrieval, web access, tax-database tools, or calculator tools were allowed.

Run a small smoke test before a full 156-question evaluation.

Do not let an answering agent inspect `data/answer.csv` or `data/exam.csv`. Use the runner's default temporary CLI workspace for benchmark runs.

Do not edit `data/*.csv` unless the user explicitly asks to change the dataset.
