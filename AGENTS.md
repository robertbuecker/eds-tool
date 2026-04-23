# EDS Tool Repo Notes

## Required Onboarding

At the start of every new session, read:

- `PROGRAM_STRUCTURE.md` for current architecture and implementation rules.
- `FITTING_TESTS.md` before changing fitting, refinement, background modeling,
  or HyperSpy/exSpy model handling.
- `tests/TESTS.md` before adding or editing tests.

Update `PROGRAM_STRUCTURE.md` after completing each major feature or design
change, and before every commit/push. Update `FITTING_TESTS.md` when fitting
strategy or fitting diagnostics change. Update `tests/TESTS.md` when tests are
added, removed, renamed, or materially changed.

## Script Execution Wrapper

Python and project scripts must run in the `eds-mini` conda environment. Use
`scripts/with-eds-mini.ps1` instead of `conda run`.

Why:

- Codex shell commands run in fresh PowerShell processes, so conda activation
  does not persist across calls.
- This PowerShell host starts with execution policy `Restricted`, which blocks
  the conda hook unless the process policy is relaxed first.
- In this sandbox, `exspy` import is reliable only when `NUMBA_CACHE_DIR` points
  inside the repository.

Examples:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python -c "import sys; print(sys.executable)"
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python eds_tool.py grain1_thin.eds
```

For non-Python read-only commands such as `git status`, `rg`, or
`Get-ChildItem`, the wrapper is optional.

## Implementation Rules

- Keep business logic out of `eds_tool.py`; put fitting/session behavior in
  `eds_session.py` or `eds_fit_protocol.py`.
- Fit/model diagnostics must use CPS-normalized `_fit_signal`, not display
  signals and not raw counts.
- Keep raw source spectra immutable. Display/export source modes must not change
  fit input.
- Preserve HyperSpy plot object reuse. Do not redraw/recreate plots unless there
  is a clear reason; HyperSpy plots are dynamic and expensive to rebuild.
- For fitting changes, record or inspect runtime, per-step `nfev`, final
  `chi2r`, and low-energy between-peak residuals.
- Avoid broad one-off fitting branches in `EDSSpectrumRecord`; prefer the clean
  protocol helper in `eds_fit_protocol.py`.
- Do not use multiprocessing for batch fits unless revalidated. Windows process
  startup and scientific-stack imports have been slower than the work saved.
- Keep test output and documentation ASCII unless non-ASCII is explicitly
  needed. The Windows console may fail on checkmarks and other symbols.

## Testing

Tests live in `tests` and are documented in `tests/TESTS.md`.

Core commands after fitting/background/session changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fit_protocol_module.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_refinement_stability.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_parallel_batch_fit.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_bg_handling.py
```

Run narrower tests when the change is clearly scoped, but document what was not
run in the final response.

## Auto Workflow

A non-GUI automatic workflow for embedding into external programs is in
progress. See `AUTO_WORKFLOW_README.md`. Update it when changing automatic
workflow behavior.

## Distribution

The application is packaged with PyInstaller. Relevant files:

- `rebuild.bat`
- `eds_tool_folder.spec`
- `OPTIMIZATION_SUMMARY.md`
