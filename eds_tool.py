import sys
import warnings
import logging
import os
from typing import Optional, List
import io

# Suppress all warnings and logging
warnings.filterwarnings('ignore')
logging.disable(logging.WARNING)

# Redirect stderr during imports to suppress hyperspy/rsciio numba warnings
_stderr_backup = sys.stderr
sys.stderr = io.StringIO()

import matplotlib
import os
import argparse
from eds_session import EDSSession

# GUI imports - only used when not in auto mode, but needed for class definition
try:
    from qtpy import QtWidgets, QtCore
    from qtpy.QtGui import QIcon
    from intensity_table_dialog import IntensityTableDialog
    import matplotlib.pyplot as plt
    import exspy
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

# Restore stderr after imports
sys.stderr = _stderr_backup

ICON_PATH = os.path.join(os.path.dirname(__file__), "eds_icon.png")
# print(f"Icon path: {ICON_PATH}")

# Configuration for auto workflow exports
AUTO_SPECTRUM_FORMATS = ['emsa', 'csv']  # Formats for spectrum export
AUTO_PLOT_FORMATS = ['png', 'svg', 'jpg']  # Formats for plot export (BMP not supported by matplotlib)
SIGNAL_MODE_ITEMS = [
    ("raw", "Raw"),
    ("fitted_reference_bg_subtracted", "Fitted reference"),
    ("measured_bg_subtracted", "Subtract measured"),
]

BACKGROUND_FIT_MODE_ITEMS = [
    ("none", "None"),
    ("bg_elements", "BG Elements"),
    ("bg_spec", "Ref BG Spec"),
]

BACKGROUND_PREFIT_MODE_ITEMS = [
    ("off", "Off"),
    ("exclude_sample", "Exclude sample"),
    ("bg_elements_only", "BG el. only"),
]

def auto_workflow(session: EDSSession, max_energy: Optional[float] = None, use_cps: bool = False):
    """
    Automatic workflow for EDS analysis without GUI.
    
    Steps:
    1. Set units (counts or CPS)
    2. Compute intensities for all spectra (using summing, not fitting)
    3. Export spectra in configured formats (EMSA, CSV by default)
    4. Export plots in configured formats (PNG, SVG, JPG by default)
    5. Export intensity table to the longest common folder
    """
    # Suppress stderr during exspy import to hide numba warnings
    _stderr_backup = sys.stderr
    sys.stderr = io.StringIO()
    import exspy
    sys.stderr = _stderr_backup
    
    print("Running automatic EDS workflow...")
    
    # Set units
    unit = "cps" if use_cps else "counts"
    print(f"Using units: {unit.upper()}")
    session.set_unit_and_bg(unit, False)
    
    if not session.records:
        print("Error: No spectra loaded. Please provide spectrum files or directories.")
        return
    
    # Step 1: Compute intensities for all spectra
    print(f"\n1. Computing intensities for {len(session.records)} spectra...")
    session.compute_all_intensities()
    
    # Check if any intensities were computed
    computed_count = sum(1 for rec in session.records.values() if rec.intensities is not None)
    print(f"   Intensities computed for {computed_count}/{len(session.records)} spectra.")
    
    # Step 2: Export spectra
    print(f"\n2. Exporting spectra in formats: {', '.join(AUTO_SPECTRUM_FORMATS)}...")
    for rec in session.records.values():
        try:
            rec.export(formats=AUTO_SPECTRUM_FORMATS)
            print(f"   Exported: {rec.name}")
        except Exception as e:
            print(f"   Error exporting {rec.name}: {e}")
    
    # Step 3: Export plots
    print(f"\n3. Exporting plots in formats: {', '.join(AUTO_PLOT_FORMATS)}...")
    for rec in session.records.values():
        try:
            rec.export_plot(formats=AUTO_PLOT_FORMATS, max_energy=max_energy)
            print(f"   Plotted: {rec.name}")
        except Exception as e:
            print(f"   Error plotting {rec.name}: {e}")
    
    # Step 4: Export individual intensity CSVs
    print("\n4. Exporting individual intensity files...")
    for rec in session.records.values():
        if rec.intensities:
            try:
                rec.export_intensities_csv()
                print(f"   Exported intensities: {rec.name}")
            except Exception as e:
                print(f"   Error exporting intensities for {rec.name}: {e}")
    
    # Step 5: Export intensity table to longest common folder
    print("\n5. Exporting combined intensity table...")
    if len(session.records) > 1:
        try:
            common_folder = os.path.commonpath([rec.path for rec in session.records.values()])
        except ValueError:
            # No common path (e.g., different drives on Windows)
            common_folder = None
    else:
        # Single file - use its directory
        common_folder = os.path.dirname(list(session.records.values())[0].path)
    
    if common_folder:
        try:
            session.export_intensity_table(common_folder, fitted=False)
        except Exception as e:
            print(f"   Error exporting intensity table: {e}")
    else:
        print("   Warning: Could not determine common folder for intensity table.")
    
    print("\nAutomatic workflow completed!")

class NavigatorWidget(QtWidgets.QWidget if GUI_AVAILABLE else object):
    def __init__(self, session: EDSSession):
        super().__init__()
        self.session = session
        self.setWindowTitle("EDS signals")
        self.setWindowIcon(QIcon(ICON_PATH))  # Set icon for navigator
        self.table_views: dict[str, QtWidgets.QDialog] = {}
        self._pending_first_show_layout_fix = True
        self._plot_initialized = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        self.popup = QtWidgets.QDialog(self)
        self.popup.setWindowTitle("X-ray lines")
        self.popup.setWindowIcon(QIcon(ICON_PATH))  # Set icon for popup
        self.popup.setModal(False)
        popup_layout = QtWidgets.QVBoxLayout(self.popup)
        self.popup_browser = QtWidgets.QTextBrowser()
        popup_layout.addWidget(self.popup_browser)
        self.popup_browser.anchorClicked.connect(self._on_popup_link_clicked)        

        spectrum_group = QtWidgets.QGroupBox("Spectrum Management")
        spectrum_layout = QtWidgets.QVBoxLayout(spectrum_group)
        spectrum_layout.setContentsMargins(10, 14, 10, 10)
        spectrum_layout.setSpacing(8)

        self.add_file_btn = QtWidgets.QPushButton("Add .eds File")
        self.add_dir_btn = QtWidgets.QPushButton("Add Directory (recursive)")
        self.add_file_btn.clicked.connect(self.add_file)
        self.add_dir_btn.clicked.connect(self.add_directory)

        list_header = QtWidgets.QHBoxLayout()
        list_header.addWidget(QtWidgets.QLabel("Loaded spectra"))
        list_header.addStretch()
        self.spectrum_count_label = QtWidgets.QLabel("")
        self.spectrum_count_label.setStyleSheet("QLabel { color: #666; }")
        list_header.addWidget(self.spectrum_count_label)
        spectrum_layout.addLayout(list_header)

        self.list = QtWidgets.QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.setUniformItemSizes(True)
        self.list.setMinimumHeight(280)
        self.list.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        for name in self.session.records:
            self.list.addItem(name)
        self.list.currentRowChanged.connect(self.on_spectrum_changed)

        spectrum_body = QtWidgets.QHBoxLayout()
        spectrum_body.setSpacing(10)
        spectrum_body.addWidget(self.list, 1)

        spectrum_actions_widget = QtWidgets.QWidget()
        spectrum_actions_widget.setMinimumWidth(170)
        spectrum_actions_widget.setMaximumWidth(190)
        spectrum_actions_widget.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        spectrum_actions = QtWidgets.QVBoxLayout(spectrum_actions_widget)
        spectrum_actions.setContentsMargins(0, 0, 0, 0)
        spectrum_actions.setSpacing(6)

        self.remove_spec_btn = QtWidgets.QPushButton("Remove Selected")
        self.remove_all_btn = QtWidgets.QPushButton("Remove All")
        self.remove_spec_btn.setMinimumHeight(28)
        self.remove_all_btn.setMinimumHeight(28)
        self.add_file_btn.setMinimumHeight(28)
        self.add_dir_btn.setMinimumHeight(28)
        spectrum_actions.addWidget(self.add_file_btn)
        spectrum_actions.addWidget(self.add_dir_btn)
        spectrum_actions.addSpacing(4)
        spectrum_actions.addWidget(self.remove_spec_btn)
        spectrum_actions.addWidget(self.remove_all_btn)
        self.remove_spec_btn.clicked.connect(self.remove_selected_spectrum)
        self.remove_all_btn.clicked.connect(self.remove_all_spectra)

        self.export_selected_btn = QtWidgets.QPushButton("Export Selected")
        self.export_all_btn = QtWidgets.QPushButton("Export All")
        self.export_selected_btn.setMinimumHeight(28)
        self.export_all_btn.setMinimumHeight(28)
        spectrum_actions.addSpacing(4)
        spectrum_actions.addWidget(self.export_selected_btn)
        spectrum_actions.addWidget(self.export_all_btn)
        self.export_selected_btn.clicked.connect(self.export_selected_spectrum)
        self.export_all_btn.clicked.connect(self.export_all_spectra)

        self.ask_folder_checkbox = QtWidgets.QCheckBox("Ask for folder")
        self.format_entry = QtWidgets.QLineEdit("emsa, csv")
        self.ask_folder_checkbox.setMinimumHeight(22)
        self.format_entry.setMinimumHeight(26)
        spectrum_actions.addSpacing(4)
        spectrum_actions.addWidget(self.ask_folder_checkbox)
        spectrum_actions.addWidget(QtWidgets.QLabel("Formats:"))
        spectrum_actions.addWidget(self.format_entry)
        spectrum_actions.addStretch()

        spectrum_body.addWidget(spectrum_actions_widget)
        spectrum_layout.addLayout(spectrum_body, 1)

        setup_group = QtWidgets.QGroupBox("Elements and Background")
        setup_layout = QtWidgets.QVBoxLayout(setup_group)
        setup_layout.setContentsMargins(10, 14, 10, 10)
        setup_layout.setSpacing(8)

        el_layout = QtWidgets.QHBoxLayout()
        self.el_edit = QtWidgets.QLineEdit(",".join(self.session.active_record.elements if self.session.active_record else []))
        self.el_edit.setClearButtonEnabled(True)
        el_apply = QtWidgets.QPushButton("Apply")
        el_layout.addWidget(QtWidgets.QLabel("Elements:"))
        el_layout.addWidget(self.el_edit, 1)
        el_layout.addWidget(el_apply)
        setup_layout.addLayout(el_layout)
        el_apply.clicked.connect(self.apply_elements)

        element_hint = QtWidgets.QLabel("Right-click the spectrum plot to add nearby X-ray lines.")
        element_hint.setWordWrap(True)
        element_hint.setStyleSheet("QLabel { color: #666; }")
        setup_layout.addWidget(element_hint)

        fit_bg_row = QtWidgets.QHBoxLayout()
        fit_bg_row.addWidget(QtWidgets.QLabel("Fit background:"))
        self.fit_bg_combo = QtWidgets.QComboBox()
        for _mode, label in BACKGROUND_FIT_MODE_ITEMS:
            self.fit_bg_combo.addItem(label)
        self.fit_bg_combo.setCurrentIndex(2)
        fit_bg_row.addWidget(self.fit_bg_combo, 1)
        setup_layout.addLayout(fit_bg_row)
        self.fit_bg_combo.currentIndexChanged.connect(self._on_fit_bg_mode_changed)

        bg_el_layout = QtWidgets.QHBoxLayout()
        self.bg_el_edit = QtWidgets.QLineEdit(",".join(self.session.active_record.bg_elements if self.session.active_record else []))
        self.bg_el_edit.setClearButtonEnabled(True)
        self.bg_el_apply_btn = QtWidgets.QPushButton("Apply")
        bg_el_layout.addWidget(QtWidgets.QLabel("BG elements:"))
        bg_el_layout.addWidget(self.bg_el_edit, 1)
        bg_el_layout.addWidget(self.bg_el_apply_btn)
        setup_layout.addLayout(bg_el_layout)
        self.bg_el_apply_btn.clicked.connect(self.apply_bg_elements)

        self.bg_file_label = QtWidgets.QLabel("No reference BG loaded")
        self.bg_file_label.setStyleSheet(
            "QLabel { padding: 6px 8px; background: #f5f5f5; border: 1px solid #d9d9d9; border-radius: 4px; color: #555; }"
        )

        bg_row = QtWidgets.QHBoxLayout()
        self.bg_open_btn = QtWidgets.QPushButton("Open Ref BG")
        bg_row.addWidget(self.bg_open_btn)
        bg_row.addWidget(self.bg_file_label, 1)
        setup_layout.addLayout(bg_row)
        self.bg_open_btn.clicked.connect(self._on_bg_open)

        self.fitting_group = QtWidgets.QGroupBox("Fitting and Quantification")
        fitting_layout = QtWidgets.QVBoxLayout(self.fitting_group)
        fitting_layout.setContentsMargins(10, 14, 10, 10)
        fitting_layout.setSpacing(8)

        fitting_grid = QtWidgets.QGridLayout()
        fitting_grid.setHorizontalSpacing(10)
        fitting_grid.setVerticalSpacing(8)
        fitting_grid.setColumnStretch(1, 1)
        fitting_grid.setColumnStretch(2, 1)

        selected_header = QtWidgets.QLabel("Selected")
        selected_header.setAlignment(QtCore.Qt.AlignCenter)
        all_header = QtWidgets.QLabel("All Loaded")
        all_header.setAlignment(QtCore.Qt.AlignCenter)
        fitting_grid.addWidget(selected_header, 0, 1)
        fitting_grid.addWidget(all_header, 0, 2)

        self.intensity_btn = QtWidgets.QPushButton("Compute")
        self.intensity_all_btn = QtWidgets.QPushButton("Compute")
        fitting_grid.addWidget(QtWidgets.QLabel("Intensities"), 1, 0)
        fitting_grid.addWidget(self.intensity_btn, 1, 1)
        fitting_grid.addWidget(self.intensity_all_btn, 1, 2)
        self.intensity_btn.clicked.connect(self.compute_intensities_active)
        self.intensity_all_btn.clicked.connect(self.compute_intensities_all)

        self.fit_btn = QtWidgets.QPushButton("Fit")
        self.fit_all_btn = QtWidgets.QPushButton("Fit")
        fitting_grid.addWidget(QtWidgets.QLabel("Fit model"), 2, 0)
        fitting_grid.addWidget(self.fit_btn, 2, 1)
        fitting_grid.addWidget(self.fit_all_btn, 2, 2)
        self.fit_btn.clicked.connect(self.fit_spectrum_active)
        self.fit_all_btn.clicked.connect(self.fit_spectrum_all)

        self.finetune_btn = QtWidgets.QPushButton("Refine")
        self.finetune_all_btn = QtWidgets.QPushButton("Apply")
        fitting_grid.addWidget(QtWidgets.QLabel("Fine-tune"), 3, 0)
        fitting_grid.addWidget(self.finetune_btn, 3, 1)
        fitting_grid.addWidget(self.finetune_all_btn, 3, 2)
        self.finetune_btn.clicked.connect(self.fine_tune_active)
        self.finetune_all_btn.clicked.connect(self.fine_tune_all)

        self.remove_fit_btn = QtWidgets.QPushButton("Clear")
        self.remove_all_fit_btn = QtWidgets.QPushButton("Clear")
        fitting_grid.addWidget(QtWidgets.QLabel("Delete fit"), 4, 0)
        fitting_grid.addWidget(self.remove_fit_btn, 4, 1)
        fitting_grid.addWidget(self.remove_all_fit_btn, 4, 2)
        self.remove_fit_btn.clicked.connect(self.remove_fit_active)
        self.remove_all_fit_btn.clicked.connect(self.remove_fit_all)

        fitting_layout.addLayout(fitting_grid)

        self.advanced_peak_toggle = QtWidgets.QToolButton()
        self.advanced_peak_toggle.setText("Advanced")
        self.advanced_peak_toggle.setCheckable(True)
        self.advanced_peak_toggle.setChecked(False)
        self.advanced_peak_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.advanced_peak_toggle.setArrowType(QtCore.Qt.RightArrow)
        fitting_layout.addWidget(self.advanced_peak_toggle)

        self.advanced_peak_widget = QtWidgets.QWidget()
        peak_advanced_layout = QtWidgets.QVBoxLayout(self.advanced_peak_widget)
        peak_advanced_layout.setContentsMargins(12, 0, 0, 0)
        peak_advanced_layout.setSpacing(6)

        peak_layout = QtWidgets.QHBoxLayout()
        peak_layout.addWidget(QtWidgets.QLabel("Peak-sum source:"))
        self.peak_sum_mode_combo = QtWidgets.QComboBox()
        for mode, label in SIGNAL_MODE_ITEMS:
            self.peak_sum_mode_combo.addItem(label, mode)
        peak_layout.addWidget(self.peak_sum_mode_combo, 1)
        peak_advanced_layout.addLayout(peak_layout)

        fit_range_row = QtWidgets.QHBoxLayout()
        fit_range_row.addWidget(QtWidgets.QLabel("Fit range:"))
        self.fit_lower_spin = QtWidgets.QDoubleSpinBox()
        self.fit_lower_spin.setDecimals(2)
        self.fit_lower_spin.setRange(0.0, 39.99)
        self.fit_lower_spin.setSingleStep(0.05)
        self.fit_lower_spin.setSuffix(" kV")
        self.fit_lower_spin.setValue(self.session.active_record.fit_energy_min_keV if self.session.active_record else 0.1)
        self.fit_upper_spin = QtWidgets.QDoubleSpinBox()
        self.fit_upper_spin.setDecimals(2)
        self.fit_upper_spin.setRange(0.01, 40.0)
        self.fit_upper_spin.setSingleStep(0.5)
        self.fit_upper_spin.setSuffix(" kV")
        self.fit_upper_spin.setValue(self.session.active_record.fit_energy_max_keV if self.session.active_record else 40.0)
        fit_range_row.addWidget(self.fit_lower_spin)
        fit_range_row.addWidget(QtWidgets.QLabel("to"))
        fit_range_row.addWidget(self.fit_upper_spin)
        peak_advanced_layout.addLayout(fit_range_row)

        ignore_row = QtWidgets.QHBoxLayout()
        ignore_row.addWidget(QtWidgets.QLabel("Ignore sample ±"))
        self.ignore_sample_spin = QtWidgets.QDoubleSpinBox()
        self.ignore_sample_spin.setDecimals(2)
        self.ignore_sample_spin.setRange(0.0, 2.0)
        self.ignore_sample_spin.setSingleStep(0.05)
        self.ignore_sample_spin.setSuffix(" kV")
        self.ignore_sample_spin.setValue(
            self.session.active_record.reference_bg_ignore_sample_half_width_keV if self.session.active_record else 0.0
        )
        ignore_row.addWidget(self.ignore_sample_spin)
        ignore_row.addStretch()
        peak_advanced_layout.addLayout(ignore_row)

        bg_prefit_row = QtWidgets.QHBoxLayout()
        bg_prefit_row.addWidget(QtWidgets.QLabel("BG prefit:"))
        self.bg_prefit_combo = QtWidgets.QComboBox()
        for mode, label in BACKGROUND_PREFIT_MODE_ITEMS:
            self.bg_prefit_combo.addItem(label, mode)
        bg_prefit_row.addWidget(self.bg_prefit_combo, 1)
        peak_advanced_layout.addLayout(bg_prefit_row)

        poly_row = QtWidgets.QHBoxLayout()
        poly_row.addWidget(QtWidgets.QLabel("Poly order:"))
        self.poly_order_spin = QtWidgets.QSpinBox()
        self.poly_order_spin.setRange(1, 12)
        self.poly_order_spin.setValue(
            self.session.active_record.background_polynomial_order if self.session.active_record else 6
        )
        poly_row.addWidget(self.poly_order_spin)
        poly_row.addStretch()
        peak_advanced_layout.addLayout(poly_row)

        self.peak_sum_help_label = QtWidgets.QLabel("")
        self.peak_sum_help_label.setWordWrap(True)
        self.peak_sum_help_label.setStyleSheet("QLabel { color: #666; }")
        peak_advanced_layout.addWidget(self.peak_sum_help_label)
        self.advanced_peak_widget.setVisible(False)
        fitting_layout.addWidget(self.advanced_peak_widget)

        self.advanced_peak_toggle.toggled.connect(self._toggle_advanced_peak_controls)
        self.peak_sum_mode_combo.currentIndexChanged.connect(self._on_peak_sum_mode_changed)
        self.fit_lower_spin.valueChanged.connect(self._on_fit_range_changed)
        self.fit_upper_spin.valueChanged.connect(self._on_fit_range_changed)
        self.ignore_sample_spin.valueChanged.connect(self._on_ignore_sample_changed)
        self.bg_prefit_combo.currentIndexChanged.connect(self._on_bg_prefit_mode_changed)
        self.poly_order_spin.valueChanged.connect(self._on_poly_order_changed)

        self.display_group = QtWidgets.QGroupBox("Display and Tables")
        display_layout = QtWidgets.QVBoxLayout(self.display_group)
        display_layout.setContentsMargins(10, 14, 10, 10)
        display_layout.setSpacing(8)

        view_row = QtWidgets.QHBoxLayout()
        view_row.addWidget(QtWidgets.QLabel("View:"))
        self.display_mode_combo = QtWidgets.QComboBox()
        for mode, label in SIGNAL_MODE_ITEMS:
            self.display_mode_combo.addItem(label, mode)
        view_row.addWidget(self.display_mode_combo, 1)
        self.residual_checkbox = QtWidgets.QCheckBox("Resid.")
        self.residual_checkbox.setChecked(True)
        self.residual_checkbox.stateChanged.connect(self.toggle_residual)
        self.background_checkbox = QtWidgets.QCheckBox("Ref BG")
        self.background_checkbox.setChecked(False)
        self.background_checkbox.stateChanged.connect(self.toggle_background)
        self.show_bg_elements_checkbox = QtWidgets.QCheckBox("BG el.")
        self.show_bg_elements_checkbox.setChecked(False)
        self.show_bg_elements_checkbox.stateChanged.connect(self.toggle_bg_elements)
        view_row.addWidget(self.residual_checkbox)
        view_row.addWidget(self.background_checkbox)
        view_row.addWidget(self.show_bg_elements_checkbox)
        display_layout.addLayout(view_row)
        self.display_mode_combo.currentIndexChanged.connect(self._on_display_mode_changed)

        unit_row = QtWidgets.QHBoxLayout()
        self.reset_zoom_btn = QtWidgets.QPushButton("Reset Zoom")
        self.reset_y_btn = QtWidgets.QPushButton("Reset Y")
        self.log_checkbox = QtWidgets.QCheckBox("Log")
        self.signal_unit_label = QtWidgets.QLabel("Unit:")
        self.unit_counts_radio = QtWidgets.QRadioButton("cts")
        self.unit_cps_radio = QtWidgets.QRadioButton("cps")
        self.x_range_label = QtWidgets.QLabel("X lim:")
        self.x_range_combo = QtWidgets.QComboBox()
        for value in (5, 15, 40):
            self.x_range_combo.addItem(f"{value} kV", float(value))
        self.x_range_combo.setCurrentIndex(2)
        unit_row.addWidget(self.reset_zoom_btn)
        unit_row.addWidget(self.reset_y_btn)
        unit_row.addWidget(self.log_checkbox)
        unit_row.addWidget(self.signal_unit_label)
        unit_row.addWidget(self.unit_counts_radio)
        unit_row.addWidget(self.unit_cps_radio)
        unit_row.addWidget(self.x_range_label)
        unit_row.addWidget(self.x_range_combo)
        unit_row.addStretch()
        display_layout.addLayout(unit_row)
        self.unit_counts_radio.setChecked(True)
        self.unit_counts_radio.toggled.connect(self._on_signal_type_changed)
        self.unit_cps_radio.toggled.connect(self._on_signal_type_changed)
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        self.reset_y_btn.clicked.connect(self.reset_y)
        self.log_checkbox.stateChanged.connect(self.toggle_log_y)
        self.x_range_combo.currentIndexChanged.connect(self._on_x_range_changed)

        # Row 10: Intensities (sum) | Intensities (fit)
        table_row = QtWidgets.QHBoxLayout()
        self.show_summed_table_checkbox = QtWidgets.QCheckBox("Summed intensities")
        self.show_fitted_table_checkbox = QtWidgets.QCheckBox("Fitted intensities")
        table_row.addWidget(self.show_summed_table_checkbox)
        table_row.addWidget(self.show_fitted_table_checkbox)
        display_layout.addLayout(table_row)
        self.show_summed_table_checkbox.stateChanged.connect(self.toggle_summed_table)
        self.show_fitted_table_checkbox.stateChanged.connect(self.toggle_fitted_table)

        layout.addWidget(spectrum_group, 1)
        layout.addWidget(setup_group)
        layout.addWidget(self.fitting_group)
        layout.addWidget(self.display_group)

        self._update_spectrum_count_label()

        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            screen_geom = screen.availableGeometry()
        else:
            screen_geom = QtCore.QRect(0, 0, 1920, 1080)

        nav_width = max(420, min(460, int(screen_geom.width() * 0.26)))
        nav_height = max(760, min(860, int(screen_geom.height() * 0.86)))
        self.setMinimumSize(420, 720)
        self.resize(nav_width, nav_height)

        max_fig_width = max(720, screen_geom.width() - nav_width - 40)
        fig_width = min(int(screen_geom.width() * 0.54), max_fig_width)
        fig_height = min(max(680, int(screen_geom.height() * 0.82)), screen_geom.height())

        total_width = nav_width + fig_width + 20
        total_height = max(nav_height, fig_height)
        x0 = screen_geom.left() + max(0, (screen_geom.width() - total_width) // 2)
        y0 = screen_geom.top() + max(0, (screen_geom.height() - total_height) // 2)
        self.move(x0, y0)

        self._initial_plot_geometry = QtCore.QRect(x0 + nav_width + 20, y0, fig_width, fig_height)
        self.fig = None
        self.ax = None

        # Set current row after all widgets are created
        self.list.setCurrentRow(0)
        
        # Sync UI state with any command-line loaded background
        rec = self.session.active_record
        if rec is not None:
            mode_index = {mode: i for i, (mode, _label) in enumerate(BACKGROUND_FIT_MODE_ITEMS)}
            with QtCore.QSignalBlocker(self.fit_bg_combo):
                self.fit_bg_combo.setCurrentIndex(mode_index.get(rec.bg_fit_mode, 2))

            # Enable/disable BG elements entry based on fit mode
            bg_elements_enabled = rec.bg_fit_mode == 'bg_elements'
            self.bg_el_edit.setEnabled(bg_elements_enabled)
            self.bg_el_apply_btn.setEnabled(bg_elements_enabled)
            self._update_background_label(rec)
            self._sync_background_mode_controls(rec)
            self._sync_display_controls(rec)
            self._sync_fit_controls(rec)
        
    def _update_spectrum_count_label(self):
        count = len(self.session.records)
        label = "spectrum" if count == 1 else "spectra"
        self.spectrum_count_label.setText(f"{count} {label}")

    def _update_background_label(self, rec=None, path=None):
        if path:
            self.bg_file_label.setText(f"{os.path.basename(path)}")
            return

        rec = rec or self.session.active_record
        if rec is None or rec._background is None:
            self.bg_file_label.setText("No ref BG loaded")
            return

        if (
            hasattr(rec._background, 'metadata')
            and hasattr(rec._background.metadata, 'General')
            and hasattr(rec._background.metadata.General, 'original_filename')
        ):
            bg_name = rec._background.metadata.General.original_filename
            self.bg_file_label.setText(f"{os.path.basename(bg_name)}")
        else:
            self.bg_file_label.setText("Reference BG loaded")
        
    def on_spectrum_changed(self, idx):
        """Handle spectrum selection changes in the list."""
        if idx < 0 or idx >= self.list.count():
            return
        name = self.list.item(idx).text()
        if self.session.active_name == name:
            return  # No change, skip recomputation
        self.session.set_active(name)
        
        # Update elements fields
        self.el_edit.setText(",".join(self.session.active_record.elements))
        self.bg_el_edit.setText(",".join(self.session.active_record.bg_elements))
        
        # Sync UI controls with record state
        rec = self.session.active_record
        if rec is not None:
            mode_index = {mode: i for i, (mode, _label) in enumerate(BACKGROUND_FIT_MODE_ITEMS)}
            with QtCore.QSignalBlocker(self.fit_bg_combo):
                self.fit_bg_combo.setCurrentIndex(mode_index.get(rec.bg_fit_mode, 2))

            # Enable/disable BG elements entry based on fit mode
            bg_elements_enabled = rec.bg_fit_mode == 'bg_elements'
            self.bg_el_edit.setEnabled(bg_elements_enabled)
            self.bg_el_apply_btn.setEnabled(bg_elements_enabled)
            self._update_background_label(rec)
            self._sync_background_mode_controls(rec)
            self._sync_display_controls(rec)
            self._sync_fit_controls(rec)
        
        self.update_plot()

    def _toggle_advanced_peak_controls(self, checked):
        self.advanced_peak_widget.setVisible(checked)
        self.advanced_peak_toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        QtCore.QTimer.singleShot(0, self._resize_for_content_change)

    def _set_signal_mode_combo_state(self, combo, selected_mode, enabled_modes):
        with QtCore.QSignalBlocker(combo):
            for index, (mode, _label) in enumerate(SIGNAL_MODE_ITEMS):
                item = combo.model().item(index)
                if item is not None:
                    item.setEnabled(mode in enabled_modes)
            index = combo.findData(selected_mode)
            if index < 0 or selected_mode not in enabled_modes:
                index = combo.findData('raw')
            combo.setCurrentIndex(index)

    def _get_peak_sum_mode_help_text(self, rec):
        if rec is None:
            return ""
        if rec.bg_fit_mode == 'bg_elements' and rec.has_bg_element_overlap():
            return (
                "Fitted reference BG is unavailable in BG Elements mode when "
                "background elements overlap the sample elements."
            )
        if rec.model is None:
            return (
                "Fit a model to enable fitted reference BG. "
                "Measured subtraction requires a loaded reference BG."
            )
        if rec.bg_fit_mode == 'bg_spec' and rec._background is None:
            return "Load a reference BG to enable BG Spec modeling and measured subtraction."
        return (
            "Peak-sum sources affect get_lines_intensity() only. Fit limits apply to fit/fine-tune. "
            "Ignore sample ± only affects reference-BG shift refinement."
        )

    def _sync_background_mode_controls(self, rec=None):
        rec = rec or self.session.active_record
        if rec is None:
            return

        display_enabled_modes = {'raw'}
        peak_enabled_modes = {'raw'}
        if rec._background is not None:
            display_enabled_modes.add('measured_bg_subtracted')
            peak_enabled_modes.add('measured_bg_subtracted')
        if rec.can_use_fitted_reference_bg_subtraction():
            display_enabled_modes.add('fitted_reference_bg_subtracted')
            peak_enabled_modes.add('fitted_reference_bg_subtracted')

        self._set_signal_mode_combo_state(self.display_mode_combo, rec.display_signal_mode, display_enabled_modes)
        self._set_signal_mode_combo_state(self.peak_sum_mode_combo, rec.peak_sum_signal_mode, peak_enabled_modes)
        self.peak_sum_help_label.setText(self._get_peak_sum_mode_help_text(rec))

    def _get_peak_sum_mode_help_text(self, rec):
        if rec is None:
            return ""
        if rec.bg_fit_mode == 'bg_elements' and rec.has_bg_element_overlap():
            return (
                "Fitted reference BG is unavailable in BG Elements mode when "
                "background elements overlap the sample elements."
            )
        if rec.model is None:
            return (
                "Fit a model to enable fitted reference BG. "
                "Measured subtraction requires a loaded reference BG."
            )
        if rec.bg_fit_mode == 'bg_spec' and rec._background is None:
            return "Load a reference BG to enable BG Spec modeling and measured subtraction."
        return (
            "Peak-sum source only affects get_lines_intensity(). BG prefit runs a two-step fit. "
            "Ignore sample +/- affects BG prefit and reference-BG shift refinement."
        )

    def _sync_fit_controls(self, rec=None):
        rec = rec or self.session.active_record
        if rec is None:
            return
        with QtCore.QSignalBlocker(self.fit_lower_spin), QtCore.QSignalBlocker(self.fit_upper_spin), QtCore.QSignalBlocker(self.ignore_sample_spin), QtCore.QSignalBlocker(self.bg_prefit_combo), QtCore.QSignalBlocker(self.poly_order_spin):
            self.fit_lower_spin.setMaximum(max(0.0, rec.fit_energy_max_keV - 0.01))
            self.fit_upper_spin.setMinimum(rec.fit_energy_min_keV + 0.01)
            self.fit_lower_spin.setValue(rec.fit_energy_min_keV)
            self.fit_upper_spin.setValue(rec.fit_energy_max_keV)
            self.ignore_sample_spin.setValue(rec.reference_bg_ignore_sample_half_width_keV)
            self.bg_prefit_combo.setCurrentIndex(self.bg_prefit_combo.findData(rec.background_prefit_mode))
            self.poly_order_spin.setValue(rec.background_polynomial_order)

    def _on_fit_range_changed(self):
        lower = self.fit_lower_spin.value()
        upper = self.fit_upper_spin.value()
        self.fit_lower_spin.setMaximum(max(0.0, upper - 0.01))
        self.fit_upper_spin.setMinimum(lower + 0.01)
        try:
            self.session.set_fit_energy_range(lower, upper)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Fit Range Error", str(e))
            self._sync_fit_controls()

    def _on_ignore_sample_changed(self):
        try:
            self.session.set_reference_bg_ignore_sample_half_width(self.ignore_sample_spin.value())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Ignore Range Error", str(e))
            self._sync_fit_controls()

    def _on_bg_prefit_mode_changed(self):
        try:
            self.session.set_background_prefit_mode(self.bg_prefit_combo.currentData())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "BG Prefit Error", str(e))
            self._sync_fit_controls()

    def _on_poly_order_changed(self):
        try:
            self.session.set_background_polynomial_order(self.poly_order_spin.value())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Polynomial Order Error", str(e))
            self._sync_fit_controls()

    def _sync_display_controls(self, rec=None):
        rec = rec or self.session.active_record
        uses_model_plot = rec.uses_model_plot() if rec is not None else False
        unit = rec.signal_unit if rec is not None else 'counts'
        effective_unit = 'cps' if uses_model_plot else unit
        with QtCore.QSignalBlocker(self.unit_counts_radio):
            self.unit_counts_radio.setChecked(effective_unit == "counts")
        with QtCore.QSignalBlocker(self.unit_cps_radio):
            self.unit_cps_radio.setChecked(effective_unit == "cps")
        if uses_model_plot:
            self.signal_unit_label.setText("Unit:")
            tooltip = (
                "Model plots always use CPS because fitting and model diagnostics are normalized "
                "to live time. Counts still apply to signal-only views, exports, and peak-sum intensities."
            )
            self.unit_counts_radio.setEnabled(False)
            self.unit_cps_radio.setEnabled(False)
            self.residual_checkbox.setEnabled(True)
            self.residual_checkbox.setToolTip("")
        else:
            self.signal_unit_label.setText("Unit:")
            tooltip = ""
            self.unit_counts_radio.setEnabled(True)
            self.unit_cps_radio.setEnabled(True)
            self.residual_checkbox.setEnabled(False)
            self.residual_checkbox.setToolTip("Fit residuals are only shown on the raw CPS model plot.")

        for widget in (self.signal_unit_label, self.unit_counts_radio, self.unit_cps_radio):
            widget.setToolTip(tooltip)

    def _get_effective_plot_unit(self, rec=None):
        rec = rec or self.session.active_record
        if rec is None:
            return "counts"
        return "cps" if rec.uses_model_plot() else rec.signal_unit

    def _get_current_plot_signal(self, rec=None):
        rec = rec or self.session.active_record
        if rec is None:
            return None
        return rec.get_signal_for_fit() if rec.uses_model_plot() else rec.signal

    def _get_log_lower_bound(self, rec=None):
        rec = rec or self.session.active_record
        if rec is None:
            return 1.0
        if self._get_effective_plot_unit(rec) == "cps":
            live_time = rec.get_live_time()
            if live_time and live_time > 0:
                return 1.0 / live_time
        return 1.0

    def _get_x_range_limit(self, rec=None):
        rec = rec or self.session.active_record
        plot_signal = self._get_current_plot_signal(rec)
        if plot_signal is None:
            return None
        xaxis = plot_signal.axes_manager.signal_axes[0]
        requested = float(self.x_range_combo.currentData())
        return min(xaxis.high_value, requested)

    def _update_fitting_group_title(self, rec=None):
        rec = rec or self.session.active_record
        if rec is None or rec.reduced_chisq is None:
            self.fitting_group.setTitle("Fitting and Quantification")
        else:
            self.fitting_group.setTitle(f"Fitting and Quantification (χ²ᵣ: {rec.reduced_chisq:.4f})")

    def _update_fitting_group_title(self, rec=None):
        rec = rec or self.session.active_record
        if rec is None or rec.reduced_chisq is None:
            self.fitting_group.setTitle("Fitting and Quantification")
        else:
            self.fitting_group.setTitle(
                f"Fitting and Quantification (χ²ᵣ: {rec.reduced_chisq:.4f}, Res: {rec.get_energy_resolution():.2f} eV)"
            )

    def apply_elements(self):
        # Always update elements, even if empty
        els = [e.strip() for e in self.el_edit.text().split(",") if e.strip()]
        self.session.set_elements(els)
        # session.set_elements should handle clearing elements for all records
        self.update_plot()
        # Update tables (they will be empty after element change)
        if self.show_summed_table_checkbox.isChecked():
            self.show_summed_intensity_table()
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()

    def update_plot(self, force_replot=False):
        if not self._plot_initialized:
            if not self.isVisible():
                return
            self._initialize_plot_window()
            self._plot_initialized = True

        rec = self.session.active_record
        if rec is None:
            return

        previous_effective_unit = getattr(self, "_last_effective_plot_unit", None)

        fig, ax = rec.plot(
            use_model=None,  # default: use model if available
            ax=self.ax,
            fig=self.fig,
            show_residual=self.residual_checkbox.isChecked(),
            show_background=self.background_checkbox.isChecked(),
            show_bg_elements=self.show_bg_elements_checkbox.isChecked()
        )
        
        self.fig = fig
        self.ax = ax 
        self._update_fitting_group_title(rec)
        self._sync_background_mode_controls(rec)
        self._sync_display_controls(rec)
        if self.fig is None or self.ax is None:
            return

        current_effective_unit = self._get_effective_plot_unit(rec)
        self._last_effective_plot_unit = current_effective_unit
        if previous_effective_unit is not None and previous_effective_unit != current_effective_unit:
            self.reset_y()

        self.fig.canvas.manager.window.setWindowIcon(QIcon(ICON_PATH))
        plt.show(block=False)
        
        # Connect right-click handler
        if fig is not None:
            fig.canvas.mpl_connect("button_press_event", self._on_right_click)

    def _on_right_click(self, event):
        if event.button == 3 and event.inaxes == self.ax and event.xdata is not None:
            energy = event.xdata
            lines = exspy.utils.eds.get_xray_lines_near_energy(energy, only_lines=['a', 'b'])
            msg = "\n".join(lines)
            self._show_lines_popup(energy, msg)

    def _show_lines_popup(self, energy, msg):
        if msg:
            html = "<br>".join(
                f'<a href="{line.split("_")[0]}">{line}</a>' for line in msg.splitlines()
            )
        else:
            html = "No lines found."
        self.popup.setWindowTitle(f"X-ray lines near {energy:.2f} keV")
        self.popup_browser.setHtml(html)
        self.popup.show()

    def _on_popup_link_clicked(self, qurl):
        element = qurl.toString()
        current_elements = [e.strip() for e in self.el_edit.text().split(",") if e.strip()]
        if element not in current_elements:
            current_elements.append(element)
            self.el_edit.setText(",".join(current_elements))
            self.apply_elements()
        self.popup.close()

    def compute_intensities_active(self):
        rec = self.session.active_record
        if rec is None or not rec.elements:
            QtWidgets.QMessageBox.warning(self, "No Elements Defined", "Please define elements first before computing intensities.")
            return
        rec.compute_intensities()
        # Always show global table, auto-check if needed
        if not self.show_summed_table_checkbox.isChecked():
            self.show_summed_table_checkbox.setChecked(True)
        else:
            self.show_summed_intensity_table()

    def compute_intensities_all(self):
        self.session.compute_all_intensities()
        # Always show global table, auto-check if needed
        if not self.show_summed_table_checkbox.isChecked():
            self.show_summed_table_checkbox.setChecked(True)
        else:
            self.show_summed_intensity_table()

    def fit_spectrum_active(self):
        rec = self.session.active_record
        if rec is None or not rec.elements:
            QtWidgets.QMessageBox.warning(self, "No Elements Defined", "Please define elements first before fitting.")
            return
        
        # Check if BG Spec mode is selected but no background is loaded
        if rec.bg_fit_mode == 'bg_spec' and rec._background is None:
            reply = QtWidgets.QMessageBox.question(
                self, 
                "No Background Loaded",
                "BG Spec mode requires a reference BG spectrum, but none is loaded.\n\n"
                "Would you like to load a reference BG spectrum now?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self._on_bg_open()
                # Check if background was actually loaded
                if rec._background is None:
                    return  # User cancelled, abort fit
            else:
                return  # User declined, abort fit
        
        rec.fit_model()
        # Always show global table, auto-check if needed
        if not self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_table_checkbox.setChecked(True)
        else:
            self.show_fitted_intensity_table()
        self.update_plot(force_replot=True)

    def fit_spectrum_all(self):
        # Check if any spectrum has BG Spec mode but no background loaded
        needs_bg = any(rec.bg_fit_mode == 'bg_spec' and rec._background is None 
                       for rec in self.session.records.values())
        
        if needs_bg:
            reply = QtWidgets.QMessageBox.question(
                self, 
                "No Background Loaded",
                "One or more spectra are set to BG Spec mode, but no reference BG is loaded.\n\n"
                "Would you like to load a reference BG spectrum now?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self._on_bg_open()
                # Check if background was actually loaded
                if self.session.active_record._background is None:
                    return  # User cancelled, abort fit
            else:
                return  # User declined, abort fit
        
        self.session.fit_all_models()
        # Always show global table, auto-check if needed
        if not self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_table_checkbox.setChecked(True)
        else:
            self.show_fitted_intensity_table()
        self.update_plot(force_replot=True)

    def remove_fit_active(self):
        rec = self.session.active_record
        if rec is not None:
            rec.clear_fit()
            self.update_plot(force_replot=True)
            # Update the fitted table view if open
            if self.show_fitted_table_checkbox.isChecked():
                self.show_fitted_intensity_table()

    def remove_fit_all(self):
        for rec in self.session.records.values():
            rec.clear_fit()
        self.update_plot(force_replot=True)
        for title in list(self.table_views.keys()):
            if "Fitted Line Intensities" in title:
                dialog = self.table_views.pop(title, None)
                if dialog is not None:
                    dialog.close()
    
    def fine_tune_active(self):
        """Fine-tune the fitted model for the active spectrum."""
        rec = self.session.active_record
        if rec is None:
            return
        if rec.model is None:
            QtWidgets.QMessageBox.warning(
                self, "No Fitted Model", 
                "Please fit a model first before fine-tuning."
            )
            return
        
        rec.fine_tune_model()
        
        # Update fitted intensity table if visible
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()
        
        self.update_plot(force_replot=True)
    
    def fine_tune_all(self):
        """Apply the active spectrum's refined calibration to all fitted models."""
        rec = self.session.active_record
        if rec is None or rec.model is None:
            QtWidgets.QMessageBox.warning(
                self, "No Fitted Model",
                "Please fit and refine the selected spectrum first."
            )
            return

        try:
            self.session.apply_active_fine_tuning_to_all_models()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Apply Fine-Tuning Error", str(e))
            return
        
        # Update fitted intensity table if visible
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()
        
        self.update_plot(force_replot=True)

    def _show_intensity_table(self, line_names, table_data, title="Line Intensities"):
        geom = None
        if title in self.table_views:
            old_dialog = self.table_views[title]
            geom = old_dialog.geometry()
            old_dialog.close()
        dialog = self.table_views[title] = IntensityTableDialog(self, line_names, table_data, title=title)
        if geom is not None:
            dialog.setGeometry(geom)
        dialog.show()
        def on_dialog_closed(result):
            if title == "Summed Line Intensities":
                if self.show_summed_table_checkbox.isChecked():
                    self.show_summed_table_checkbox.setChecked(False)
            elif title == "Fitted Line Intensities":
                if self.show_fitted_table_checkbox.isChecked():
                    self.show_fitted_table_checkbox.setChecked(False)
            self.table_views.pop(title, None)
        dialog.finished.connect(on_dialog_closed)

    def toggle_log_y(self):
        ax = self.ax
        fig = self.fig
        rec = self.session.active_record
        if ax is not None:
            scale = "log" if self.log_checkbox.isChecked() else "linear"
            ax.set_yscale(scale)
            if scale == 'log':
                ax.set_ylim(bottom=self._get_log_lower_bound(rec))
            if fig is not None:
                fig.canvas.draw_idle()

    def toggle_residual(self):
        self.update_plot(force_replot=True)
    
    def toggle_background(self):
        rec = self.session.active_record
        if (
            self.background_checkbox.isChecked()
            and rec is not None
            and rec.model is None
            and rec._background is not None
            and rec.signal_unit != "cps"
        ):
            self.session.set_unit("cps")
            self._sync_display_controls(rec)
        self.update_plot(force_replot=True)

    def toggle_bg_elements(self):
        self.update_plot(force_replot=True)

    def reset_y(self):
        ax = self.ax
        fig = self.fig
        rec = self.session.active_record
        if ax is None or rec is None:
            return

        x_limits = ax.get_xlim()
        if ax.get_yscale() == 'log':
            ax.autoscale(enable=True, axis='y', tight=True)
            ax.set_xlim(x_limits)
            ax.set_ylim(bottom=self._get_log_lower_bound(rec))
        else:
            ax.autoscale(enable=True, axis='y')
            ax.set_xlim(x_limits)
        if fig is not None:
            fig.canvas.draw_idle()

    def reset_zoom(self):
        ax = self.ax
        fig = self.fig
        rec = self.session.active_record
        if ax is not None and rec is not None:
            plot_signal = self._get_current_plot_signal(rec)
            xaxis = plot_signal.axes_manager.signal_axes[0]
            xmax = self._get_x_range_limit(rec)
            ax.set_xlim(xaxis.low_value, xmax if xmax is not None else xaxis.high_value)
            self.reset_y()
            if fig is not None:
                fig.canvas.draw_idle()

    def _on_x_range_changed(self):
        self.reset_zoom()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_first_show_layout_fix:
            self._pending_first_show_layout_fix = False
            QtCore.QTimer.singleShot(0, self._complete_initial_show)

    def _complete_initial_show(self):
        self._finalize_initial_layout()
        if not self._plot_initialized:
            self._initialize_plot_window()
            self._plot_initialized = True
            self.update_plot()

    def _finalize_initial_layout(self):
        self.ensurePolished()
        self.updateGeometry()
        self._activate_layout_tree(self)
        width = self.width()
        height = self.height()
        self.setUpdatesEnabled(False)
        try:
            self.resize(width, height + 1)
            self.resize(width, height)
            self._activate_layout_tree(self)
        finally:
            self.setUpdatesEnabled(True)
        self.repaint()

    def _resize_for_content_change(self):
        self.ensurePolished()
        self.updateGeometry()
        self._activate_layout_tree(self)
        if not self.isVisible():
            return
        screen = self.screen() or QtWidgets.QApplication.primaryScreen()
        max_height = screen.availableGeometry().height() if screen is not None else 1200
        target_height = min(max(self.minimumHeight(), self.sizeHint().height()), max_height)
        if abs(target_height - self.height()) >= 2:
            self.resize(self.width(), target_height)

    def _activate_layout_tree(self, widget):
        layout = widget.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        for child in widget.findChildren(QtWidgets.QWidget):
            child_layout = child.layout()
            if child_layout is not None:
                child_layout.invalidate()
                child_layout.activate()
            child.updateGeometry()

    def _initialize_plot_window(self):
        plot_geom = self._initial_plot_geometry
        self.fig = plt.figure(
            figsize=(plot_geom.width() / 100, plot_geom.height() / 100),
            dpi=100
        )
        fig_manager = self.fig.canvas.manager
        fig_win = fig_manager.window
        fig_win.setWindowIcon(QIcon(ICON_PATH))
        fig_win.show()
        fig_win.setGeometry(plot_geom)

    def closeEvent(self, event):
        fig = self.fig
        if fig is not None:
            plt.close(fig)
        event.accept()

    def toggle_summed_table(self):
        if self.show_summed_table_checkbox.isChecked():
            self.show_summed_intensity_table()
        else:
            self.close_table("Summed Line Intensities")

    def toggle_fitted_table(self):
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()
        else:
            self.close_table("Fitted Line Intensities")

    def close_table(self, title):
        dlg = self.table_views.pop(title, None)
        if dlg is not None:
            dlg.close()
        # Do NOT uncheck the checkbox here!

    def show_summed_intensity_table(self):
        table_data = []
        line_names = []
        for rec in self.session.records.values():
            if rec.intensities:
                line_names = [sig.metadata.get_item('Sample.xray_lines')[0] for sig in rec.intensities]
                break
        for rec in self.session.records.values():
            if rec.intensities:
                row = [rec.name] + [f"{sig.data[0]:.1f}" for sig in rec.intensities]
                table_data.append(row)
        self._show_intensity_table(line_names, table_data, title="Summed Line Intensities")

    def show_fitted_intensity_table(self):
        table_data = []
        line_names = []
        for rec in self.session.records.values():
            if rec.fitted_intensities:
                line_names = [sig.metadata.get_item('Sample.xray_lines')[0] for sig in rec.fitted_intensities]
                break
        for rec in self.session.records.values():
            if rec.fitted_intensities:
                row = [rec.name] + [f"{sig.data[0]:.1f}" for sig in rec.fitted_intensities]
                table_data.append(row)
        self._show_intensity_table(line_names, table_data, title="Fitted Line Intensities")

    def add_file(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Add .eds File", "", "EDS Files (*.eds)")
        if fname:
            self.session.load([fname])
            self._refresh_spectrum_list()
            # Optionally set elements for new spectra
            self.apply_elements()
            self.update_plot()

    def add_directory(self):
        dname = QtWidgets.QFileDialog.getExistingDirectory(self, "Add Directory")
        if dname:
            from glob import glob
            paths = glob(os.path.join(dname, '**', '*.eds'), recursive=True)
            if paths:
                self.session.load(paths)
                self._refresh_spectrum_list()
                self.apply_elements()
                self.update_plot()

    def remove_selected_spectrum(self):
        idx = self.list.currentRow()
        if idx < 0 or idx >= self.list.count():
            return
        name = self.list.item(idx).text()
        self.session.remove(name)
        self._refresh_spectrum_list()
        # Update plot and tables
        self.update_plot()
        if self.show_summed_table_checkbox.isChecked():
            self.show_summed_intensity_table()
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()
            
    def remove_all_spectra(self):
        # Remove all spectra from the session
        for name in list(self.session.records.keys()):
            self.session.remove(name)
        self.session.active_name = None
        self._refresh_spectrum_list()
        self.update_plot()
        # Update tables if open
        if self.show_summed_table_checkbox.isChecked():
            self.show_summed_intensity_table()
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()            

    # --- Export helper and handler methods (moved out of __init__) ---
    def _get_export_folder_and_formats(self):
        folder = None
        if self.ask_folder_checkbox.isChecked():
            folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Export Folder")
            if not folder:
                return None, None  # User cancelled
        # Parse formats from entry (split by comma or space)
        fmt_text = self.format_entry.text().strip()
        if not fmt_text:
            formats = ["emsa", "csv"]
        else:
            # Split by comma or whitespace
            import re
            formats = [f.strip() for f in re.split(r'[\s,]+', fmt_text) if f.strip()]
        return folder, formats

    def export_selected_spectrum(self):
        rec = self.session.active_record
        if rec is None:
            QtWidgets.QMessageBox.warning(self, "No Spectrum Selected", "Please select a spectrum to export.")
            return
        folder, formats = self._get_export_folder_and_formats()
        if formats is None:
            return  # Cancelled
        try:
            rec.export(folder=folder, formats=formats)
            QtWidgets.QMessageBox.information(self, "Export Complete", f"Exported '{rec.name}' to {folder or os.path.dirname(rec.path)} in formats: {', '.join(formats)}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export Error", str(e))

    def export_all_spectra(self):
        if not self.session.records:
            QtWidgets.QMessageBox.warning(self, "No Spectra", "No spectra loaded to export.")
            return
        folder, formats = self._get_export_folder_and_formats()
        if formats is None:
            return  # Cancelled
        try:
            self.session.export_all(folder=folder, formats=formats)
            QtWidgets.QMessageBox.information(self, "Export Complete", f"Exported all spectra to {folder or 'default folders'} in formats: {', '.join(formats)}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export Error", str(e))

    def _refresh_spectrum_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        for name in self.session.records:
            self.list.addItem(name)
        # Select the new active spectrum if any
        if self.session.active_name and self.session.active_name in self.session.records:
            idx = list(self.session.records.keys()).index(self.session.active_name)
            self.list.setCurrentRow(idx)
        elif self.list.count() > 0:
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._update_spectrum_count_label()
        if not self.session.records:
            self._update_background_label(None)

    def _on_signal_type_changed(self):
        """Handle changes to signal unit (counts/CPS)."""
        if not self.unit_counts_radio.isEnabled() and not self.unit_cps_radio.isEnabled():
            return
        if self.unit_counts_radio.isChecked():
            unit = "counts"
        elif self.unit_cps_radio.isChecked():
            unit = "cps"
        else:
            return
        
        # Apply unit change while preserving bg_correction_mode
        try:
            self.session.set_unit(unit)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Signal Type Error", str(e))

        # Update plot and tables
        self.update_plot()
        if self.show_summed_table_checkbox.isChecked():
            self.show_summed_intensity_table()
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()
    
    def _on_display_mode_changed(self):
        """Handle changes to the display signal source."""
        rec = self.session.active_record
        if rec is None:
            return
        mode = self.display_mode_combo.currentData()
        try:
            self.session.set_display_signal_mode(mode)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Spectrum View Error", str(e))
            self._sync_background_mode_controls(rec)
            return
        self.update_plot()

    def _on_peak_sum_mode_changed(self):
        """Handle changes to the peak-sum intensity source."""
        rec = self.session.active_record
        if rec is None:
            return
        mode = self.peak_sum_mode_combo.currentData()
        try:
            self.session.set_peak_sum_signal_mode(mode)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Peak-Sum Source Error", str(e))
            self._sync_background_mode_controls(rec)
            return

        if self.show_summed_table_checkbox.isChecked():
            self.show_summed_intensity_table()
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()
    
    def _on_fit_bg_mode_changed(self):
        """Handle changes to fit background mode combo box."""
        mode = BACKGROUND_FIT_MODE_ITEMS[self.fit_bg_combo.currentIndex()][0]
        
        # If switching to bg_spec without BG loaded, prompt to load one
        if mode == 'bg_spec':
            if not self.session.records:
                return
            first_rec = next(iter(self.session.records.values()))
            if first_rec._background is None:
                QtWidgets.QMessageBox.information(
                    self, "Reference BG Required",
                    "BG Spec mode requires a reference background spectrum. Please load one using 'Open Ref BG'."
                )
                self._on_bg_open()
                # Check again if BG was loaded
                if first_rec._background is None:
                    # User cancelled, revert to None
                    self.fit_bg_combo.blockSignals(True)
                    self.fit_bg_combo.setCurrentIndex(0)
                    self.fit_bg_combo.blockSignals(False)
                    mode = 'none'
        
        try:
            self.session.set_bg_fit_mode(mode)
            # Update BG elements field enable state
            bg_elements_enabled = mode == 'bg_elements'
            self.bg_el_edit.setEnabled(bg_elements_enabled)
            self.bg_el_apply_btn.setEnabled(bg_elements_enabled)
            self._sync_background_mode_controls()
            self.update_plot(force_replot=True)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Fit BG Mode Error", str(e))
    
    def apply_bg_elements(self):
        """Handle changes to BG elements entry field."""
        text = self.bg_el_edit.text().strip()
        if not text:
            elements = []
        else:
            elements = [e.strip() for e in text.split(',') if e.strip()]
        
        try:
            self.session.set_bg_elements(elements)
            self._sync_background_mode_controls()
            self.update_plot(force_replot=True)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "BG Elements Error", str(e))

    def _on_bg_open(self):
        """Open and load a background spectrum file."""
        # Start in the folder of the active spectrum
        start_dir = ""
        rec = self.session.active_record
        if rec is not None and hasattr(rec, "path"):
            start_dir = os.path.dirname(rec.path)
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Reference Background Spectrum", start_dir, "EDS Files (*.eds)"
        )
        if fname:
            try:
                self.session.set_background(fname)
                self._update_background_label(path=fname)
                
                # Automatically select "BG Spec (recommended)" mode when BG is loaded
                self.fit_bg_combo.blockSignals(True)
                self.fit_bg_combo.setCurrentIndex(2)  # BG Spec
                self.fit_bg_combo.blockSignals(False)
                self.session.set_bg_fit_mode('bg_spec')
                self.bg_el_edit.setEnabled(False)  # Disable BG elements entry
                self.bg_el_apply_btn.setEnabled(False)
                self._sync_background_mode_controls()
                self.update_plot(force_replot=True)
                
                QtWidgets.QMessageBox.information(
                    self, "Reference BG Loaded",
                    f"Reference background spectrum loaded and fit mode set to 'BG Spec':\n{fname}"
                )
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Reference BG Error", str(e))

def main():
    from glob import glob
    p = argparse.ArgumentParser(description="EDS Spectrum Viewer")
    p.add_argument("spectra", nargs="*", help="List of spectra files, or directories to search for .eds files")
    p.add_argument("--elements", type=str, help="Comma‑separated element symbols (e.g. Fe,O,Cu)")
    p.add_argument("--bg-elements", type=str, help="Comma-separated background element symbols (e.g. Cu,Au,Cr)")
    p.add_argument("--bg-spectrum", type=str, help="Path to background spectrum file (.eds)")
    p.add_argument("--energy-resolution", type=float, default=128, help="Energy resolution FWHM at Mn Ka in eV (default: 128)")
    p.add_argument("--auto", action="store_true", help="Run automatic workflow without GUI: load spectra, compute intensities, export spectra/plots/table")
    p.add_argument("--max-energy", type=float, default=None, help="Maximum energy (keV) for plot range in auto mode")
    p.add_argument("--cps", action="store_true", help="Use counts per second (CPS) units instead of counts")
    args = p.parse_args()
    paths = []
    for p in args.spectra:
        if os.path.isfile(p):
            paths.append(p)
        else:
            paths.extend(glob(os.path.join(p,'**','*.eds'), recursive=True))
            print(f"Found {len(paths)} .eds files in directory: {p}")
    
    # if not paths:
    #     print("No spectra files provided. Please provide at least one .eds file or directory containing .eds files.")
    #     sys.exit(1)
    
    session = EDSSession(paths)
    
    # Set energy resolution (default 128 eV)
    session.set_energy_resolution(args.energy_resolution)
    
    if args.elements:
        session.set_elements([e.strip() for e in args.elements.split(',') if e.strip()])
    if args.bg_elements:
        session.set_bg_elements([e.strip() for e in args.bg_elements.split(',')])

    if args.bg_spectrum:
        session.set_background(args.bg_spectrum)
        
    if args.auto:
        # Run automatic workflow without GUI
        auto_workflow(session, max_energy=args.max_energy, use_cps=args.cps)
    else:
        # Start GUI
        if not GUI_AVAILABLE:
            print("Error: GUI modules not available. Install qtpy and related packages.")
            sys.exit(1)
        matplotlib.use('QtAgg')
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        nav = NavigatorWidget(session)
        nav.show()
        app.exec_()

if __name__ == "__main__":
    main()
