# Fitting Protocol Design Notes

This document summarizes the fitting approaches evaluated for EDS Tool and the
current recommended implementation. It is written as a design reference for
humans or agents who may need to maintain or rewrite the fitting system.

The implementation described here lives primarily in `eds_fit_protocol.py` and
is called by `EDSSpectrumRecord.fit_model()` and
`EDSSpectrumRecord.fine_tune_model()`.

## Goals

The fitting protocol must:

- Fit typical single spectra in seconds, not tens of seconds.
- Be robust when a batch-wide element list contains elements absent from some
  spectra.
- Keep detector resolution physically plausible without using hard one-off
  patches.
- Fit on CPS, not counts, because reference/background spectra may have
  different live times.
- Keep reference-background modeling separate from signal display choices.
- Preserve one live HyperSpy/exSpy model through staged fitting operations.
- Leave the model in a stable state so later re-fitting after element changes
  continues from a sensible solution.

## Model Structure

The normal `bg_spec` model contains:

- Sample x-ray line components.
- A polynomial baseline.
- A `ScalableFixedPattern` component named `instrument`, built from the
  CPS-normalized reference-background spectrum.

The `bg_elements` model contains:

- Sample x-ray line components.
- Background-element line components.
- A polynomial baseline.

The `none` model contains:

- Sample x-ray line components.
- A polynomial baseline.

The polynomial baseline is a fit component, not the user-facing external
background. Fitted reference-background subtraction only subtracts identifiable
external/reference components.

## Current Chosen Protocol

### Initial Fit

1. Normalize spectrum and reference background to CPS.
2. Build one exSpy model on the CPS signal.
3. Add family lines and the configured polynomial baseline.
4. Add the reference-background fixed pattern in `bg_spec` mode.
5. Set x-ray amplitude lower bounds to zero.
6. Fix x-ray line centers and widths.
7. In `bg_spec`, run a masked reference-background scale prefit:
   - all parameters fixed except `instrument.yscale`
   - `instrument.shift` fixed
   - sample-line windows excluded
8. Run low-energy peak-sum screening up to 4 keV:
   - screen only primary families such as `C_Ka`, `O_Ka`, `F_Ka`, `Fe_La`
   - fix lines with non-positive peak-sum evidence at zero
   - keep positive-evidence lines active
9. Run the bounded initial fit with `optimizer="trf"`:
   - x-ray amplitudes free except screened-zero lines
   - polynomial baseline free
   - reference-background scale free
   - reference-background shift and xscale fixed

### Refinement

1. Re-apply low-energy screening constraints.
2. Calibrate overall energy offset.
3. Run a bounded linear re-fit:
   - x-ray amplitudes free except screened-zero lines
   - polynomial baseline free
   - reference-background scale free
   - offset, resolution, reference-background shift fixed
4. In `bg_spec`, run masked reference-background shift refinement:
   - all parameters fixed except `instrument.shift` and `instrument.yscale`
   - sample-line windows excluded
   - reported chi-square is a masked background-window metric
5. Run another bounded linear re-fit.
6. Run resolution candidate search:
   - capture a model snapshot before resolution trials
   - try `skip`, `mixed_strong`, `low_energy`, and `very_low_energy` candidates
   - for each candidate, twin selected line widths and free only one reference
     width parameter
   - after each trial, run a bounded linear re-fit
   - score by `chi2r + penalty * resolution_excess_eV^2`
   - restore the best candidate state

The explicit `skip` candidate is important. It avoids forcing resolution changes
when the current state is already best.

## Why CPS Is Required

Counts depend on live time. Reference/background spectra are often recorded with
different exposure times than sample spectra. A fitted scale on raw counts would
therefore combine physics and acquisition duration. CPS makes the reference
background an intensive spectrum and keeps the scale meaningful.

Counts are still useful for display/export, but fitting and model diagnostics
must use CPS.

## Low-Energy Peak-Sum Screening

Practical multi-spectrum sessions often use one broad element list for spectra
that are not chemically identical. Low-energy absent elements can destabilize
the fit because their peaks overlap strongly with each other, the reference
background, and the polynomial baseline.

The implemented screening is intentionally conservative:

- Energy range: primary x-ray families up to 4 keV.
- Evidence metric: HyperSpy `get_lines_intensity()` with estimated background
  windows.
- Rule: non-positive evidence is fixed at zero.
- Positive but weak evidence remains active.

This is not a full qualitative peak finder. It only prevents clearly absent
low-energy families from creating poorly conditioned fit dimensions.

Important validation cases:

- `exp_7987` with extra `F` and `S`: `F_Ka` and `S_Ka` are fixed at zero and
  the initial bounded fit stays in a short `nfev` path.
- `exp_7985` with real `F`: `F_Ka` remains active because peak-sum evidence is
  positive.

Once a line is screened in a live model, later refinement and re-fit steps keep
it fixed at zero. This avoids repeat-refinement drift caused by a line becoming
slightly positive after calibration shifts.

## Background Prefit

The masked `instrument.yscale` prefit is retained as an initializer.

It is not a separate user-facing mode and it is not proof that the final
reference-background scale is correct. The subsequent bounded fit can still
adjust the scale. Its practical value is to reduce cases where the polynomial
baseline initially absorbs too much continuum between peaks.

The prefit must:

- Use CPS signals.
- Keep `instrument.shift` fixed.
- Exclude sample-line windows.
- Restore all parameter free/fixed/twin states afterward.

## Polynomial Baseline

The default baseline order is 6. This is high enough to represent smooth
continuum variation in the tested spectra without needing a separate
background-only fitting stage.

Pitfalls:

- The polynomial can compensate for an under-scaled reference background.
- The polynomial can compensate for unsupported low-energy elements.
- A good global `chi2r` can still hide a poor between-peak continuum.

Use low-energy between-peak residual metrics when evaluating changes. The test
suite now reports these metrics in `test_fit_protocol_module.py`.

## Detector Resolution

Detector resolution is physically constrained by the instrument. Broadly freeing
resolution during a full model fit is unstable because width can substitute for
background and amplitude errors.

The current approach avoids hard clamping in the normal path:

- Fit width only in a locked one-parameter step.
- Try a small number of sensible candidate line groups.
- Penalize solutions outside the expected range.
- Keep `skip` if changing resolution does not improve the scored model.

When resolution still leaves the expected range, inspect the model rather than
adding a one-off clamp. Common causes are missing elements, unsupported low
energy lines, poor reference-background scaling, or a bad baseline.

## HyperSpy/exSpy API Pitfalls

The following observations matter for this model shape:

- `fit_background()` is not reliable with polynomial baseline plus
  `ScalableFixedPattern` reference background.
- `calibrate_energy_axis(calibrate="resolution")` cannot be used blindly because
  helper internals can walk non-line components.
- Broad `model.fit()` calls with many nonlinear parameters are slow and
  unstable.
- Helper methods that operate on "all" components can affect polynomial or
  fixed-pattern components.
- `model.store()` / `signal.models.restore()` are safer than manually copying
  component and parameter state.
- Parameter maps and current scalar parameter values can diverge; call
  `assign_current_value_to_all()` when seeding scalar values into a rebuilt
  model.
- `numexpr` thread count is process-global; changes must be protected when
  fitting in threads.

## Parameter Hygiene

Temporary fit stages must restore:

- `free`
- `twin`
- `bmin`
- `bmax`

After any restore or helper call:

- Re-apply amplitude lower bounds.
- Re-apply screened-zero constraints.
- Fix line centers unless explicitly calibrating offset.
- Fix line widths unless explicitly calibrating resolution.
- Keep reference-background xscale fixed.

## Approaches Evaluated and Discarded

### Direct Measured Subtraction Before Fitting

Rejected. It makes the fit depend on a mutable display signal and mixes
acquisition-time scaling, display choices, and model input. Fitting now always
uses raw spectrum data normalized to CPS.

### Free Reference-Background X-Scale

Rejected. It adds a nonlinear degree of freedom with little physical
justification for spectra sharing the same energy calibration.

### Reference-Background Shift in the Initial Fit

Rejected as default. It often worsened stability. The reference-background
shift is fitted later in a masked, local step after the sample spectrum offset
has been calibrated.

### Broad Free Resolution Fit

Rejected. It can create implausible detector resolutions and exaggerated
baselines.

### Hard Resolution Bounds as Main Stabilizer

Rejected as the primary strategy. Bounds hide symptoms but do not explain why
the model wants nonphysical widths. The chosen approach is candidate search with
a soft physical penalty.

### Background-Only `fit_background()`

Rejected for this model shape. It is not robust with the current combination of
polynomial baseline and fixed-pattern reference background.

### Fixed Reference-BG Scale After Prefit

Rejected. Keeping the prefitted scale fixed made final fits slightly worse and
did not solve repeat-refinement drift.

### Naive Peak-Sum Amplitude Seeding

Rejected as a default. Peak-sum values are useful diagnostics, but directly
seeding all amplitudes can distort other spectra. Conservative screening of
clearly absent low-energy lines is safer.

## Performance Diagnostics

Every fitting protocol change should report:

- Wall-clock time per step.
- `nfev` per `model.fit()` call.
- Final `chi2r`.
- Low-energy between-peak residual mean and mean absolute value.
- Resolution and reference-background shift.

Important slow/bad cases:

- `acac/exp_7987.EDS` with extra `F` or `S`.
- `acac/exp_7985.EDS` when `F` is omitted or mishandled.
- `acac/exp_7989.EDS` and `exp_7993.EDS` for baseline/reference-background
  stress.

## Standalone Exploration Script

Use `tests/explore_fitting_protocols.py` for protocol experiments that should
not yet be integrated into the application.

Typical command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 `
  python tests\explore_fitting_protocols.py `
  --protocols offset_bgshift_resolution_search `
  --repeat-cycle `
  --remove-readd
```

The script writes CSV/JSON traces suitable for comparing protocols without
re-running every experiment manually.

## Regression Tests

Primary tests for fitting changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fit_protocol_module.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_refinement_stability.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_parallel_batch_fit.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_bg_handling.py
```

Use `tests/test_fit_protocol_module.py` first when changing
`eds_fit_protocol.py`; it is the most direct check of the standalone helper.

## Reimplementation Checklist

If the fitting system is rewritten, preserve these requirements:

- Fit on CPS signals.
- Keep raw source data immutable.
- Keep display/export source selection out of fit input.
- Keep one live exSpy model where possible.
- Use model snapshots for candidate states.
- Bound x-ray amplitudes at zero.
- Use masked reference-background scale prefit as initialization.
- Use conservative low-energy peak-sum screening.
- Keep reference-background shift out of the initial full fit.
- Use staged offset, linear, masked reference-background shift, linear,
  candidate-resolution refinement.
- Record per-step `nfev`.
- Validate with low-energy between-peak residuals, not only `chi2r`.
