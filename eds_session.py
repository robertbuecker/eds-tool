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
        self.signal = hs.load(path)
        self.signal.metadata.set_item('General.title', os.path.splitext(os.path.basename(path))[0])
        self.signal.metadata.set_item('General.original_filename', path)
        self.model: Optional[exspy.models.EDSTEMModel] = None
        self.intensities: Optional[List[hs.BaseSignal]] = None
        self.fitted_intensities: Optional[List[hs.BaseSignal]] = None

    @property
    def name(self) -> str:
        return self.signal.metadata.get_item('General.title', default=os.path.basename(self.path))

    @property
    def elements(self) -> List[str]:
        return self.signal.metadata.get_item('Sample.elements', default=[])

    def set_elements(self, elements: List[str]):
        if not elements:
            print(f"Warning: No elements provided for {self.name}")
            return
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

    def get_live_time(self) -> Optional[float]:
        """Get measurement live time from metadata, or None if missing."""
        try:
            return float(self.signal.metadata.get_item('Acquisition_instrument.TEM.Detector.EDS.live_time'))
        except Exception:
            return None

    def set_unit(self, unit: str):
        """
        Set signal unit to 'counts' or 'cps'. Invalidate fit and intensities only if changed.
        """
        if unit not in ('counts', 'cps'):
            raise ValueError("unit must be 'counts' or 'cps'")
        current_quantity = self.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
        live_time = self.get_live_time()
        if unit == 'cps':
            if current_quantity == 'X-rays (CPS)':
                return  # Already normalized, do nothing
            if live_time is None or live_time == 0:
                raise ValueError(f"Live time missing or zero for spectrum '{self.name}'")
            self.signal.data = self.signal.data / live_time
            self.signal.metadata.set_item('Signal.quantity', 'X-rays (CPS)')
        elif unit == 'counts':
            if current_quantity == 'X-rays (Counts)':
                return  # Already raw counts, do nothing
            if live_time is None or live_time == 0:
                raise ValueError(f"Live time missing or zero for spectrum '{self.name}'")
            self.signal.data = self.signal.data * live_time
            self.signal.metadata.set_item('Signal.quantity', 'X-rays (Counts)')
        # Invalidate fit and intensities only if changed
        self.intensities = None
        self.model = None
        self.fitted_intensities = None

class EDSSession:
    def __init__(self, paths: Optional[List[str]] = None):
        self.records: Dict[str, EDSSpectrumRecord] = {}
        self.active_name: Optional[str] = None
        if paths:
            self.load(paths)

    def load(self, paths: List[str]):
        # Optionally copy elements from the first existing record
        existing_elements = None
        if self.records:
            first_rec = next(iter(self.records.values()))
            existing_elements = first_rec.elements if first_rec.elements else None

        for rec in [EDSSpectrumRecord(p) for p in paths]:
            if rec.name in self.records:
                print(f"Warning: Spectrum '{rec.name}' already loaded, skipping.")
                continue
            # Copy elements if available
            if existing_elements:
                rec.set_elements(existing_elements)
            self.records[rec.name] = rec
        if self.records and self.active_name is None:
            self.active_name = next(iter(self.records))

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
            rec.plot(use_model=use_model, ax=ax, fig=fig, **kwargs)

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