import os
from typing import List, Dict, Optional, Any
import hyperspy.api as hs
import exspy
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

class EDSSpectrumRecord:
    def __init__(self, path: str):
        self.path = path
        self._signal = hs.load(path)
        self._signal.metadata.set_item('General.title', os.path.splitext(os.path.basename(path))[0])
        self._signal.metadata.set_item('General.original_filename', path)
        self._background: Optional[exspy.signals.EDSTEMSpectrum] = None
        self._bg_correction_active = False
        self.signal = self._signal  # This will be updated by set_bg_correction
        self.model: Optional[exspy.models.EDSTEMModel] = None
        self.intensities: Optional[List[hs.BaseSignal]] = None
        self.fitted_intensities: Optional[List[hs.BaseSignal]] = None

    @property
    def name(self) -> str:
        return self.signal.metadata.get_item('General.title', default=os.path.basename(self.path))

    @property
    def elements(self) -> List[str]:
        return self.signal.metadata.get_item('Sample.elements', default=[])
    
    def export(self, folder: Optional[str] = None, formats: list | str | tuple = ('csv', 'mas')):
        if isinstance(formats, str):
            formats = [formats]
            
        folder = folder if folder is not None else os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
            
        for fmt in formats:
            if fmt.lower() == 'csv':
                import pandas as pd
                energy = self.signal.axes_manager['Energy'].axis.round(6)
                signal = self.signal.data
                spec_data = pd.DataFrame(signal, index=energy, columns=[self.signal.metadata.get_item('Signal.quantity')])
                spec_data.index.name = 'Energy'
                spec_data.to_csv(os.path.join(folder, f"{self.name}.csv"))
            else:
                target = os.path.join(folder, f"{self.name}.{fmt}")                
                if os.path.exists(target): os.remove(target)
                self.signal.save(target)

    def set_elements(self, elements: List[str]):
        if elements != self.elements:
            self.signal.set_elements(elements)
            self.intensities = None
            self.model = None
            self.fitted_intensities = None

    def compute_intensities(self):
        try:
            self.intensities = self.signal.get_lines_intensity()
        except Exception as e:
            print(f"Warning: Could not compute intensities for {self.name}: {e}")
            self.intensities = None

    def fit_model(self):
        try:
            if self.model is None:
                self.model = self.signal.create_model()
            self.model.fit()
            self.fitted_intensities = self.model.get_lines_intensity()
        except Exception as e:
            print(f"Warning: Could not fit model for {self.name}: {e}")
            self.model = None
            self.fitted_intensities = None

    def plot(
        self,
        use_model: Optional[bool] = None,
        ax: Optional[Any] = None,
        fig: Optional[Any] = None,
        show_residual: bool = True,
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
            use_model = self.model is not None
        show_lines = bool(self.elements)
        if use_model and self.model is not None:
            self.model.plot(
                xray_lines=show_lines,
                plot_residual=show_residual,
                navigator=None,
                **kwargs
            )
        else:
            self.signal.plot(show_lines, navigator=None, **kwargs)

        # Extract new fig/ax
        fig_new = self.signal._plot.signal_plot.figure
        ax_new = self.signal._plot.signal_plot.ax

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
        return self.signal.metadata.as_dictionary()

    def get_live_time(self, signal=None) -> Optional[float]:
        """Get measurement live time from metadata, or None if missing."""
        sig = signal if signal is not None else self._signal
        try:
            return float(sig.metadata.get_item('Acquisition_instrument.TEM.Detector.EDS.live_time'))
        except Exception:
            return None

    def set_background(self, bg_signal: exspy.signals.EDSTEMSpectrum):
        """Set the background signal for subtraction. Always keep in counts."""
        self._background = bg_signal
        # If BG correction is active, recompute signal
        current_quantity = self.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
        bg_active = "BG" in current_quantity
        unit = "cps" if "CPS" in current_quantity else "counts"
        self.set_unit_and_bg(unit, bg_active)

    def set_unit_and_bg(self, unit: str, bg_correct: bool):
        """
        Set signal unit to 'counts' or 'cps', and apply/remove background correction.
        Stores both in Signal.quantity (e.g. 'X-rays (Counts, BG)').
        """
        if unit not in ('counts', 'cps'):
            raise ValueError("unit must be 'counts' or 'cps'")
        current_quantity = self.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
        already_cps = "CPS" in current_quantity
        already_counts = "Counts" in current_quantity
        already_bg = "BG" in current_quantity

        # Only recompute if something changes
        if ((unit == "cps" and already_cps) or (unit == "counts" and already_counts)) and (bg_correct == already_bg):
            return

        # Always start from raw signal
        sig = self._signal
        live_time_sig = self.get_live_time(sig)
        if live_time_sig is None or live_time_sig == 0:
            raise ValueError(f"Live time missing or zero for spectrum '{self.name}'")

        # Prepare background subtraction if needed
        if bg_correct and self._background is not None:
            bg = self._background
            live_time_bg = self.get_live_time(bg)
            if live_time_bg is None or live_time_bg == 0:
                raise ValueError(f"Live time missing or zero for background spectrum")
            # Always keep background in counts
            bg_data = bg.data
            # Scale background appropriately
            if unit == "counts":
                scale = live_time_sig / live_time_bg
                sig_data = sig.data - bg_data * scale
            else:  # CPS
                sig_data = (sig.data / live_time_sig) - (bg_data / live_time_bg)
            self.signal = sig.deepcopy()
            self.signal.data = sig_data
        else:
            # No BG correction
            if unit == "counts":
                self.signal = sig.deepcopy()
                self.signal.data = sig.data
            else:  # CPS
                self.signal = sig.deepcopy()
                self.signal.data = sig.data / live_time_sig

        # Set quantity string
        quantity = f"X-rays ({unit.capitalize()}{', BG' if bg_correct and self._background is not None else ''})"
        self.signal.metadata.set_item('Signal.quantity', quantity)
        self._bg_correction_active = bg_correct and self._background is not None

        # Invalidate fit and intensities
        self.intensities = None
        self.model = None
        self.fitted_intensities = None

    def set_unit(self, unit: str):
        """Legacy: just call set_unit_and_bg with current BG state."""
        self.set_unit_and_bg(unit, self._bg_correction_active)

    def set_bg_correction(self, active: bool):
        """Legacy: just call set_unit_and_bg with current unit."""
        current_quantity = self.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
        unit = "cps" if "CPS" in current_quantity else "counts"
        self.set_unit_and_bg(unit, active)

class EDSSession:
    def __init__(self, paths: Optional[List[str]] = None):
        self.records: Dict[str, EDSSpectrumRecord] = {}
        self.active_name: Optional[str] = None
        if paths:
            self.load(paths)

    def load(self, paths: List[str]):
        # Optionally copy elements from the first existing record
        existing_elements = None
        bg_signal = None
        unit = "counts"
        bg_active = False
        bg_file = None
        if self.records:
            first_rec = next(iter(self.records.values()))
            existing_elements = first_rec.elements if first_rec.elements else None
            bg_signal = first_rec._background
            unit = "cps" if "CPS" in first_rec.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)') else "counts"
            bg_active = first_rec._bg_correction_active
            bg_file = getattr(first_rec, "bg_file", None)

        for rec in [EDSSpectrumRecord(p) for p in paths]:
            if rec.name in self.records:
                print(f"Warning: Spectrum '{rec.name}' already loaded, skipping.")
                continue
            if existing_elements:
                rec.set_elements(existing_elements)
            if bg_signal is not None:
                rec.set_background(bg_signal)
            rec.set_unit_and_bg(unit, bg_active)
            if bg_file:
                rec.bg_file = bg_file
            self.records[rec.name] = rec
        if self.records and self.active_name is None:
            self.active_name = next(iter(self.records))
            
    def export_all(self, folder: Optional[str] = None, formats: list | str | tuple = ('csv', 'mas')):
        for rec in self.records.values():
            rec.export(folder=folder, formats=formats)

    def set_elements(self, elements: List[str]):
        for rec in self.records.values():
            rec.set_elements(elements)

    def compute_all_intensities(self):
        for rec in self.records.values():
            rec.compute_intensities()

    def fit_all_models(self):
        for rec in self.records.values():
            rec.fit_model()

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

    def set_bg_correction(self, active: bool):
        """Enable/disable background subtraction for all records."""
        for rec in self.records.values():
            rec.set_bg_correction(active)

    def set_unit_and_bg(self, unit: str, bg_correct: bool):
        for rec in self.records.values():
            rec.set_unit_and_bg(unit, bg_correct)
    def set_background(self, bg_path: str):
        bg_signal = hs.load(bg_path)
        if not isinstance(bg_signal, exspy.signals.EDSTEMSpectrum):
            print(f"Error: The loaded background is not an EDSTEMSpectrum (got {type(bg_signal)}).")
            return
        for rec in self.records.values():
            rec.set_background(bg_signal)
            rec.set_background(bg_signal)