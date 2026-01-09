import os
import sys
import io
from typing import List, Dict, Optional, Any
import pandas as pd
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
        
        # New background handling attributes
        self.bg_elements: List[str] = []  # Elements from BG (instrument, holder, etc.)
        self.bg_fit_mode: str = 'bg_spec'  # 'bg_elements' or 'bg_spec'
        self.bg_correction_mode: str = 'none'  # 'none', 'subtract_fitted', 'subtract_spectra'
        
        # Fitted signals (computed after fitting for efficiency)
        self.signal_clean: Optional[exspy.signals.EDSTEMSpectrum] = None  # Signal minus background
        self.signal_bg: Optional[exspy.signals.EDSTEMSpectrum] = None  # Background only
        self.reduced_chisq: Optional[float] = None  # Reduced chi-square from fit

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
            # Plot using hyperspy's built-in method which adds X-ray lines
            if self.elements:
                self.signal.plot(xray_lines=True, navigator=None)
            else:
                self.signal.plot(xray_lines=False, navigator=None)
            
            # Get the figure that was just created
            fig = self.signal._plot.signal_plot.figure
            ax = self.signal._plot.signal_plot.ax
            
            # Set x-axis range if max_energy is specified
            if max_energy is not None:
                energy = self.signal.axes_manager['Energy'].axis
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
            self.signal.set_elements(elements)
            self.intensities = None
            
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
        Takes bg_correction_mode into account:
        - 'none': Use raw signal
        - 'subtract_fitted': Use spec_clean (signal minus fitted instrument component)
        - 'subtract_spectra': Use signal with subtracted background spectrum
        """
        try:
            # Determine which signal to use for intensity computation
            if self.bg_correction_mode == 'subtract_fitted':
                # Need fitted model with 'instrument' component
                if self.model is None or not any(c.name == 'instrument' for c in self.model):
                    print(f"Warning: subtract_fitted mode requires fitted model with 'instrument' component. "
                          f"Falling back to no correction for {self.name}")
                    signal_to_use = self.signal
                else:
                    # Create clean spectrum: signal - instrument component
                    signal_to_use = self.signal - self.model.as_signal(component_list=['instrument'])
            else:
                # Use the current signal (already has bg_correction applied via set_unit_and_bg if needed)
                signal_to_use = self.signal
            
            self.intensities = signal_to_use.get_lines_intensity()
        except Exception as e:
            print(f"Warning: Could not compute intensities for {self.name}: {e}")
            self.intensities = None

    def fit_model(self):
        """
        Fit the model based on bg_fit_mode:
        - 'bg_elements': Temporarily add bg_elements to signal, fit, then restore
        - 'bg_spec': Use ScalableFixedPattern component with background spectrum
        """
        try:
            original_elements = self.elements.copy()
            
            if self.bg_fit_mode == 'bg_elements':
                # Mode 1: Add BG elements to the model
                all_elements = original_elements + self.bg_elements
                self.signal.set_elements(all_elements)
                self.model = self.signal.create_model(auto_add_lines=True, auto_background=True)
                self.model.add_family_lines()
                
            elif self.bg_fit_mode == 'bg_spec':
                # Mode 2: Use ScalableFixedPattern with background spectrum
                if self._background is None:
                    raise ValueError(f"Background spectrum required for bg_fit_mode='bg_spec' but none loaded")
                
                # Create model with only sample elements
                self.signal.set_elements(original_elements)
                self.model = self.signal.create_model(auto_add_lines=True, auto_background=True)
                self.model.add_family_lines()
                
                # Add ScalableFixedPattern component for instrument background
                comp_bg = hs.model.components1D.ScalableFixedPattern(self._background)
                comp_bg.name = 'instrument'
                self.model.append(comp_bg)
            else:
                raise ValueError(f"Unknown bg_fit_mode: {self.bg_fit_mode}")
            
            # Perform the fit
            self.model.fit()
            self.fitted_intensities = self.model.get_lines_intensity()
            
            # Compute reduced chi-square (extract scalar from array if needed)
            if hasattr(self.model, 'red_chisq'):
                chisq_data = self.model.red_chisq.data
                self.reduced_chisq = float(chisq_data) if hasattr(chisq_data, '__float__') else float(chisq_data.item())
            else:
                self.reduced_chisq = None
            
            # Pre-compute clean and background signals for efficiency
            self._compute_fitted_signals()
            
            # Restore original elements if we added bg_elements
            if self.bg_fit_mode == 'bg_elements':
                self.signal.set_elements(original_elements)
                
        except Exception as e:
            print(f"Warning: Could not fit model for {self.name}: {e}")
            self.model = None
            self.fitted_intensities = None
            self.signal_clean = None
            self.signal_bg = None
            self.reduced_chisq = None
    
    def _compute_fitted_signals(self):
        """
        Compute clean and background signals after fitting.
        Called automatically after fit_model() for efficiency.
        """
        if self.model is None:
            self.signal_clean = None
            self.signal_bg = None
            return
        
        try:
            # Identify background components
            bg_component_names = []
            
            if self.bg_fit_mode == 'bg_spec':
                # In bg_spec mode, 'instrument' is the background
                bg_component_names = ['instrument']
            elif self.bg_fit_mode == 'bg_elements':
                # In bg_elements mode, all lines from bg_elements are background
                # Check various ways components might identify their element
                for comp in self.model:
                    comp_element = None
                    
                    # Try different ways to get the element
                    if hasattr(comp, 'element'):
                        comp_element = comp.element
                    elif hasattr(comp, 'name'):
                        # Parse element from name (e.g., 'Cu_Ka' -> 'Cu')
                        name_parts = comp.name.split('_')
                        if len(name_parts) >= 2:
                            comp_element = name_parts[0]
                    
                    if comp_element and comp_element in self.bg_elements:
                        bg_component_names.append(comp.name)
            
            if bg_component_names:
                # Compute background signal (sum of background components)
                self.signal_bg = self.model.as_signal(component_list=bg_component_names)
                
                # Compute clean signal (original minus background)
                self.signal_clean = self.signal - self.signal_bg
            else:
                # No background components found
                self.signal_bg = None
                self.signal_clean = None
                
        except Exception as e:
            print(f"Warning: Could not compute fitted signals for {self.name}: {e}")
            import traceback
            traceback.print_exc()
            self.signal_clean = None
            self.signal_bg = None

    def plot(
        self,
        use_model: Optional[bool] = None,
        ax: Optional[Any] = None,
        fig: Optional[Any] = None,
        show_residual: bool = True,
        show_background: bool = False,
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
        
        # Determine which elements to show
        # In bg_elements mode with a fit, show all elements (sample + bg)
        elements_to_show = self.get_all_elements_for_display()
        show_lines = bool(elements_to_show)
        
        # Temporarily set elements for display if in bg_elements mode with fit
        original_elements = self.signal.metadata.get_item('Sample.elements', default=[])
        if show_lines and elements_to_show != original_elements:
            self.signal.set_elements(elements_to_show)
        
        try:
            if use_model and self.model is not None:
                self.model.plot(
                    xray_lines=show_lines,
                    plot_residual=show_residual,
                    navigator=None,
                    **kwargs
                )
            else:
                self.signal.plot(show_lines, navigator=None, **kwargs)
        finally:
            # Restore original elements
            if elements_to_show != original_elements:
                self.signal.set_elements(original_elements)

        # Extract new fig/ax (check if plot exists)
        if self.signal._plot is None or not hasattr(self.signal._plot, 'signal_plot'):
            return None, None
        
        fig_new = self.signal._plot.signal_plot.figure
        ax_new = self.signal._plot.signal_plot.ax
        
        # Plot background if requested and available
        if show_background and self.signal_bg is not None:
            energy_axis = self.signal_bg.axes_manager['Energy'].axis
            # Fill area with transparency
            ax_new.fill_between(energy_axis, 0, self.signal_bg.data, 
                               color='lightgray', alpha=0.4, 
                               label='Fitted Background')
            # Add line on top with no transparency
            ax_new.plot(energy_axis, self.signal_bg.data, 
                       color='gray', alpha=1.0, linewidth=1.0)
            ax_new.legend(loc='best')

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
        Note: bg_correct parameter is kept for backwards compatibility but now maps to bg_correction_mode.
        If bg_correct=True, uses 'subtract_spectra' mode; if False, uses 'none' mode.
        For new code, use set_bg_correction_mode() directly.
        """
        if unit not in ('counts', 'cps'):
            raise ValueError("unit must be 'counts' or 'cps'")
        
        # Map old bg_correct boolean to new bg_correction_mode
        if bg_correct:
            self.bg_correction_mode = 'subtract_spectra'
        else:
            self.bg_correction_mode = 'none'
        
        self._apply_unit_and_bg_correction(unit)
    
    def set_bg_correction_mode(self, mode: str):
        """
        Set background correction mode: 'none', 'subtract_fitted', or 'subtract_spectra'.
        """
        if mode not in ('none', 'subtract_fitted', 'subtract_spectra'):
            raise ValueError("mode must be 'none', 'subtract_fitted', or 'subtract_spectra'")
        
        self.bg_correction_mode = mode
        
        # Re-apply current unit with new bg_correction_mode
        current_quantity = self.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
        unit = "cps" if "CPS" in current_quantity else "counts"
        self._apply_unit_and_bg_correction(unit)
    
    def _apply_unit_and_bg_correction(self, unit: str):
        """
        Internal method to apply unit conversion and background correction based on current settings.
        """
        current_quantity = self.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
        already_cps = "CPS" in current_quantity
        already_counts = "Counts" in current_quantity
        
        # Check if we need to do anything
        current_bg_mode = self._get_current_bg_mode_from_quantity(current_quantity)
        if ((unit == "cps" and already_cps) or (unit == "counts" and already_counts)) and \
           (current_bg_mode == self.bg_correction_mode):
            return

        # Always start from raw signal
        sig = self._signal
        live_time_sig = self.get_live_time(sig)
        if live_time_sig is None or live_time_sig == 0:
            raise ValueError(f"Live time missing or zero for spectrum '{self.name}'")

        # Apply background correction based on mode
        # Note: 'subtract_fitted' is handled in compute_intensities, not here
        if self.bg_correction_mode == 'subtract_spectra' and self._background is not None:
            bg = self._background
            live_time_bg = self.get_live_time(bg)
            if live_time_bg is None or live_time_bg == 0:
                raise ValueError(f"Live time missing or zero for background spectrum")
            
            # Always keep background in counts
            bg_data = bg.data
            
            # Scale background and subtract
            if unit == "counts":
                scale = live_time_sig / live_time_bg
                sig_data = sig.data - bg_data * scale
            else:  # cps
                sig_data = (sig.data / live_time_sig) - (bg_data / live_time_bg)
            
            self.signal = sig.deepcopy()
            self.signal.data = sig_data
        else:
            # No spectral BG correction (none or subtract_fitted)
            if unit == "counts":
                self.signal = sig.deepcopy()
                self.signal.data = sig.data
            else:  # cps
                self.signal = sig.deepcopy()
                self.signal.data = sig.data / live_time_sig

        # Set quantity string
        bg_suffix = self._get_bg_suffix_for_quantity()
        quantity = f"X-rays ({unit.capitalize()}{bg_suffix})"
        self.signal.metadata.set_item('Signal.quantity', quantity)
        self._bg_correction_active = (self.bg_correction_mode != 'none')

        # Only invalidate intensities, NOT the model (bg_correction_mode doesn't affect fitting)
        # The model stays valid because it was fitted on the original data
        self.intensities = None
        # Note: fitted_intensities from the model remain valid
    
    def _get_current_bg_mode_from_quantity(self, quantity: str) -> str:
        """Extract bg_correction_mode from quantity string."""
        if ", BG Fitted" in quantity:
            return 'subtract_fitted'
        elif ", BG" in quantity:
            return 'subtract_spectra'
        else:
            return 'none'
    
    def _get_bg_suffix_for_quantity(self) -> str:
        """Get suffix for Signal.quantity based on bg_correction_mode."""
        if self.bg_correction_mode == 'subtract_fitted':
            return ', BG Fitted'
        elif self.bg_correction_mode == 'subtract_spectra':
            return ', BG'
        else:
            return ''

    def set_unit(self, unit: str):
        """Legacy: just call set_unit_and_bg with current BG state."""
        self.set_unit_and_bg(unit, self._bg_correction_active)

    def set_bg_correction(self, active: bool):
        """Legacy: just call set_unit_and_bg with current unit."""
        current_quantity = self.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
        unit = "cps" if "CPS" in current_quantity else "counts"
        self.set_unit_and_bg(unit, active)
    
    def set_bg_elements(self, elements: List[str]):
        """Set background elements (used in bg_elements fit mode)."""
        if elements != self.bg_elements:
            self.bg_elements = elements
            # If a fit exists and we're in bg_elements mode, refit with new BG elements
            if self.model is not None and self.bg_fit_mode == 'bg_elements':
                print(f"Refitting model for {self.name} with updated BG elements...")
                self.fit_model()
    
    def set_bg_fit_mode(self, mode: str):
        """
        Set background fitting mode: 'bg_elements' or 'bg_spec'.
        If switching to 'bg_spec' without a background spectrum, raise an error.
        """
        if mode not in ('bg_elements', 'bg_spec'):
            raise ValueError("mode must be 'bg_elements' or 'bg_spec'")
        
        if mode == 'bg_spec' and self._background is None:
            raise ValueError("Cannot set bg_fit_mode to 'bg_spec' without a background spectrum. Load one first.")
        
        if mode != self.bg_fit_mode:
            self.bg_fit_mode = mode
            # Invalidate existing fit
            self.model = None
            self.fitted_intensities = None
    
    def get_all_elements_for_display(self) -> List[str]:
        """
        Get all elements that should be displayed in plots.
        In bg_elements mode with a fit, this includes sample + bg elements.
        Otherwise, just sample elements.
        """
        if self.model is not None and self.bg_fit_mode == 'bg_elements':
            return self.elements + self.bg_elements
        else:
            return self.elements

class EDSSession:
    def __init__(self, paths: Optional[List[str]] = None):
        self.records: Dict[str, EDSSpectrumRecord] = {}
        self.active_name: Optional[str] = None
        if paths:
            self.load(paths)

    def load(self, paths: List[str]):
        # Copy settings from the first existing record if available
        existing_elements = None
        bg_signal = None
        bg_elements = []
        bg_fit_mode = 'bg_spec'
        bg_correction_mode = 'none'
        unit = "counts"
        bg_file = None
        
        if self.records:
            first_rec = next(iter(self.records.values()))
            existing_elements = first_rec.elements if first_rec.elements else None
            bg_signal = first_rec._background
            bg_elements = first_rec.bg_elements
            bg_fit_mode = first_rec.bg_fit_mode
            bg_correction_mode = first_rec.bg_correction_mode
            unit = "cps" if "CPS" in first_rec.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)') else "counts"
            bg_file = getattr(first_rec, "bg_file", None)

        for rec in [EDSSpectrumRecord(p) for p in paths]:
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
            rec.set_bg_correction_mode(bg_correction_mode)
            
            # Apply unit conversion (will use the bg_correction_mode set above)
            current_quantity = rec.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
            current_unit = "cps" if "CPS" in current_quantity else "counts"
            if unit != current_unit:
                rec._apply_unit_and_bg_correction(unit)
            
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
        """Set unit and background correction for all records (legacy method)."""
        for rec in self.records.values():
            rec.set_unit_and_bg(unit, bg_correct)
    
    def set_bg_correction_mode(self, mode: str):
        """Set background correction mode for all records: 'none', 'subtract_fitted', or 'subtract_spectra'."""
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
        bg_signal = hs.load(bg_path)
        if not isinstance(bg_signal, exspy.signals.EDSTEMSpectrum):
            print(f"Error: The loaded background is not an EDSTEMSpectrum (got {type(bg_signal)}).")
            return
        for rec in self.records.values():
            rec.set_background(bg_signal)