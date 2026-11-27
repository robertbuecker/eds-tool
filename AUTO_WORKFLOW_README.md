# EDS Tool automatic workflow

Run Python through `scripts/with-eds-mini.ps1` in the `eds-mini` environment.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python eds_tool.py --auto --elements C,O,Cu spectra/
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python eds_tool.py --auto --fit --elements C,O,Cu --bg-spectrum background.eds --max-energy 12 spectra/
```

Inputs may be EDS/HSPY files, directories scanned recursively, or explicit CAP
Data Explorer CSVs. Same-stem HSPY snapshots take precedence over EDS files.
CAP columns remain under `Signal.metadata.CAP_Data_Explorer.columns`.
Directory scans do not read unrelated CSVs. Be deliberate about the input list:
`--fit` calibrates on the first loaded spectrum, including a background spectrum
if you explicitly include it in that list.

Without `--fit`, the workflow computes peak sums. With `--fit`, it fits the
first spectrum and refines its energy offset, detector resolution, and reference
background shift. Remaining spectra receive that calibration and are fitted
individually; background scale and line amplitudes remain individual fit values.
A defined/embedded reference selects numerical reference-background fitting;
otherwise fitting uses sample lines and polynomial continuum without an external
background component. All fitting and quality diagnostics use CPS input.

## Saved files

Beside each input spectrum, the workflow writes EMSA, channel CSV, and HSPY,
and PNG/SVG/JPG plots. HSPY preserves raw counts, fit settings/results, embedded
reference and display mode. Existing corresponding outputs are overwritten on
successful saving. `--cps` selects CPS for signal-only exports; model plots
always use CPS. `--max-energy` sets figure X limits, not fitting limits.

Fitted plots contain the actual model and residual, with fit notes below the
axes. When a reference is available, signal/model are shown with the fitted
reference contribution subtracted; the polynomial continuum remains. Otherwise
raw signal, fit and residual are shown. No GUI is opened.

Summed intensities are saved individually and as a combined table in the common
input directory. `--fit` also writes `fitted_intensities.csv`, including fitted
standard errors. Plot/spectrum formats are configured by `AUTO_PLOT_FORMATS` and
`AUTO_SPECTRUM_FORMATS` in `eds_tool.py`.

## Fit rejection

The automatic workflow warns and rejects poor fits rather than silently masking
possible missing elements. Current conservative heuristic limits are:

- At least 100 counts within the fit range; finite model and chi-square.
- Final native reduced chi-square <= 10.
- Significant unexplained positive peaks <= 3% of total positive signal area.
  Channels must exceed both eight Poisson standard deviations and 3% of the
  spectrum maximum, with at least three contiguous channels.
- Negative model area <= 5% of total positive signal area.
- Reference-background excess above measured signal <= 30% of that area.

Initial chi-square and unexplained peaks alone do not prevent first-spectrum
refinement, because calibration can resolve them. Nonphysical initial models
are rejected before refinement. Optimizer calls routed through the fitting
helper have a 200-evaluation budget in auto mode (GUI defaults are unchanged).
These checks identify tested failure modes, not every possible scientific error.

Each attempted spectrum gets `<name>.fit_quality.json`: decisions/reasons,
metrics, fit/refine timings and per-step function-evaluation counts. Low-energy
between-peak residual mean and mean absolute value are also recorded. Rejected
models are cleared. Rejection of the first spectrum cancels the automatic run
before spectrum/image saving, leaving any earlier output files untouched.
A later rejection skips that fitted result and saves the record as unfitted.
Any fit rejection gives exit status 2; successful runs give status 0.

`--fit` requires `--auto`. `--energy-resolution` explicitly overrides detector
resolution; otherwise saved calibration is retained and raw EDS defaults to
128 eV. `--elements` overrides the sample element list.
