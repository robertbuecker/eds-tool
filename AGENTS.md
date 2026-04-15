# EDS Tool Repo Notes

## General information

A general overview of the program, its scope, architecture, design choices, pitfalls for implementation, etc. is contained in `PROGRAM_STRUCTURE.md`. There is a specific summary for Agents near the end.

**In every new session, read `PROGRAM_STRUCTURE.md` for onboarding. Update `PROGRAM_STRUCTURE.md` after completing each major task and new feature implementation, and/or before every commit/push**.

## Script execution wrapper

Scripts are to be executed in the `eds-mini` conda environment. Use `scripts/with-eds-mini.ps1` for shell commands that execute Python or project scripts in this repository, instead of `conda run`. This will activate the environment and set up further defaults.

Why:
- Codex shell commands run in fresh PowerShell processes, so conda activation does not persist across calls.
- This PowerShell host starts with execution policy `Restricted`, which blocks the conda hook unless the process policy is relaxed first.
- In this sandbox, `exspy` import is reliable only when `NUMBA_CACHE_DIR` points inside the repository.

Examples:
- `powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python -c "import sys; print(sys.executable)"`
- `powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python eds_tool.py grain1_thin.eds`

For non-Python read-only commands such as `git status` or `Get-ChildItem`, the wrapper is optional.

## Testing

Tests are located in `tests` and documented in detail in `tests/TESTS.md`. When creating new tests for features or editing the existing ones, **update this file.**

## Auto Workflow (under development)

A non-GUI program mode with an automatic workflow for embedding into external programs is in progress. See `AUTO_WORKFLOW_README.md` for the current status. Update this file if work is done on the automatic workflows.

## Distribution

The application is packaged using PyInstaller. See `rebuild.bat`, `eds_tool_folder.spec`, `OPTIMIZATION_SUMMARY.md`.