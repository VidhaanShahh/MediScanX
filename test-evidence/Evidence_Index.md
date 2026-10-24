# Evidence Index — MediScanX Comprehensive Test Artifacts

This directory contains verified execution artifacts, test outputs, environment configuration, and updated test sheets for the MediScanX Multimodal AI Diagnostic System.

## Directory Contents

| File | Type | Description |
|---|---|---|
| `MediScanX_Test_Case_Sheet.csv` | CSV | Synchronized copy of the authoritative 59-test case sheet with actual observed execution results and statuses |
| `Testing_Summary.md` | Markdown | Comprehensive summary of test counts, execution metrics, pass/fail/blocked ratios, and phase breakdown |
| `Unit_Test_Report.txt` | Raw Text | Pytest terminal output for unit test suites (M1–M4, M5, M6, Integrity) |
| `Integration_Test_Report.txt` | Raw Text | Pytest terminal output for integration test suites (Core CS, M7 Fusion, M8 Explainability, M9 Reports, M10 Audit) |
| `Backend_Test_Report.txt` | Raw Text | Complete backend test suite execution output (108 tests executed, 108 passed) |
| `Frontend_Build_Report.txt` | Raw Text | Next.js 16 production build output confirming TypeScript compilation and static page generation |
| `Security_Test_Report.md` | Markdown | Detailed findings for authentication, object-level authorization (403), SHA-256 integrity, SQLi, and XSS defenses |
| `Performance_Test_Report.md` | Markdown | Measured latency benchmarks (SHA-256 hashing, CXR preprocessing, ECG preprocessing, API health, memory footprint) |
| `Model_Evaluation_Report.md` | Markdown | Evaluation report detailing model architectures, subset metrics, and explicit documentation of held-out set limitations |
| `Defect_Log.csv` | CSV | Tracking table of defects, root causes, small safe corrections, and regression test citations |
| `Execution_Environment.md` | Markdown | Host system configuration, operating system, and runtime tool versions (Python, Node, PyTorch, FastAPI, Next.js) |
| `Evidence_Index.md` | Markdown | This index document mapping all generated evidence artifacts |
