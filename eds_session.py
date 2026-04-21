import os
import sys
import io
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Optional, Any
import numpy as np
import pandas as pd
import hyperspy.api as hs
import exspy
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from exspy.models.edsmodel import _get_sigma, eV2keV, sigma2fwhm

try:
    import numexpr
except ImportError:  # pragma: no cover - HyperSpy falls back to numpy without numexpr.
    numexpr = None


@contextmanager
def _small_signal_numexpr():
    """
    HyperSpy evaluates many small 1D component arrays during EDS fitting.
    For ~4k-channel spectra, numexpr's default multi-threading overhead is
    much slower than a single worker.
    """
    if numexpr is None:
        yield
        return

    previous_threads = numexpr.set_num_threads(1)
    try:
        yield
    finally:
        numexpr.set_num_threads(previous_threads)


RESOLUTION_MIN_EV = 127.0
RESOLUTION_MAX_EV = 130.0
BACKGROUND_WINDOW_SIGMA = (4.0, 3.0)
DEFAULT_FIT_MIN_KEV = 0.2
DEFAULT_FIT_MAX_KEV = 40.0
DEFAULT_IGNORE_SAMPLE_HALF_WIDTH_KEV = 0.2
DEFAULT_BACKGROUND_PREFIT_MODE = 'exclude_sample'
DEFAULT_BACKGROUND_POLYNOMIAL_ORDER = 6
EDS_TOOL_STATE_KEY = 'EDS_Tool.state'
EDS_TOOL_STATE_VERSION = 1


def _prefer_hspy_path(path: str) -> str:
    candidate = Path(path)
    if candidate.suffix.lower() == '.eds':
        hspy_candidate = candidate.with_suffix('.hspy')
        if hspy_candidate.exists():
            return str(hspy_candidate)
    return str(candidate)


def _dedupe_preferred_spectrum_paths(paths: List[str]) -> List[str]:
    preferred: Dict[str, str] = {}
    for raw_path in paths:
        path = Path(_prefer_hspy_path(raw_path)).resolve()
        key = str(path.with_suffix('')).lower()
        current = preferred.get(key)
        if current is None:
            preferred[key] = str(path)
            continue
        if Path(path).suffix.lower() == '.hspy':
            preferred[key] = str(path)
    return list(preferred.values())

class EDSSpectrumRecord:
    def __init__(self, path: str):
        self.path = _prefer_hspy_path(path)
        self.bg_file: Optional[str] = None
        self._signal = hs.load(self.path)
        self._signal.metadata.set_item('General.title', os.path.splitext(os.path.basename(path))[0])
        self._signal.metadata.set_item('General.original_filename', self.path)
        self._signal.metadata.set_item('Signal.quantity', 'X-rays (Counts)')
        
        # Set default energy resolution to 128 eV (instead of HyperSpy's default of 133 eV)
        self._signal.set_microscope_parameters(energy_resolution_MnKa=128)
        
        self._background: Optional[exspy.signals.EDSTEMSpectrum] = None
        self._background_fit_signal: Optional[exspy.signals.EDSTEMSpectrum] = None
        self._bg_correction_active = False
        self.signal_unit: str = 'counts'
        self.display_signal_mode: str = 'raw'
        self.peak_sum_signal_mode: str = 'raw'
        self.bg_correction_mode: str = 'none'  # Legacy compatibility summary
        self._fit_signal = self._signal.deepcopy()
        self.signal = self._signal.deepcopy()
        self.model: Optional[exspy.models.EDSTEMModel] = None
        self.intensities: Optional[List[hs.BaseSignal]] = None
        self.fitted_intensities: Optional[List[hs.BaseSignal]] = None
        
        # New background handling attributes
        self.bg_elements: List[str] = []  # Elements from BG (instrument, holder, etc.)
        self.bg_fit_mode: str = 'bg_spec'  # 'none', 'bg_elements' or 'bg_spec'
        self.background_prefit_mode: str = 'off'  # 'off', 'exclude_sample', 'bg_elements_only'
        self.background_polynomial_order: int = 6
        
        # Fitted signals (computed after fitting for efficiency)
        self.fitted_reference_clean_signal: Optional[exspy.signals.EDSTEMSpectrum] = None
        self.fitted_reference_bg_signal: Optional[exspy.signals.EDSTEMSpectrum] = None
        self.signal_clean: Optional[exspy.signals.EDSTEMSpectrum] = None  # Legacy alias
        self.signal_bg: Optional[exspy.signals.EDSTEMSpectrum] = None  # Legacy alias
        self.reduced_chisq: Optional[float] = None  # Reduced chi-square from fit
        raw_axis = self._signal.axes_manager.signal_axes[0]
        self._default_energy_offset = raw_axis.offset
        self._default_energy_scale = raw_axis.scale
        self._default_energy_resolution = self._signal.metadata.get_item(
            'Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa',
            default=128,
        )
        self.reference_bg_shift = 0.0
        self.fit_energy_min_keV = DEFAULT_FIT_MIN_KEV
        self.fit_energy_max_keV = DEFAULT_FIT_MAX_KEV
        self.reference_bg_ignore_sample_half_width_keV = DEFAULT_IGNORE_SAMPLE_HALF_WIDTH_KEV
        self._sync_fit_signal_from_raw()
        self._refresh_display_signal_cache()
        self._restore_from_saved_state_if_present()

    @property
    def name(self) -> str:
        return self._signal.metadata.get_item('General.title', default=os.path.basename(self.path))

    @property
    def elements(self) -> List[str]:
        return self._signal.metadata.get_item('Sample.elements', default=[])

    def _sync_legacy_bg_correction_mode(self):
        if self.display_signal_mode == self.peak_sum_signal_mode:
            mapping = {
                'raw': 'none',
                'measured_bg_subtracted': 'subtract_spectra',
                'fitted_reference_bg_subtracted': 'subtract_fitted',
            }
            self.bg_correction_mode = mapping[self.display_signal_mode]
        else:
            self.bg_correction_mode = 'mixed'
        self._bg_correction_active = self.display_signal_mode != 'raw' or self.peak_sum_signal_mode != 'raw'

    def _format_quantity(self, unit: str, mode: str) -> str:
        suffix_map = {
            'raw': '',
            'measured_bg_subtracted': ', Measured BG Subtracted',
            'fitted_reference_bg_subtracted': ', Fitted Reference BG Subtracted',
        }
        return f"X-rays ({unit.capitalize()}{suffix_map[mode]})"

    def _get_live_time_or_raise(self, signal) -> float:
        live_time = self.get_live_time(signal)
        if live_time is None or live_time == 0:
            raise ValueError(f"Live time missing or zero for spectrum '{self.name}'")
        return live_time

    def _copy_calibration(self, source_signal, target_signal):
        source_axis = source_signal.axes_manager.signal_axes[0]
        target_axis = target_signal.axes_manager.signal_axes[0]
        target_axis.offset = source_axis.offset
        target_axis.scale = source_axis.scale
        source_resolution = source_signal.metadata.get_item(
            'Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa',
            default=None,
        )
        if source_resolution is not None:
            target_signal.set_microscope_parameters(energy_resolution_MnKa=source_resolution)

    def _set_signal_calibration(self, signal, offset=None, scale=None, resolution=None):
        axis = signal.axes_manager.signal_axes[0]
        if offset is not None:
            axis.offset = offset
        if scale is not None:
            axis.scale = scale
        if resolution is not None:
            signal.set_microscope_parameters(energy_resolution_MnKa=resolution)

    def _sync_signal_proxy(self, target_signal, source_signal):
        self._copy_calibration(source_signal, target_signal)
        target_signal.data = source_signal.data.copy()
        target_signal.metadata.set_item(
            'Signal.quantity',
            source_signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)'),
        )
        target_signal.metadata.set_item(
            'Sample.elements',
            list(source_signal.metadata.get_item('Sample.elements', default=[])),
        )

    def _make_cps_signal(self, source_signal):
        cps_signal = source_signal.deepcopy()
        live_time = self._get_live_time_or_raise(source_signal)
        cps_signal.data = source_signal.data / live_time
        cps_signal.metadata.set_item('Signal.quantity', 'X-rays (CPS)')
        return cps_signal

    def _sync_fit_signal_from_raw(self):
        fit_signal = self._make_cps_signal(self._signal)
        self._sync_signal_proxy(self._fit_signal, fit_signal)

    def _sync_raw_signal_from_fit(self):
        self._copy_calibration(self._fit_signal, self._signal)
        if self.signal is not None:
            self._copy_calibration(self._fit_signal, self.signal)

    def _restore_default_calibration(self):
        self._set_signal_calibration(
            self._signal,
            offset=self._default_energy_offset,
            scale=self._default_energy_scale,
            resolution=self._default_energy_resolution,
        )
        self._set_signal_calibration(
            self._fit_signal,
            offset=self._default_energy_offset,
            scale=self._default_energy_scale,
            resolution=self._default_energy_resolution,
        )
        if self.signal is not None:
            self._set_signal_calibration(
                self.signal,
                offset=self._default_energy_offset,
                scale=self._default_energy_scale,
                resolution=self._default_energy_resolution,
            )

    def _serialize_signal_payload(self, signal):
        axis = signal.axes_manager.signal_axes[0]
        return {
            'data': np.asarray(signal.data, dtype=float).tolist(),
            'offset': float(axis.offset),
            'scale': float(axis.scale),
            'resolution': self.get_energy_resolution(signal),
            'live_time': self.get_live_time(signal),
            'quantity': signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)'),
            'title': signal.metadata.get_item('General.title', default=''),
            'original_filename': signal.metadata.get_item('General.original_filename', default=''),
        }

    def _deserialize_signal_payload(self, payload):
        signal = exspy.signals.EDSTEMSpectrum(np.asarray(payload['data'], dtype=float))
        axis = signal.axes_manager.signal_axes[0]
        axis.offset = float(payload.get('offset', 0.0))
        axis.scale = float(payload.get('scale', 1.0))
        resolution = payload.get('resolution')
        if resolution is not None:
            signal.set_microscope_parameters(energy_resolution_MnKa=float(resolution))
        live_time = payload.get('live_time')
        if live_time is not None:
            signal.metadata.set_item('Acquisition_instrument.TEM.Detector.EDS.live_time', float(live_time))
        signal.metadata.set_item('Signal.quantity', payload.get('quantity', 'X-rays (Counts)'))
        signal.metadata.set_item('General.title', payload.get('title', self.name))
        original_filename = payload.get('original_filename')
        if original_filename:
            signal.metadata.set_item('General.original_filename', original_filename)
        return signal

    def _serialize_model_state(self):
        if self.model is None:
            return None
        components = []
        for component in self.model:
            params = []
            for param in component.parameters:
                twin = getattr(param, 'twin', None)
                params.append({
                    'name': param.name,
                    'value': float(param.value),
                    'free': bool(param.free),
                    'bmin': None if param.bmin is None else float(param.bmin),
                    'bmax': None if param.bmax is None else float(param.bmax),
                    'twin_component': getattr(getattr(twin, 'component', None), 'name', None),
                    'twin_parameter': getattr(twin, 'name', None),
                })
            components.append({'name': component.name, 'parameters': params})
        return {
            'reduced_chisq': self.reduced_chisq,
            'components': components,
        }

    def _apply_serialized_model_state(self, state):
        if self.model is None or not state:
            return
        component_map = self._component_map(self.model)
        for component_state in state.get('components', []):
            component = component_map.get(component_state.get('name'))
            if component is None:
                continue
            param_map = {param.name: param for param in component.parameters}
            for param_state in component_state.get('parameters', []):
                param = param_map.get(param_state.get('name'))
                if param is None:
                    continue
                if param.twin is None:
                    param.value = float(param_state.get('value', param.value))
                param.free = bool(param_state.get('free', param.free))
                param.bmin = param_state.get('bmin')
                param.bmax = param_state.get('bmax')
                param.assign_current_value_to_all()
        self._restore_model_state_hygiene()
        self.reduced_chisq = state.get('reduced_chisq')

    def _serialize_state(self):
        fit_axis = self._fit_signal.axes_manager.signal_axes[0]
        return {
            'version': EDS_TOOL_STATE_VERSION,
            'defaults': {
                'offset': float(self._default_energy_offset),
                'scale': float(self._default_energy_scale),
                'resolution': float(self._default_energy_resolution),
            },
            'current_calibration': {
                'offset': float(fit_axis.offset),
                'scale': float(fit_axis.scale),
                'resolution': float(self.get_energy_resolution(self._fit_signal)),
            },
            'settings': {
                'signal_unit': self.signal_unit,
                'display_signal_mode': self.display_signal_mode,
                'peak_sum_signal_mode': self.peak_sum_signal_mode,
                'bg_fit_mode': self.bg_fit_mode,
                'bg_elements': list(self.bg_elements),
                'background_prefit_mode': self.background_prefit_mode,
                'background_polynomial_order': int(self.background_polynomial_order),
                'reference_bg_shift': float(self.reference_bg_shift),
                'fit_energy_min_keV': float(self.fit_energy_min_keV),
                'fit_energy_max_keV': float(self.fit_energy_max_keV),
                'reference_bg_ignore_sample_half_width_keV': float(self.reference_bg_ignore_sample_half_width_keV),
                'bg_file': self.bg_file,
            },
            'background_signal': self._serialize_signal_payload(self._background) if self._background is not None else None,
            'fit_state': self._serialize_model_state(),
        }

    def _tree_to_dict(self, obj):
        if hasattr(obj, 'as_dictionary'):
            return obj.as_dictionary()
        return obj

    def _restore_from_saved_state_if_present(self):
        state = self._tree_to_dict(self._signal.metadata.get_item(EDS_TOOL_STATE_KEY, default=None))
        if not isinstance(state, dict):
            return

        defaults = state.get('defaults', {})
        self._default_energy_offset = float(defaults.get('offset', self._default_energy_offset))
        self._default_energy_scale = float(defaults.get('scale', self._default_energy_scale))
        self._default_energy_resolution = float(defaults.get('resolution', self._default_energy_resolution))

        settings = state.get('settings', {})
        self.bg_elements = list(settings.get('bg_elements', self.bg_elements))
        self.bg_fit_mode = settings.get('bg_fit_mode', self.bg_fit_mode)
        self.background_prefit_mode = settings.get('background_prefit_mode', self.background_prefit_mode)
        self.background_polynomial_order = int(settings.get('background_polynomial_order', self.background_polynomial_order))
        self.reference_bg_shift = float(settings.get('reference_bg_shift', self.reference_bg_shift))
        self.fit_energy_min_keV = float(settings.get('fit_energy_min_keV', self.fit_energy_min_keV))
        self.fit_energy_max_keV = float(settings.get('fit_energy_max_keV', self.fit_energy_max_keV))
        self.reference_bg_ignore_sample_half_width_keV = float(
            settings.get('reference_bg_ignore_sample_half_width_keV', self.reference_bg_ignore_sample_half_width_keV)
        )
        self.bg_file = settings.get('bg_file', self.bg_file)

        background_payload = self._tree_to_dict(state.get('background_signal'))
        if isinstance(background_payload, dict):
            self.set_background(self._deserialize_signal_payload(background_payload))

        current = state.get('current_calibration', {})
        self._set_signal_calibration(
            self._signal,
            offset=current.get('offset'),
            scale=current.get('scale'),
            resolution=current.get('resolution'),
        )
        self._set_signal_calibration(
            self._fit_signal,
            offset=current.get('offset'),
            scale=current.get('scale'),
            resolution=current.get('resolution'),
        )
        self._sync_fit_signal_from_raw()

        self.signal_unit = settings.get('signal_unit', self.signal_unit)
        self.display_signal_mode = settings.get('display_signal_mode', self.display_signal_mode)
        self.peak_sum_signal_mode = settings.get('peak_sum_signal_mode', self.peak_sum_signal_mode)
        self._sync_legacy_bg_correction_mode()

        fit_state = self._tree_to_dict(state.get('fit_state'))
        if isinstance(fit_state, dict):
            self._restore_saved_model(fit_state)
        self._refresh_display_signal_cache()

    def _restore_saved_model(self, fit_state):
        original_elements = self.elements.copy()
        fit_signal = self.get_signal_for_fit()
        if self.bg_fit_mode == 'none':
            self.model = self._make_model(fit_signal, original_elements)
        elif self.bg_fit_mode == 'bg_elements':
            all_elements = original_elements + self.bg_elements
            self.model = self._make_model(fit_signal, all_elements)
        elif self.bg_fit_mode == 'bg_spec':
            if self._background is None:
                return
            self.model = self._make_model(fit_signal, original_elements)
            comp_bg = hs.model.components1D.ScalableFixedPattern(self._background_fit_signal)
            comp_bg.name = 'instrument'
            comp_bg.isbackground = True
            comp_bg.xscale.free = False
            comp_bg.shift.free = False
            comp_bg.shift.value = self.reference_bg_shift
            self.model.append(comp_bg)
            self.model.background_components.append(comp_bg)
        else:
            return

        self._apply_serialized_model_state(fit_state)
        self.fitted_intensities = self.model.get_lines_intensity()
        self._compute_fitted_signals()
        if self.bg_fit_mode == 'bg_elements':
            fit_signal.set_elements(original_elements)
        self._refresh_display_signal_cache()

    def _make_signal_from_counts(self, counts_data, unit: str, mode: str):
        live_time = self._get_live_time_or_raise(self._signal)
        signal = self._signal.deepcopy()
        signal.data = counts_data if unit == 'counts' else counts_data / live_time
        signal.metadata.set_item('Signal.quantity', self._format_quantity(unit, mode))
        return signal

    def _make_signal_from_cps(self, cps_data, unit: str, mode: str):
        live_time = self._get_live_time_or_raise(self._signal)
        signal = self._fit_signal.deepcopy()
        signal.data = cps_data if unit == 'cps' else cps_data * live_time
        signal.metadata.set_item('Signal.quantity', self._format_quantity(unit, mode))
        return signal

    def _get_measured_bg_counts(self):
        if self._background is None:
            raise ValueError(f"Measured background subtraction requires a background spectrum for {self.name}")

        live_time_sig = self._get_live_time_or_raise(self._signal)
        live_time_bg = self._get_live_time_or_raise(self._background)
        scale = live_time_sig / live_time_bg
        return self._signal.data - (self._background.data * scale)

    def _component_element(self, component):
        if hasattr(component, 'element'):
            return component.element
        name = getattr(component, 'name', '')
        if '_' in name:
            return name.split('_', 1)[0]
        return None

    def _component_map(self, model):
        if model is None:
            return {}
        return {component.name: component for component in model}

    def _is_sample_line_component(self, component) -> bool:
        return getattr(component, 'isbackground', None) is False and self._component_element(component) in self.elements

    def _is_xray_line_component(self, component) -> bool:
        return getattr(component, 'isbackground', None) is False and hasattr(component, 'sigma')

    def _get_fit_range_bounds(self, signal=None):
        signal = signal or self._fit_signal
        axis = signal.axes_manager.signal_axes[0]
        low = max(axis.low_value, float(self.fit_energy_min_keV))
        high = min(axis.high_value, float(self.fit_energy_max_keV))
        if high <= low:
            raise ValueError(
                f"Invalid fit energy range for {self.name}: lower={low:.3f} keV, upper={high:.3f} keV"
            )
        return low, high

    @contextmanager
    def _temporary_model_signal_range(self, model, exclude_sample_half_width: float = 0.0, mask=None):
        if model is None:
            yield
            return

        previous_mask = np.copy(getattr(model, '_channel_switches', []))
        if mask is not None:
            model.set_signal_range_from_mask(mask)
        else:
            lower, upper = self._get_fit_range_bounds(model.signal)
            model.set_signal_range(lower, upper)
            if exclude_sample_half_width > 0:
                for component in model:
                    if self._is_sample_line_component(component):
                        centre = getattr(component, 'centre', None)
                        if centre is not None:
                            model.remove_signal_range(
                                centre.value - exclude_sample_half_width,
                                centre.value + exclude_sample_half_width,
                            )
        try:
            yield
        finally:
            if len(previous_mask):
                model.set_signal_range_from_mask(previous_mask)

    def has_bg_element_overlap(self) -> bool:
        return bool(set(self.elements) & set(self.bg_elements))

    def can_use_fitted_reference_bg_subtraction(self) -> bool:
        if self.model is None or self.fitted_reference_bg_signal is None:
            return False
        if self.bg_fit_mode == 'bg_spec':
            return True
        if self.bg_fit_mode == 'bg_elements':
            return not self.has_bg_element_overlap()
        return False

    def _validate_signal_mode(self, mode: str):
        valid_modes = ('raw', 'measured_bg_subtracted', 'fitted_reference_bg_subtracted')
        if mode not in valid_modes:
            raise ValueError(f"mode must be one of {valid_modes}")
        if mode == 'measured_bg_subtracted' and self._background is None:
            raise ValueError(f"Measured background subtraction requires a loaded background spectrum for {self.name}")
        if mode == 'fitted_reference_bg_subtracted' and not self.can_use_fitted_reference_bg_subtraction():
            if self.bg_fit_mode == 'bg_elements' and self.has_bg_element_overlap():
                raise ValueError(
                    f"Fitted reference background subtraction is unavailable for {self.name}: "
                    "background elements overlap sample elements."
                )
            raise ValueError(f"Fitted reference background subtraction is unavailable for {self.name}")

    def _normalize_signal_modes(self):
        for attr in ('display_signal_mode', 'peak_sum_signal_mode'):
            mode = getattr(self, attr)
            try:
                self._validate_signal_mode(mode)
            except ValueError:
                setattr(self, attr, 'raw')
        self._sync_legacy_bg_correction_mode()

    def _refresh_display_signal_cache(self):
        self._normalize_signal_modes()
        display_signal = self.get_signal_for_display()
        self._sync_signal_proxy(self.signal, display_signal)

    def set_display_signal_mode(self, mode: str):
        self._validate_signal_mode(mode)
        self.display_signal_mode = mode
        self._sync_legacy_bg_correction_mode()
        display_signal = self.get_signal_for_display()
        self._sync_signal_proxy(self.signal, display_signal)

    def set_peak_sum_signal_mode(self, mode: str):
        self._validate_signal_mode(mode)
        self.peak_sum_signal_mode = mode
        self._sync_legacy_bg_correction_mode()

    def get_signal_for_fit(self):
        return self._fit_signal

    def _get_signal_for_mode(self, mode: str, unit: Optional[str] = None):
        unit = unit or self.signal_unit
        if unit not in ('counts', 'cps'):
            raise ValueError("unit must be 'counts' or 'cps'")

        if mode == 'raw':
            return self._make_signal_from_counts(self._signal.data, unit, mode)
        if mode == 'measured_bg_subtracted':
            return self._make_signal_from_counts(self._get_measured_bg_counts(), unit, mode)
        if mode == 'fitted_reference_bg_subtracted':
            self._validate_signal_mode(mode)
            return self._make_signal_from_cps(self.fitted_reference_clean_signal.data, unit, mode)
        raise ValueError(f"Unknown signal mode: {mode}")

    def get_signal_for_display(self, unit: Optional[str] = None):
        return self._get_signal_for_mode(self.display_signal_mode, unit=unit)

    def get_signal_for_export(self, unit: Optional[str] = None):
        return self.get_signal_for_display(unit=unit)

    def get_signal_for_peak_sum(self, unit: Optional[str] = None):
        return self._get_signal_for_mode(self.peak_sum_signal_mode, unit=unit)

    def uses_model_plot(self) -> bool:
        return self.model is not None and self.display_signal_mode in ('raw', 'fitted_reference_bg_subtracted')

    def _get_reference_bg_data_for_plot(self):
        if self.signal_bg is None:
            return None
        return self.signal_bg._get_current_data()

    def _signal_minus_reference_bg_for_plot(self, **kwargs):
        bg_data = self._get_reference_bg_data_for_plot()
        if bg_data is None:
            return self._fit_signal._get_current_data()
        return self._fit_signal._get_current_data() - bg_data

    def _model_minus_reference_bg_for_plot(self, axes_manager, out_of_range2nans=True):
        model_data = self.model._model2plot(axes_manager, out_of_range2nans=out_of_range2nans)
        bg_data = self._get_reference_bg_data_for_plot()
        if bg_data is None:
            return model_data
        return model_data - bg_data

    def _apply_fitted_reference_bg_subtracted_plot_callbacks(self):
        if self.model is None or self._fit_signal._plot is None:
            return

        signal_plot = self._fit_signal._plot.signal_plot
        if not signal_plot.ax_lines:
            return

        signal_line = signal_plot.ax_lines[0]
        signal_line.data_function = self._signal_minus_reference_bg_for_plot
        signal_line.update(render_figure=False, update_ylimits=False)

        if self.model._model_line is not None:
            self.model._model_line.data_function = self._model_minus_reference_bg_for_plot
            self.model._model_line.update(render_figure=False, update_ylimits=False)

        if self.model._residual_line is not None:
            self.model._residual_line.update(render_figure=False, update_ylimits=False)

        signal_plot.figure.canvas.draw_idle()

    def _get_signal_legend_label(self) -> str:
        return "Signal raw" if self.display_signal_mode == 'raw' else "Signal background-corrected"

    def _apply_plot_legend(self, plot_signal, ax, use_model: bool, show_residual: bool, background_handle=None):
        if plot_signal is None or plot_signal._plot is None:
            return
        signal_plot = plot_signal._plot.signal_plot
        handles = []

        if signal_plot.ax_lines:
            signal_artist = signal_plot.ax_lines[0].line
            signal_artist.set_label(self._get_signal_legend_label())
            handles.append(signal_artist)

            if background_handle is not None:
                background_handle.set_label("Background")
                handles.append(background_handle)

            if use_model and len(signal_plot.ax_lines) >= 2:
                fit_artist = signal_plot.ax_lines[1].line
                fit_artist.set_label("Fit")
                handles.append(fit_artist)
            if use_model and show_residual and len(signal_plot.ax_lines) >= 3:
                residual_artist = signal_plot.ax_lines[2].line
                residual_artist.set_label("Residual")
                handles.append(residual_artist)

        if handles:
            ax.legend(handles=handles, loc='best')

    def get_energy_resolution(self, signal=None) -> float:
        signal = signal or self._fit_signal
        return float(
            signal.metadata.get_item(
                'Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa',
                default=self._default_energy_resolution,
            )
        )

    def _make_model(self, fit_signal, elements):
        fit_signal.set_elements(elements)
        model = fit_signal.create_model(auto_add_lines=True, auto_background=False)
        model.add_family_lines()
        model.add_polynomial_background(order=self.background_polynomial_order)
        return model

    def _iter_background_stage_components(self):
        if self.model is None:
            return []

        components = []
        for component in self.model:
            if self.bg_fit_mode == 'bg_spec' and component.name == 'instrument':
                components.append(component)
                continue
            if getattr(component, 'isbackground', False):
                components.append(component)
                continue
            if self.bg_fit_mode == 'bg_elements':
                element = self._component_element(component)
                if (
                    element in self.bg_elements
                    and element not in self.elements
                    and hasattr(component, 'A')
                    and component.A.twin is None
                ):
                    components.append(component)
        return components

    def _background_prefit_enabled(self) -> bool:
        return self.background_prefit_mode in ('exclude_sample', 'bg_elements_only')

    def _warn(self, message: str):
        warnings.warn(message, RuntimeWarning, stacklevel=2)
        print(f"Warning: {message}")

    def _print_fit_banner(self, action: str):
        print(f"\n=== {action} {self.name} ===")

    def _format_delta_percent(self, current: float, previous: float) -> str:
        if previous == 0:
            return "n/a"
        return f"{((current / previous) - 1) * 100:+.1f}%"

    def _background_prefit_description(self) -> str:
        if self.background_prefit_mode == 'exclude_sample':
            return "Fitting reference background (sample elements excluded)"
        if self.background_prefit_mode == 'bg_elements_only':
            return "Fitting reference background (BG elements only)"
        return "Fitting background components"

    def _make_bg_elements_only_mask(self):
        if self.model is None:
            return None
        axis = self.model.signal.axes_manager.signal_axes[0]
        energies = axis.axis
        lower, upper = self._get_fit_range_bounds(self.model.signal)
        mask = np.zeros_like(energies, dtype=bool)
        usable_components = [
            component
            for component in self._iter_background_stage_components()
            if not getattr(component, 'isbackground', False) and hasattr(component, 'sigma')
        ]
        if not usable_components:
            return None
        for component in usable_components:
            sigma = abs(float(component.sigma.value))
            lo = max(lower, float(component.centre.value) - BACKGROUND_WINDOW_SIGMA[0] * sigma)
            hi = min(upper, float(component.centre.value) + BACKGROUND_WINDOW_SIGMA[1] * sigma)
            mask |= (energies >= lo) & (energies <= hi)
        return mask if np.any(mask) else None

    def _set_component_prefit_state(self, component, free: bool):
        if component.name == 'instrument':
            component.xscale.free = False
            component.shift.free = False
            component.yscale.free = free
            return

        if getattr(component, 'isbackground', False):
            if free:
                component.set_parameters_free()
            else:
                component.set_parameters_not_free()
            return

        if hasattr(component, 'A'):
            component.A.free = free

    def _freeze_background_stage_components(self, components):
        for component in components:
            self._set_component_prefit_state(component, free=False)

    def _run_background_prefit(self):
        if self.model is None or not self._background_prefit_enabled():
            return {'used': False}

        bg_components = self._iter_background_stage_components()
        if not bg_components:
            return {'used': False}

        if self.background_prefit_mode == 'exclude_sample':
            if self.reference_bg_ignore_sample_half_width_keV <= 0:
                self._warn(
                    f"Background prefit is enabled for {self.name}, but 'Ignore sample ±' is 0 keV. "
                    "Skipping the background-only stage."
                )
                return {'used': False}
            mask = None
            exclude_sample_half_width = self.reference_bg_ignore_sample_half_width_keV
        elif self.background_prefit_mode == 'bg_elements_only':
            mask = self._make_bg_elements_only_mask()
            exclude_sample_half_width = 0.0
            if mask is None:
                self._warn(
                    f"Background-elements-only prefit is unavailable for {self.name}: "
                    "no non-overlapping background-element lines are available in range."
                )
                return {'used': False}
        else:
            return {'used': False}

        previous_free = {
            param: param.free
            for component in self.model
            for param in component.parameters
        }
        try:
            for param in previous_free:
                param.free = False
            for component in bg_components:
                self._set_component_prefit_state(component, free=True)

            with _small_signal_numexpr():
                with self._temporary_model_signal_range(
                    self.model,
                    exclude_sample_half_width=exclude_sample_half_width,
                    mask=mask,
                ):
                    self.model.fit()

            for param, was_free in previous_free.items():
                param.free = was_free
            self._freeze_background_stage_components(bg_components)
            info = {
                'used': True,
                'description': self._background_prefit_description(),
                'chi2r': float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data),
            }
            instrument = self._get_instrument_component()
            if instrument is not None:
                info['scale'] = float(instrument.yscale.value)
                info['shift'] = float(instrument.shift.value)
            return info
        finally:
            if self.model is not None:
                self._restore_model_state_hygiene()

    def _get_resolution_reference_component(self, xray_lines='all_alpha'):
        if self.model is None:
            return None
        lines = [component.name for component in self.model.xray_lines] if xray_lines == 'all_alpha' else list(xray_lines)
        if not lines:
            return None
        return self.model[lines[0]]

    def _get_resolution_sigma_bounds(self, reference_component):
        energy_Mn_Ka = self.model.signal._get_line_energy("Mn_Ka", "auto")[0]
        sigma_from_mn = _get_sigma(
            reference_component.centre.value,
            energy_Mn_Ka,
            self.model.units_factor,
            return_f=True,
        )
        sigma_min = sigma_from_mn(RESOLUTION_MIN_EV / eV2keV * self.model.units_factor / sigma2fwhm)
        sigma_max = sigma_from_mn(RESOLUTION_MAX_EV / eV2keV * self.model.units_factor / sigma2fwhm)
        return float(min(sigma_min, sigma_max)), float(max(sigma_min, sigma_max))

    def _calibrate_resolution_with_bounds(self):
        reference_component = self._get_resolution_reference_component()
        if reference_component is None:
            raise ValueError("No X-ray lines available for resolution calibration")

        sigma_min, sigma_max = self._get_resolution_sigma_bounds(reference_component)
        prev_bmin, prev_bmax = reference_component.sigma.bmin, reference_component.sigma.bmax

        try:
            reference_component.sigma.bmin = sigma_min
            reference_component.sigma.bmax = sigma_max
            self.model._twin_xray_lines_width(xray_lines='all_alpha')
            with _small_signal_numexpr():
                with self._temporary_model_signal_range(self.model):
                    self.model.fit(optimizer='trf', bounded=True)
            self.model.fix_xray_lines_width(xray_lines='all_alpha')
            self.model._set_energy_resolution(xray_lines='all_alpha')
            self._restore_model_state_hygiene()
        finally:
            reference_component.sigma.bmin = prev_bmin
            reference_component.sigma.bmax = prev_bmax

        resolution = self.get_energy_resolution(self._fit_signal)
        tol = 1e-6
        hit_bound = None
        if resolution <= RESOLUTION_MIN_EV + tol:
            hit_bound = 'lower'
            self._warn(
                f"Resolution calibration for {self.name} hit the lower bound "
                f"({RESOLUTION_MIN_EV:.2f} eV)."
            )
        elif resolution >= RESOLUTION_MAX_EV - tol:
            hit_bound = 'upper'
            self._warn(
                f"Resolution calibration for {self.name} hit the upper bound "
                f"({RESOLUTION_MAX_EV:.2f} eV)."
            )
        return resolution, hit_bound

    def apply_calibration(self, offset=None, resolution=None, reference_bg_shift=None, refit_model=False):
        if offset is not None:
            self._set_signal_calibration(self._signal, offset=offset)
            self._set_signal_calibration(self._fit_signal, offset=offset)
            if self.signal is not None:
                self._set_signal_calibration(self.signal, offset=offset)
        if resolution is not None:
            self._set_signal_calibration(self._signal, resolution=resolution)
            self._set_signal_calibration(self._fit_signal, resolution=resolution)
            if self.signal is not None:
                self._set_signal_calibration(self.signal, resolution=resolution)
        if reference_bg_shift is not None:
            self.reference_bg_shift = float(reference_bg_shift)
        self._refresh_display_signal_cache()
        if refit_model and self.model is not None:
            self.fit_model()
    
    def export(self, folder: Optional[str] = None, formats: list | str | tuple = ('csv', 'mas')):
        if isinstance(formats, str):
            formats = [formats]
            
        folder = folder if folder is not None else os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
        export_signal = self.get_signal_for_export()
             
        for fmt in formats:
            fmt_lower = fmt.lower()
            if fmt_lower == 'csv':
                import pandas as pd
                energy = export_signal.axes_manager['Energy'].axis.round(6)
                signal = export_signal.data
                spec_data = pd.DataFrame(signal, index=energy, columns=[export_signal.metadata.get_item('Signal.quantity')])
                spec_data.index.name = 'Energy'
                spec_data.to_csv(os.path.join(folder, f"{self.name}.csv"))
            elif fmt_lower == 'hspy':
                target = os.path.join(folder, f"{self.name}.hspy")
                if os.path.exists(target):
                    os.remove(target)
                signal_to_save = self._signal.deepcopy()
                signal_to_save.metadata.set_item('General.title', self.name)
                signal_to_save.metadata.set_item('General.original_filename', self.path)
                signal_to_save.metadata.set_item('Signal.quantity', 'X-rays (Counts)')
                filedate = signal_to_save.metadata.get_item('General.filedate', default=None)
                if filedate is not None and not isinstance(filedate, (str, int, float, bool)):
                    signal_to_save.metadata.set_item('General.filedate', str(filedate))
                original_filedate = signal_to_save.original_metadata.get_item('Header.filedate', default=None)
                if original_filedate is not None and not isinstance(original_filedate, (str, int, float, bool)):
                    signal_to_save.original_metadata.set_item('Header.filedate', str(original_filedate))
                signal_to_save.metadata.set_item(EDS_TOOL_STATE_KEY, self._serialize_state())
                signal_to_save.save(target)
            else:
                target = os.path.join(folder, f"{self.name}.{fmt}")                
                if os.path.exists(target): os.remove(target)
                export_signal.save(target)

    def export_intensities_csv(self, folder: Optional[str] = None):
        """Export computed intensities to a CSV file in the same folder as the spectrum."""
        if not self.intensities:
            return
        
        import pandas as pd
        
        folder = folder if folder is not None else os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
        
        # Build a single-row table with line names as columns
        data = {}
        for sig in self.intensities:
            line = sig.metadata.get_item('Sample.xray_lines')[0]
            val = sig.data[0] if hasattr(sig.data, "__getitem__") else sig.data
            data[line] = [float(val)]
        
        df = pd.DataFrame(data, index=[self.name])
        df.index.name = 'spectrum'
        
        # Save with naming convention: {spectrum_name}_summed_intensities.csv
        filepath = os.path.join(folder, f"{self.name}_summed_intensities.csv")
        df.to_csv(filepath)

    def export_plot(self, folder: Optional[str] = None, formats: list | str | tuple = ('png',), max_energy: Optional[float] = None):
        """Export plot of the spectrum to image files in various formats."""
        if isinstance(formats, str):
            formats = [formats]
            
        folder = folder if folder is not None else os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
        
        # Use hyperspy's plot method to get proper X-ray line annotations
        import matplotlib.pyplot as plt
        import sys
        import io
        
        # Suppress stderr to hide matplotlib blit warnings for non-interactive backends
        stderr_backup = sys.stderr
        sys.stderr = io.StringIO()
        
        try:
            export_signal = self.get_signal_for_export()
            export_signal.set_elements(self.get_all_elements_for_display())
            export_signal.plot(xray_lines=bool(self.elements), navigator=None)
            
            # Get the figure that was just created
            fig = export_signal._plot.signal_plot.figure
            ax = export_signal._plot.signal_plot.ax
            
            # Set x-axis range if max_energy is specified
            if max_energy is not None:
                energy = export_signal.axes_manager['Energy'].axis
                ax.set_xlim(left=energy[0], right=max_energy)
            
            # Save in all requested formats
            for fmt in formats:
                target = os.path.join(folder, f"{self.name}.{fmt}")
                fig.savefig(target, dpi=150, bbox_inches='tight')
            
            # Close the plot
            plt.close(fig)
        finally:
            # Restore stderr
            sys.stderr = stderr_backup

    def set_elements(self, elements: List[str]):
        if elements != self.elements:
            had_model = self.model is not None
            self._signal.set_elements(elements)
            self._fit_signal.set_elements(elements)
            self.intensities = None
            self._refresh_display_signal_cache()
            
            # If a model existed, refit it with new elements instead of just deleting
            if had_model:
                print(f"Refitting model for {self.name} with updated elements...")
                self.fit_model()
            else:
                self.model = None
                self.fitted_intensities = None

    def compute_intensities(self):
        """
        Compute intensities using peak summation.
        Uses the explicitly selected peak-sum signal source.
        """
        try:
            signal_to_use = self.get_signal_for_peak_sum()
            self.intensities = signal_to_use.get_lines_intensity()
        except Exception as e:
            print(f"Warning: Could not compute intensities for {self.name}: {e}")
            self.intensities = None

    def set_fit_energy_range(self, lower_keV: float, upper_keV: float):
        lower_keV = float(lower_keV)
        upper_keV = float(upper_keV)
        if lower_keV < 0:
            raise ValueError("Fit lower limit must be >= 0 keV")
        if upper_keV <= lower_keV:
            raise ValueError("Fit upper limit must be greater than the lower limit")
        self.fit_energy_min_keV = lower_keV
        self.fit_energy_max_keV = upper_keV

    def set_reference_bg_ignore_sample_half_width(self, half_width_keV: float):
        half_width_keV = float(half_width_keV)
        if half_width_keV < 0:
            raise ValueError("Ignore range half-width must be >= 0 keV")
        self.reference_bg_ignore_sample_half_width_keV = half_width_keV

    def _restore_model_state_hygiene(self):
        if self.model is None:
            return
        # exspy's resolution calibration clears sigma.bmin on x-ray lines even
        # though the original fitted model keeps a non-negative lower bound.
        for component in self.model:
            if self._is_xray_line_component(component):
                component.sigma.bmin = 0.0

    def _seed_model_from_previous(self, previous_model):
        if self.model is None or previous_model is None:
            return

        previous_components = self._component_map(previous_model)
        for component in self.model:
            previous_component = previous_components.get(component.name)
            if previous_component is None:
                continue

            previous_params = {param.name: param for param in previous_component.parameters}
            for param in component.parameters:
                previous_param = previous_params.get(param.name)
                if previous_param is None:
                    continue

                # Keep target twinning/free structure, but reuse the fitted
                # numeric state from matching existing components.
                if param.twin is None:
                    param.value = previous_param.value

                if param.bmin is not None or previous_param.bmin is not None:
                    param.bmin = previous_param.bmin
                if param.bmax is not None or previous_param.bmax is not None:
                    param.bmax = previous_param.bmax

                # HyperSpy stores current scalar values and per-navigation
                # parameter maps separately. The rebuilt model must inherit both.
                param.assign_current_value_to_all()

    def clear_fit(self, reset_calibration: bool = True):
        self.model = None
        self.fitted_intensities = None
        self.fitted_reference_clean_signal = None
        self.fitted_reference_bg_signal = None
        self.signal_clean = None
        self.signal_bg = None
        self.reduced_chisq = None
        if reset_calibration:
            self.reference_bg_shift = 0.0
            self._restore_default_calibration()
        self._refresh_display_signal_cache()

    def fit_model(self):
        """
        Fit the model based on bg_fit_mode:
        - 'none': Sample elements + polynomial baseline only
        - 'bg_elements': Temporarily add bg_elements to signal, fit, then restore
        - 'bg_spec': Use ScalableFixedPattern component with background spectrum
        """
        try:
            self._print_fit_banner("Fitting")
            previous_model = self.model
            original_elements = self.elements.copy()
            fit_signal = self.get_signal_for_fit()
            
            if self.bg_fit_mode == 'none':
                self.model = self._make_model(fit_signal, original_elements)

            elif self.bg_fit_mode == 'bg_elements':
                # Mode 1: Add BG elements to the model
                all_elements = original_elements + self.bg_elements
                self.model = self._make_model(fit_signal, all_elements)
                
            elif self.bg_fit_mode == 'bg_spec':
                # Mode 2: Use ScalableFixedPattern with background spectrum
                if self._background is None:
                    raise ValueError(f"Background spectrum required for bg_fit_mode='bg_spec' but none loaded")
                
                # Create model with only sample elements
                self.model = self._make_model(fit_signal, original_elements)
                
                # Add ScalableFixedPattern component for instrument background
                comp_bg = hs.model.components1D.ScalableFixedPattern(self._background_fit_signal)
                comp_bg.name = 'instrument'
                comp_bg.isbackground = True
                # Instrument/background spectra should share the same energy calibration.
                # Letting xscale float makes the whole fit nonlinear with negligible benefit.
                comp_bg.xscale.free = False
                # Keep the background shift fixed during the initial fit.
                # If needed, fine_tune_model() can refine it later.
                comp_bg.shift.free = False
                comp_bg.shift.value = self.reference_bg_shift
                self.model.append(comp_bg)
                self.model.background_components.append(comp_bg)
            else:
                raise ValueError(f"Unknown bg_fit_mode: {self.bg_fit_mode}")

            self._seed_model_from_previous(previous_model)
            
            # With fixed line positions/widths and fixed reference-BG shift/xscale,
            # these EDS fits are linear in amplitudes and polynomial terms.
            prefit_info = self._run_background_prefit()
            if prefit_info.get('used'):
                message = prefit_info['description']
                if 'scale' in prefit_info:
                    print(
                        f"{message}... Scale: {prefit_info['scale']:.4f}, "
                        f"Shift: {prefit_info['shift']:.6f} keV, "
                        f"chi2r: {prefit_info['chi2r']:.2f}"
                    )
                else:
                    print(f"{message}... chi2r: {prefit_info['chi2r']:.2f}")
            fit_kwargs = {} if prefit_info.get('used') else {'optimizer': 'lstsq'}
            with _small_signal_numexpr():
                with self._temporary_model_signal_range(self.model):
                    self.model.fit(**fit_kwargs)
            self._restore_model_state_hygiene()
            self.fitted_intensities = self.model.get_lines_intensity()
            
            # Compute reduced chi-square (extract scalar from array if needed)
            if hasattr(self.model, 'red_chisq'):
                chisq_data = self.model.red_chisq.data
                self.reduced_chisq = float(chisq_data) if hasattr(chisq_data, '__float__') else float(chisq_data.item())
            else:
                self.reduced_chisq = None
            if self.reduced_chisq is not None:
                print(f"Fitting element lines and polynomial baseline... chi2r: {self.reduced_chisq:.2f}")
            
            # Pre-compute clean and background signals for efficiency
            self._compute_fitted_signals()
            
            # Restore original elements if we added bg_elements
            if self.bg_fit_mode == 'bg_elements':
                fit_signal.set_elements(original_elements)

            self._sync_raw_signal_from_fit()

            self._refresh_display_signal_cache()
                
        except Exception as e:
            print(f"Warning: Could not fit model for {self.name}: {e}")
            self.clear_fit(reset_calibration=False)

    def _get_instrument_component(self):
        if self.model is None:
            return None

        for component in self.model:
            if component.name == 'instrument':
                return component
        return None

    def _refine_background_shift(self, initial_bg_shift: float):
        """
        Refine the measured background alignment separately from the peak offset.
        """
        instrument = self._get_instrument_component()
        if instrument is None:
            return None, None

        previously_free = []
        for component in self.model:
            for param in component.parameters:
                if param.free:
                    previously_free.append(param)
                    param.free = False

        instrument.shift.free = True
        instrument.yscale.free = True

        try:
            with _small_signal_numexpr():
                with self._temporary_model_signal_range(
                    self.model,
                    exclude_sample_half_width=self.reference_bg_ignore_sample_half_width_keV,
                ):
                    self.model.fit()
        finally:
            for param in previously_free:
                param.free = True
            instrument.shift.free = False

        bg_shift = instrument.shift.value
        chisq = float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data)
        print(
            f"Fitting reference background shift... {bg_shift:.6f} keV "
            f"(delta = {(bg_shift - initial_bg_shift) * 1000:+.2f} eV). "
            f"chi2r: {chisq:.2f}"
        )
        return bg_shift, chisq
    
    def _fine_tune_model_legacy(self):
        """
        Fine-tune the fitted model using energy axis calibration.
        Calibrates energy offset and resolution to improve fit quality.
        Uses parameter locking to speed up resolution calibration.
        """
        if self.model is None:
            raise ValueError(f"No fitted model to fine-tune for {self.name}")
        
        try:
            # Get initial values
            fit_signal = self.get_signal_for_fit()
            initial_chisq = float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data)
            initial_offset = fit_signal.axes_manager[-1].offset
            initial_resolution = fit_signal.metadata.Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa
            
            print(f"\n=== Fine-tuning {self.name} ===")
            print(f"Initial χ²ᵣ: {initial_chisq:.2f}")
            print(f"Initial offset: {initial_offset:.6f} keV")
            print(f"Initial resolution: {initial_resolution:.2f} eV")
            
            # Step 1: Calibrate energy offset
            # This includes internal fitting with all parameters free
            with _small_signal_numexpr():
                self.model.calibrate_energy_axis(calibrate='offset')
            offset_1 = fit_signal.axes_manager[-1].offset
            chisq_1 = float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data)
            print(f"\nAfter offset calibration:")
            print(f"  Offset: {offset_1:.6f} keV (Δ = {(offset_1 - initial_offset)*1000:.2f} eV)")
            print(f"  χ²ᵣ: {chisq_1:.2f} (Δ = {chisq_1 - initial_chisq:.2f}, {((chisq_1/initial_chisq - 1)*100):.1f}%)")
            
            # Step 2: Calibrate energy resolution with locked parameters for speed
            try:
                # Lock all element amplitude and background parameters
                # Only resolution parameter should vary during this calibration
                locked_params = []
                for component in self.model:
                    for param in component.parameters:
                        if param.free:
                            param.free = False
                            locked_params.append(param)
                
                # Now do resolution calibration (will unlock resolution parameter internally)
                with _small_signal_numexpr():
                    self.model.calibrate_energy_axis(calibrate='resolution')
                
                # Unlock the parameters we locked
                for param in locked_params:
                    param.free = True
                
                resolution_2 = fit_signal.metadata.Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa
                chisq_2 = float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data)
                print(f"\nAfter resolution calibration (with locked parameters):")
                print(f"  Resolution: {resolution_2:.2f} eV (Δ = {resolution_2 - initial_resolution:.2f} eV)")
                print(f"  χ²ᵣ: {chisq_2:.2f} (Δ = {chisq_2 - chisq_1:.2f}, {((chisq_2/chisq_1 - 1)*100):.1f}%)")
            except Exception as e:
                # Make sure to unlock parameters if there's an error
                for param in locked_params:
                    param.free = True
                print(f"\nNote: Resolution calibration failed: {e}")
                chisq_2 = chisq_1
                resolution_2 = initial_resolution
            
            # Step 3: Final refinement fit with all parameters free
            with _small_signal_numexpr():
                self.model.fit()
            final_chisq = float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data)
            if abs(final_chisq - chisq_2) > 0.01:
                print(f"\nAfter final refinement fit:")
                print(f"  χ²ᵣ: {final_chisq:.2f} (Δ = {final_chisq - chisq_2:.2f}, {((final_chisq/chisq_2 - 1)*100):.1f}%)")
            
            # Summary
            final_resolution = fit_signal.metadata.Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa
            final_offset = fit_signal.axes_manager[-1].offset
            total_offset_change = (final_offset - initial_offset) * 1000  # in eV
            total_resolution_change = final_resolution - initial_resolution
            total_chisq_change = final_chisq - initial_chisq
            total_chisq_improvement = ((1 - final_chisq/initial_chisq) * 100)
            
            print(f"\n--- Summary ---")
            print(f"Total offset change: {total_offset_change:+.2f} eV")
            print(f"Total resolution change: {total_resolution_change:+.2f} eV")
            print(f"χ²ᵣ: {initial_chisq:.2f} → {final_chisq:.2f} ({total_chisq_improvement:+.1f}%)")
            
            # Update fitted intensities
            self.fitted_intensities = self.model.get_lines_intensity()
            
            # Update reduced chi-square
            if hasattr(self.model, 'red_chisq'):
                chisq_data = self.model.red_chisq.data
                self.reduced_chisq = float(chisq_data) if hasattr(chisq_data, '__float__') else float(chisq_data.item())
            else:
                self.reduced_chisq = None
            
            # Re-compute fitted signals
            self._compute_fitted_signals()
            self._sync_raw_signal_from_fit()
            
        except Exception as e:
            raise RuntimeError(f"Could not fine-tune model for {self.name}: {e}")
    
    def fine_tune_model(self):
        """
        Fine-tune the fitted model using energy axis calibration.
        Calibrates peak offset and detector resolution, and in bg_spec mode
        can also refine a separate background shift.
        """
        if self.model is None:
            raise ValueError(f"No fitted model to fine-tune for {self.name}")

        try:
            fit_signal = self.get_signal_for_fit()
            initial_chisq = float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data)
            initial_offset = fit_signal.axes_manager[-1].offset
            initial_resolution = fit_signal.metadata.Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa
            instrument = self._get_instrument_component()
            initial_bg_shift = instrument.shift.value if instrument is not None else None

            self._print_fit_banner("Fine-tuning")
            print(
                f"Initial state... chi2r: {initial_chisq:.2f}, "
                f"offset: {initial_offset:.6f} keV, resolution: {initial_resolution:.2f} eV"
                + (f", BG shift: {initial_bg_shift:.6f} keV" if initial_bg_shift is not None else "")
            )

            # Step 1: calibrate the peak offset while the background stays fixed.
            if instrument is not None:
                instrument.shift.free = False
            with _small_signal_numexpr():
                with self._temporary_model_signal_range(self.model):
                    self.model.calibrate_energy_axis(calibrate='offset')
            offset_1 = fit_signal.axes_manager[-1].offset
            chisq_1 = float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data)
            print(
                f"Fitting overall offset... {offset_1:.6f} keV "
                f"(delta = {(offset_1 - initial_offset) * 1000:+.2f} eV). "
                f"chi2r: {chisq_1:.2f} (delta = {chisq_1 - initial_chisq:+.2f}, {self._format_delta_percent(chisq_1, initial_chisq)})"
            )

            # Step 2: refine the background shift separately, if present.
            if initial_bg_shift is not None:
                bg_shift_2, chisq_2 = self._refine_background_shift(initial_bg_shift)
                self.reference_bg_shift = bg_shift_2
            else:
                chisq_2 = chisq_1

            # Step 3: calibrate energy resolution with all other params locked.
            try:
                locked_params = []
                for component in self.model:
                    for param in component.parameters:
                        if param.free:
                            param.free = False
                            locked_params.append(param)

                resolution_2, resolution_bound = self._calibrate_resolution_with_bounds()
                for param in locked_params:
                    param.free = True

                chisq_3 = float(self.model.red_chisq.data.item() if hasattr(self.model.red_chisq.data, 'item') else self.model.red_chisq.data)
                warning_text = f" WARNING: resolution at {resolution_bound} bound" if resolution_bound else ""
                print(
                    f"Fitting spectrum resolution... {resolution_2:.2f} eV "
                    f"(delta = {resolution_2 - initial_resolution:+.2f} eV). "
                    f"chi2r: {chisq_3:.2f} (delta = {chisq_3 - chisq_2:+.2f}, {self._format_delta_percent(chisq_3, chisq_2)})"
                    f"{warning_text}"
                )
            except Exception as e:
                for param in locked_params:
                    param.free = True
                print(f"Fitting spectrum resolution... FAILED ({e})")
                chisq_3 = chisq_2
                resolution_2 = initial_resolution

            # Step 4: rebuild a fresh model on the calibrated signal so the
            # post-refinement state remains robust for later re-fits.
            self._restore_model_state_hygiene()
            if instrument is not None:
                instrument.shift.free = False
                self.reference_bg_shift = instrument.shift.value

            self.fitted_intensities = self.model.get_lines_intensity()
            if hasattr(self.model, 'red_chisq'):
                chisq_data = self.model.red_chisq.data
                self.reduced_chisq = float(chisq_data) if hasattr(chisq_data, '__float__') else float(chisq_data.item())
            else:
                self.reduced_chisq = None
            self._compute_fitted_signals()
            self._sync_raw_signal_from_fit()
            final_chisq = self.reduced_chisq if self.reduced_chisq is not None else chisq_3
            if abs(final_chisq - chisq_3) > 0.01:
                print(f"\nAfter keeping live refined fit:")
                print(f"  chi2r: {final_chisq:.2f} (delta = {final_chisq - chisq_3:.2f}, {((final_chisq / chisq_3 - 1) * 100):.1f}%)")

            final_resolution = fit_signal.metadata.Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa
            final_offset = fit_signal.axes_manager[-1].offset
            final_bg_shift = self.reference_bg_shift if instrument is not None else None
            total_offset_change = (final_offset - initial_offset) * 1000
            total_resolution_change = final_resolution - initial_resolution
            total_chisq_improvement = ((1 - final_chisq / initial_chisq) * 100)

            print(f"\n--- Summary ---")
            print(f"Total offset change: {total_offset_change:+.2f} eV")
            print(f"Total resolution change: {total_resolution_change:+.2f} eV")
            if final_bg_shift is not None and initial_bg_shift is not None:
                print(f"Total BG shift change: {(final_bg_shift - initial_bg_shift) * 1000:+.2f} eV")
            print(f"chi2r: {initial_chisq:.2f} -> {final_chisq:.2f} ({total_chisq_improvement:+.1f}%)")

            self._refresh_display_signal_cache()

        except Exception as e:
            raise RuntimeError(f"Could not fine-tune model for {self.name}: {e}")

    def _compute_fitted_signals(self):
        """
        Compute clean and background signals after fitting.
        Called automatically after fit_model() for efficiency.
        """
        if self.model is None:
            self.fitted_reference_clean_signal = None
            self.fitted_reference_bg_signal = None
            self.signal_clean = None
            self.signal_bg = None
            return
        
        try:
            bg_component_names = []

            if self.bg_fit_mode == 'bg_spec':
                bg_component_names = ['instrument']
            elif self.bg_fit_mode == 'bg_elements' and not self.has_bg_element_overlap():
                for comp in self.model:
                    comp_element = None
                    if hasattr(comp, 'element'):
                        comp_element = comp.element
                    elif hasattr(comp, 'name'):
                        name_parts = comp.name.split('_')
                        if len(name_parts) >= 2:
                            comp_element = name_parts[0]

                    if comp_element and comp_element in self.bg_elements:
                        bg_component_names.append(comp.name)

            if bg_component_names:
                self.fitted_reference_bg_signal = self.model.as_signal(component_list=bg_component_names)
                self.fitted_reference_clean_signal = self._fit_signal - self.fitted_reference_bg_signal
            else:
                self.fitted_reference_bg_signal = None
                self.fitted_reference_clean_signal = None

            self.signal_bg = self.fitted_reference_bg_signal
            self.signal_clean = self.fitted_reference_clean_signal
                 
        except Exception as e:
            print(f"Warning: Could not compute fitted signals for {self.name}: {e}")
            import traceback
            traceback.print_exc()
            self.fitted_reference_clean_signal = None
            self.fitted_reference_bg_signal = None
            self.signal_clean = None
            self.signal_bg = None

    def plot(
        self,
        use_model: Optional[bool] = None,
        ax: Optional[Any] = None,
        fig: Optional[Any] = None,
        show_residual: bool = True,
        show_background: bool = False,
        show_bg_elements: bool = False,
        **kwargs
    ):
        # Save axis limits if ax is supplied
        xlim = ylim = yscale = None
        if ax is not None:
            xlim, ylim = ax.get_xlim(), ax.get_ylim()
            yscale = ax.get_yscale()
        # Save window geometry if fig is supplied
        win_geom = None
        if fig is not None:
            win = fig.canvas.manager.window
            win_geom = win.geometry()
            plt.close(fig)

        # Plot
        if use_model is None:
            use_model = self.uses_model_plot()
        elif use_model and not self.uses_model_plot():
            use_model = False
        
        # Determine which elements to show
        # In bg_elements mode with a fit, show all elements (sample + bg)
        elements_to_show = self.get_all_elements_for_display(include_bg_elements=show_bg_elements)
        show_lines = bool(elements_to_show)
        
        # Temporarily set elements for display if in bg_elements mode with fit
        plot_signal = self._fit_signal if use_model and self.model is not None else self.signal
        original_elements = plot_signal.metadata.get_item('Sample.elements', default=[])
        if show_lines and elements_to_show != original_elements:
            plot_signal.set_elements(elements_to_show)
        
        try:
            if use_model and self.model is not None:
                self.model.plot(
                    xray_lines=show_lines,
                    plot_residual=show_residual,
                    navigator=None,
                    **kwargs
                )
                if self.display_signal_mode == 'fitted_reference_bg_subtracted':
                    self._apply_fitted_reference_bg_subtracted_plot_callbacks()
            else:
                plot_signal.plot(show_lines, navigator=None, **kwargs)
        finally:
            # Restore original elements
            if elements_to_show != original_elements:
                plot_signal.set_elements(original_elements)

        # Extract new fig/ax (check if plot exists)
        if plot_signal._plot is None or not hasattr(plot_signal._plot, 'signal_plot'):
            return None, None
        
        fig_new = plot_signal._plot.signal_plot.figure
        ax_new = plot_signal._plot.signal_plot.ax
        
        # Plot fitted or raw reference background if requested.
        bg_signal = None
        bg_label = None
        if show_background:
            if self.signal_bg is not None:
                bg_label = 'Fitted reference background'
                if use_model:
                    bg_signal = self.signal_bg
                else:
                    bg_signal = self._make_signal_from_cps(
                        self.signal_bg.data,
                        unit=self.signal_unit,
                        mode='fitted_reference_bg_subtracted',
                    )
            elif self._background_fit_signal is not None:
                bg_label = 'Reference background (not fitted)'
                if use_model:
                    bg_signal = self._background_fit_signal
                else:
                    bg_signal = self._make_signal_from_cps(
                        self._background_fit_signal.data,
                        unit=self.signal_unit,
                        mode='raw',
                    )

        background_handle = None
        if bg_signal is not None:
            energy_axis = bg_signal.axes_manager['Energy'].axis
            # Fill area with transparency
            background_handle = ax_new.fill_between(
                energy_axis,
                0,
                bg_signal.data,
                color='lightgray',
                alpha=0.4,
                label=bg_label,
            )
            # Add line on top with no transparency
            ax_new.plot(energy_axis, bg_signal.data,
                       color='gray', alpha=1.0, linewidth=1.0)
        self._apply_plot_legend(plot_signal, ax_new, use_model, show_residual, background_handle=background_handle)

        # Restore axis limits if ax is supplied
        if ax is not None and xlim is not None:
            ax_new.set_yscale(yscale)
            ax_new.set_xlim(xlim)
            ax_new.set_ylim(ylim)
            fig_new.canvas.draw_idle()
        # Restore window geometry if fig is supplied
        if fig is not None and win_geom is not None:
            win = fig_new.canvas.manager.window
            win.setGeometry(win_geom)
        return fig_new, ax_new

    def get_metadata(self) -> Dict:
        return self._signal.metadata.as_dictionary()

    def get_live_time(self, signal=None) -> Optional[float]:
        """Get measurement live time from metadata, or None if missing."""
        sig = signal if signal is not None else self._signal
        try:
            return float(sig.metadata.get_item('Acquisition_instrument.TEM.Detector.EDS.live_time'))
        except Exception:
            return None

    def set_background(self, bg_signal: exspy.signals.EDSTEMSpectrum):
        """Set the measured reference background spectrum without changing active signal modes."""
        self._background = bg_signal
        self._background_fit_signal = self._make_cps_signal(bg_signal)
        self._refresh_display_signal_cache()

    def set_unit_and_bg(self, unit: str, bg_correct: bool):
        """Legacy compatibility shim."""
        self.set_unit(unit)
        self.set_bg_correction(bg_correct)
    
    def set_bg_correction_mode(self, mode: str):
        """Legacy compatibility shim mapping to both explicit signal source modes."""
        if mode not in ('none', 'subtract_fitted', 'subtract_spectra'):
            raise ValueError("mode must be 'none', 'subtract_fitted', or 'subtract_spectra'")
        mode_map = {
            'none': 'raw',
            'subtract_spectra': 'measured_bg_subtracted',
            'subtract_fitted': 'fitted_reference_bg_subtracted',
        }
        signal_mode = mode_map[mode]
        self.set_display_signal_mode(signal_mode)
        self.set_peak_sum_signal_mode(signal_mode)
    
    def _apply_unit_and_bg_correction(self, unit: str):
        """Legacy helper retained for callers that only intend to change signal units."""
        self.set_unit(unit)
    
    def _get_current_bg_mode_from_quantity(self, quantity: str) -> str:
        """Legacy helper mapping current explicit state to an old-style summary."""
        return self.bg_correction_mode
    
    def _get_bg_suffix_for_quantity(self) -> str:
        """Legacy helper retained for compatibility with old callers."""
        suffix_map = {
            'none': '',
            'subtract_fitted': ', Fitted Reference BG Subtracted',
            'subtract_spectra': ', Measured BG Subtracted',
            'mixed': ', Mixed BG Modes',
        }
        return suffix_map.get(self.bg_correction_mode, '')

    def set_unit(self, unit: str):
        if unit not in ('counts', 'cps'):
            raise ValueError("unit must be 'counts' or 'cps'")
        self.signal_unit = unit
        self._refresh_display_signal_cache()

    def set_bg_correction(self, active: bool):
        """Legacy compatibility shim."""
        mode = 'measured_bg_subtracted' if active else 'raw'
        self.set_display_signal_mode(mode)
        self.set_peak_sum_signal_mode(mode)
    
    def set_bg_elements(self, elements: List[str]):
        """Set background elements (used in bg_elements fit mode)."""
        if elements != self.bg_elements:
            self.bg_elements = elements
            # If a fit exists and we're in bg_elements mode, refit with new BG elements
            if self.model is not None and self.bg_fit_mode == 'bg_elements':
                print(f"Refitting model for {self.name} with updated BG elements...")
                self.fit_model()
            else:
                self._compute_fitted_signals()
                self._refresh_display_signal_cache()

    def set_bg_fit_mode(self, mode: str):
        """
        Set background fitting mode: 'none', 'bg_elements' or 'bg_spec'.
        If switching to 'bg_spec' without a background spectrum, raise an error.
        """
        if mode not in ('none', 'bg_elements', 'bg_spec'):
            raise ValueError("mode must be 'none', 'bg_elements' or 'bg_spec'")
        
        if mode == 'bg_spec' and self._background is None:
            raise ValueError("Cannot set bg_fit_mode to 'bg_spec' without a background spectrum. Load one first.")
        
        if mode != self.bg_fit_mode:
            self.bg_fit_mode = mode
            self.clear_fit(reset_calibration=False)

    def set_background_prefit_mode(self, mode: str):
        if mode not in ('off', 'exclude_sample', 'bg_elements_only'):
            raise ValueError("background prefit mode must be 'off', 'exclude_sample', or 'bg_elements_only'")
        self.background_prefit_mode = mode

    def set_background_polynomial_order(self, order: int):
        order = int(order)
        if order < 1:
            raise ValueError("Background polynomial order must be >= 1")
        self.background_polynomial_order = order

    def get_all_elements_for_display(self, include_bg_elements: bool = False) -> List[str]:
        """
        Get all elements that should be displayed in plots.
        When requested, include both sample and background elements.
        """
        if include_bg_elements:
            combined = list(self.elements)
            for element in self.bg_elements:
                if element not in combined:
                    combined.append(element)
            return combined
        return self.elements

class EDSSession:
    def __init__(self, paths: Optional[List[str]] = None):
        self.records: Dict[str, EDSSpectrumRecord] = {}
        self.active_name: Optional[str] = None
        self.display_signal_mode_default: str = 'raw'
        self.peak_sum_signal_mode_default: str = 'raw'
        if paths:
            self.load(paths)

    def load(self, paths: List[str]):
        # Copy settings from the first existing record if available
        existing_elements = None
        bg_signal = None
        bg_elements = []
        bg_fit_mode = 'bg_spec'
        background_prefit_mode = DEFAULT_BACKGROUND_PREFIT_MODE
        background_polynomial_order = DEFAULT_BACKGROUND_POLYNOMIAL_ORDER
        display_signal_mode = self.display_signal_mode_default
        peak_sum_signal_mode = self.peak_sum_signal_mode_default
        unit = "counts"
        bg_file = None
        fit_energy_min_keV = DEFAULT_FIT_MIN_KEV
        fit_energy_max_keV = DEFAULT_FIT_MAX_KEV
        reference_bg_ignore_sample_half_width_keV = DEFAULT_IGNORE_SAMPLE_HALF_WIDTH_KEV
        
        if self.records:
            first_rec = next(iter(self.records.values()))
            existing_elements = first_rec.elements if first_rec.elements else None
            bg_signal = first_rec._background
            bg_elements = first_rec.bg_elements
            bg_fit_mode = first_rec.bg_fit_mode
            background_prefit_mode = first_rec.background_prefit_mode
            background_polynomial_order = first_rec.background_polynomial_order
            unit = first_rec.signal_unit
            bg_file = getattr(first_rec, "bg_file", None)
            fit_energy_min_keV = first_rec.fit_energy_min_keV
            fit_energy_max_keV = first_rec.fit_energy_max_keV
            reference_bg_ignore_sample_half_width_keV = first_rec.reference_bg_ignore_sample_half_width_keV

        for rec in [EDSSpectrumRecord(p) for p in _dedupe_preferred_spectrum_paths(paths)]:
            if rec.name in self.records:
                print(f"Warning: Spectrum '{rec.name}' already loaded, skipping.")
                continue
            
            # Apply settings from existing records
            if existing_elements:
                rec.set_elements(existing_elements)
            if bg_signal is not None:
                rec.set_background(bg_signal)
            
            # Set background handling settings
            rec.bg_elements = bg_elements
            rec.bg_fit_mode = bg_fit_mode
            rec.set_background_prefit_mode(background_prefit_mode)
            rec.set_background_polynomial_order(background_polynomial_order)
            rec.set_fit_energy_range(fit_energy_min_keV, fit_energy_max_keV)
            rec.set_reference_bg_ignore_sample_half_width(reference_bg_ignore_sample_half_width_keV)
            rec.set_unit(unit)
            for mode, setter in (
                (display_signal_mode, rec.set_display_signal_mode),
                (peak_sum_signal_mode, rec.set_peak_sum_signal_mode),
            ):
                try:
                    setter(mode)
                except ValueError:
                    setter('raw')
            
            if bg_file:
                rec.bg_file = bg_file
            self.records[rec.name] = rec
        if self.records and self.active_name is None:
            self.active_name = next(iter(self.records))
            
    def export_all(self, folder: Optional[str] = None, formats: list | str | tuple = ('csv', 'mas')):
        for rec in self.records.values():
            rec.export(folder=folder, formats=formats)

    def export_intensity_table(self, folder: str, fitted=False):
        """Export intensity table to CSV file."""
        import pandas as pd
        
        # Get intensity data
        table_data = self.get_intensity_table(fitted=fitted)
        if not table_data:
            print("Warning: No intensity data to export.")
            return
        
        # Convert to DataFrame and pivot for better readability
        df = pd.DataFrame(table_data)
        pivot = df.pivot(index='spectrum', columns='line', values='intensity')
        
        # Save to CSV
        os.makedirs(folder, exist_ok=True)
        filename = "fitted_intensities.csv" if fitted else "summed_intensities.csv"
        filepath = os.path.join(folder, filename)
        pivot.to_csv(filepath)
        print(f"Intensity table exported to: {filepath}")

    def set_elements(self, elements: List[str]):
        for rec in self.records.values():
            rec.set_elements(elements)
    
    def set_energy_resolution(self, resolution_ev: float):
        """Set the energy resolution (FWHM at Mn Ka) for all spectra in eV."""
        for rec in self.records.values():
            rec._signal.set_microscope_parameters(energy_resolution_MnKa=resolution_ev)
            rec._fit_signal.set_microscope_parameters(energy_resolution_MnKa=resolution_ev)
            rec._default_energy_resolution = resolution_ev
            if rec._background is not None:
                rec._background.set_microscope_parameters(energy_resolution_MnKa=resolution_ev)
            if rec._background_fit_signal is not None:
                rec._background_fit_signal.set_microscope_parameters(energy_resolution_MnKa=resolution_ev)
            rec._refresh_display_signal_cache()

    def compute_all_intensities(self):
        for rec in self.records.values():
            rec.compute_intensities()

    def fit_all_models(self):
        for rec in self.records.values():
            rec.fit_model()
    
    def fine_tune_all_models(self):
        """Fine-tune all fitted models in the session."""
        for rec in self.records.values():
            if rec.model is not None:
                rec.fine_tune_model()

    def apply_active_fine_tuning_to_all_models(self):
        source = self.active_record
        if source is None or source.model is None:
            raise ValueError("The active spectrum must have a fitted model before applying fine-tuning to all models.")

        offset = source.get_signal_for_fit().axes_manager.signal_axes[0].offset
        resolution = source.get_energy_resolution()
        reference_bg_shift = source.reference_bg_shift

        for rec in self.records.values():
            if rec is source or rec.model is None:
                continue
            rec.apply_calibration(
                offset=offset,
                resolution=resolution,
                reference_bg_shift=reference_bg_shift,
                refit_model=True,
            )

    def get_intensity_table(self, fitted=False) -> List[Dict]:
        table = []
        for rec in self.records.values():
            intensities = rec.fitted_intensities if fitted else rec.intensities
            if intensities is None:
                continue
            for sig in intensities:
                line = sig.metadata.get_item('Sample.xray_lines')[0]
                val = sig.data[0] if hasattr(sig.data, "__getitem__") else sig.data
                table.append({
                    "spectrum": rec.name,
                    "line": line,
                    "intensity": float(val)
                })
        return table

    def get_metadata(self) -> List[Dict]:
        return [rec.get_metadata() for rec in self.records.values()]

    def set_active(self, name: str):
        if name in self.records:
            self.active_name = name
        else:
            raise KeyError(f"Spectrum '{name}' not found in records. Records available: {list(self.records.keys())}")

    @property
    def active_record(self) -> Optional[EDSSpectrumRecord]:
        if self.active_name and self.active_name in self.records:
            return self.records[self.active_name]
        return None

    def plot_active(self, use_model: Optional[bool] = None, ax: Optional[Any] = None, fig: Optional[Any] = None, **kwargs):
        rec = self.active_record
        if rec is not None:
            return rec.plot(use_model=use_model, ax=ax, fig=fig, **kwargs)
        return None, None

    def remove(self, name: str):
        if name in self.records:
            del self.records[name]
            # If the active record was removed, set a new active record if any remain
            if self.active_name == name:
                self.active_name = next(iter(self.records), None)
        else:
            print(f"Warning: Spectrum '{name}' not found in records.")

    def set_unit(self, unit: str):
        """Set unit for all spectra ('counts' or 'cps')."""
        for rec in self.records.values():
            rec.set_unit(unit)

    def set_fit_energy_range(self, lower_keV: float, upper_keV: float):
        for rec in self.records.values():
            rec.set_fit_energy_range(lower_keV, upper_keV)

    def set_reference_bg_ignore_sample_half_width(self, half_width_keV: float):
        for rec in self.records.values():
            rec.set_reference_bg_ignore_sample_half_width(half_width_keV)

    def set_background_prefit_mode(self, mode: str):
        for rec in self.records.values():
            rec.set_background_prefit_mode(mode)

    def set_background_polynomial_order(self, order: int):
        for rec in self.records.values():
            rec.set_background_polynomial_order(order)

    def set_display_signal_mode(self, mode: str):
        self.display_signal_mode_default = mode
        rec = self.active_record
        if rec is not None:
            rec.set_display_signal_mode(mode)

    def set_peak_sum_signal_mode(self, mode: str):
        self.peak_sum_signal_mode_default = mode
        rec = self.active_record
        if rec is not None:
            rec.set_peak_sum_signal_mode(mode)

    def set_bg_correction(self, active: bool):
        """Enable/disable background subtraction for all records."""
        mode = 'measured_bg_subtracted' if active else 'raw'
        self.display_signal_mode_default = mode
        self.peak_sum_signal_mode_default = mode
        for rec in self.records.values():
            rec.set_bg_correction(active)

    def set_unit_and_bg(self, unit: str, bg_correct: bool):
        """Set unit and background correction for all records (legacy method)."""
        mode = 'measured_bg_subtracted' if bg_correct else 'raw'
        self.display_signal_mode_default = mode
        self.peak_sum_signal_mode_default = mode
        for rec in self.records.values():
            rec.set_unit_and_bg(unit, bg_correct)
    
    def set_bg_correction_mode(self, mode: str):
        """Set background correction mode for all records: 'none', 'subtract_fitted', or 'subtract_spectra'."""
        mode_map = {
            'none': 'raw',
            'subtract_spectra': 'measured_bg_subtracted',
            'subtract_fitted': 'fitted_reference_bg_subtracted',
        }
        if mode not in mode_map:
            raise ValueError("mode must be 'none', 'subtract_fitted', or 'subtract_spectra'")
        self.display_signal_mode_default = mode_map[mode]
        self.peak_sum_signal_mode_default = mode_map[mode]
        for rec in self.records.values():
            rec.set_bg_correction_mode(mode)
    
    def set_bg_elements(self, elements: List[str]):
        """Set background elements for all records."""
        for rec in self.records.values():
            rec.set_bg_elements(elements)
    
    def set_bg_fit_mode(self, mode: str):
        """
        Set background fit mode for all records: 'bg_elements' or 'bg_spec'.
        If mode is 'bg_spec', ensure a background spectrum is loaded first.
        """
        # Check if bg_spec mode requires background
        if mode == 'bg_spec':
            if not self.records:
                raise ValueError("No records loaded")
            first_rec = next(iter(self.records.values()))
            if first_rec._background is None:
                raise ValueError("Cannot set bg_fit_mode to 'bg_spec' without a background spectrum. Load one first.")
        
        for rec in self.records.values():
            rec.set_bg_fit_mode(mode)
    
    def set_background(self, bg_path: str):
        """Load and set background spectrum for all records."""
        bg_path = _prefer_hspy_path(bg_path)
        bg_signal = hs.load(bg_path)
        if not isinstance(bg_signal, exspy.signals.EDSTEMSpectrum):
            print(f"Error: The loaded background is not an EDSTEMSpectrum (got {type(bg_signal)}).")
            return
        
        # Set default energy resolution to 128 eV for background spectrum too
        bg_signal.set_microscope_parameters(energy_resolution_MnKa=128)
        
        for rec in self.records.values():
            rec.set_background(bg_signal)
            rec.bg_file = bg_path
