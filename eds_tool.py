import sys
from qtpy import QtWidgets, QtCore
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
import exspy
import os
import argparse
from eds_session import EDSSession
from qtpy.QtGui import QIcon
from intensity_table_dialog import IntensityTableDialog

ICON_PATH = os.path.join(os.path.dirname(__file__), "eds_icon.png")
# print(f"Icon path: {ICON_PATH}")

class NavigatorWidget(QtWidgets.QWidget):
    def __init__(self, session: EDSSession):
        super().__init__()
        self.session = session
        self.setWindowTitle("EDS signals")
        self.setWindowIcon(QIcon(ICON_PATH))  # Set icon for navigator
        self.table_views: dict[str, QtWidgets.QDialog] = {}
        layout = QtWidgets.QVBoxLayout(self)
        
        self.popup = QtWidgets.QDialog(self)
        self.popup.setWindowTitle("X-ray lines")
        self.popup.setWindowIcon(QIcon(ICON_PATH))  # Set icon for popup
        self.popup.setModal(False)
        popup_layout = QtWidgets.QVBoxLayout(self.popup)
        self.popup_browser = QtWidgets.QTextBrowser()
        popup_layout.addWidget(self.popup_browser)
        self.popup_browser.anchorClicked.connect(self._on_popup_link_clicked)        

        # Row 1: Add file | Add directory
        add_row = QtWidgets.QHBoxLayout()
        self.add_file_btn = QtWidgets.QPushButton("Add .eds File")
        self.add_dir_btn = QtWidgets.QPushButton("Add Directory (recursive)")
        add_row.addWidget(self.add_file_btn)
        add_row.addWidget(self.add_dir_btn)
        layout.addLayout(add_row)
        self.add_file_btn.clicked.connect(self.add_file)
        self.add_dir_btn.clicked.connect(self.add_directory)


        # Row 1a: Elements entry
        el_layout = QtWidgets.QHBoxLayout()
        self.el_edit = QtWidgets.QLineEdit(",".join(self.session.active_record.elements if self.session.active_record else []))
        el_apply = QtWidgets.QPushButton("Apply elements")
        el_layout.addWidget(QtWidgets.QLabel("Elements:"))
        el_layout.addWidget(self.el_edit)
        el_layout.addWidget(el_apply)
        layout.addLayout(el_layout)
        el_apply.clicked.connect(self.apply_elements)
        layout.addWidget(QtWidgets.QLabel("Right-click spectrum to add elements"))

        # Row 2: SPECTRUM LIST
        self.list = QtWidgets.QListWidget()
        for name in self.session.records:
            self.list.addItem(name)
        layout.addWidget(self.list)
        self.list.currentRowChanged.connect(self.on_spectrum_changed)

        # Add unit row
        unit_row = QtWidgets.QHBoxLayout()
        self.unit_counts_radio = QtWidgets.QRadioButton("Counts")
        self.unit_cps_radio = QtWidgets.QRadioButton("CPS")
        unit_row.addWidget(QtWidgets.QLabel("Signal unit:"))
        unit_row.addWidget(self.unit_counts_radio)
        unit_row.addWidget(self.unit_cps_radio)
        layout.addLayout(unit_row)
        self.unit_counts_radio.setChecked(True)
        self.unit_counts_radio.toggled.connect(self._on_signal_type_changed)
        self.unit_cps_radio.toggled.connect(self._on_signal_type_changed)

        # Add background status label
        self.bg_file_label = QtWidgets.QLabel("No background loaded")
        layout.addWidget(self.bg_file_label)

        # Add background row
        bg_row = QtWidgets.QHBoxLayout()
        self.bg_checkbox = QtWidgets.QCheckBox("Apply BG correction")
        self.bg_open_btn = QtWidgets.QPushButton("Open BG")
        bg_row.addWidget(self.bg_checkbox)
        bg_row.addWidget(self.bg_open_btn)
        layout.addLayout(bg_row)
        self.bg_checkbox.stateChanged.connect(self._on_signal_type_changed)
        self.bg_open_btn.clicked.connect(self._on_bg_open)


        # Row 3: Remove selected | Remove all
        remove_row = QtWidgets.QHBoxLayout()
        self.remove_spec_btn = QtWidgets.QPushButton("Remove Selected Spectrum")
        self.remove_all_btn = QtWidgets.QPushButton("Remove all")
        remove_row.addWidget(self.remove_spec_btn)
        remove_row.addWidget(self.remove_all_btn)
        layout.addLayout(remove_row)
        self.remove_spec_btn.clicked.connect(self.remove_selected_spectrum)
        self.remove_all_btn.clicked.connect(self.remove_all_spectra)

        # Row 3a: Export Selected | Export All
        export_row = QtWidgets.QHBoxLayout()
        self.export_selected_btn = QtWidgets.QPushButton("Export Selected")
        self.export_all_btn = QtWidgets.QPushButton("Export All")
        export_row.addWidget(self.export_selected_btn)
        export_row.addWidget(self.export_all_btn)
        layout.addLayout(export_row)
        self.export_selected_btn.clicked.connect(self.export_selected_spectrum)
        self.export_all_btn.clicked.connect(self.export_all_spectra)

        # Row 3b: Ask for folder (checkbox) and Format (entry)
        export_opts_row = QtWidgets.QHBoxLayout()
        self.ask_folder_checkbox = QtWidgets.QCheckBox("Ask for folder")
        self.format_entry = QtWidgets.QLineEdit("emsa, csv")
        export_opts_row.addWidget(self.ask_folder_checkbox)
        export_opts_row.addWidget(QtWidgets.QLabel("Format:"))
        export_opts_row.addWidget(self.format_entry)
        layout.addLayout(export_opts_row)

        # Row 4: Intensities (sel) | Intensities (all)
        int_row = QtWidgets.QHBoxLayout()
        self.intensity_btn = QtWidgets.QPushButton("Intensities (sel)")
        self.intensity_all_btn = QtWidgets.QPushButton("Intensities (all)")
        int_row.addWidget(self.intensity_btn)
        int_row.addWidget(self.intensity_all_btn)
        layout.addLayout(int_row)
        self.intensity_btn.clicked.connect(self.compute_intensities_active)
        self.intensity_all_btn.clicked.connect(self.compute_intensities_all)

        # Row 5: Fit (sel) | Fit (all)
        fit_row = QtWidgets.QHBoxLayout()
        self.fit_btn = QtWidgets.QPushButton("Fit (sel)")
        self.fit_all_btn = QtWidgets.QPushButton("Fit (all)")
        fit_row.addWidget(self.fit_btn)
        fit_row.addWidget(self.fit_all_btn)
        layout.addLayout(fit_row)
        self.fit_btn.clicked.connect(self.fit_spectrum_active)
        self.fit_all_btn.clicked.connect(self.fit_spectrum_all)

        # Row 6: Delete Fit (sel) | Delete Fit (all)
        del_row = QtWidgets.QHBoxLayout()
        self.remove_fit_btn = QtWidgets.QPushButton("Delete Fit (sel)")
        self.remove_all_fit_btn = QtWidgets.QPushButton("Delete Fit (all)")
        del_row.addWidget(self.remove_fit_btn)
        del_row.addWidget(self.remove_all_fit_btn)
        layout.addLayout(del_row)
        self.remove_fit_btn.clicked.connect(self.remove_fit_active)
        self.remove_all_fit_btn.clicked.connect(self.remove_fit_all)

        # Row 7: Horizontal separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(sep)

        # Row 8: Reset Zoom | Log Y
        zoom_row = QtWidgets.QHBoxLayout()
        self.reset_zoom_btn = QtWidgets.QPushButton("Reset Zoom")
        self.log_checkbox = QtWidgets.QCheckBox("Log Y")
        zoom_row.addWidget(self.reset_zoom_btn)
        zoom_row.addWidget(self.log_checkbox)
        layout.addLayout(zoom_row)
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        self.log_checkbox.stateChanged.connect(self.toggle_log_y)

        # Row 9: Show fit residual (centered)
        self.residual_checkbox = QtWidgets.QCheckBox("Show fit residual")
        layout.addWidget(self.residual_checkbox)
        self.residual_checkbox.setChecked(True)
        self.residual_checkbox.stateChanged.connect(self.toggle_residual)

        # Row 10: Intensities (sum) | Intensities (fit)
        table_row = QtWidgets.QHBoxLayout()
        self.show_summed_table_checkbox = QtWidgets.QCheckBox("Intensities (sum)")
        self.show_fitted_table_checkbox = QtWidgets.QCheckBox("Intensities (fit)")
        table_row.addWidget(self.show_summed_table_checkbox)
        table_row.addWidget(self.show_fitted_table_checkbox)
        layout.addLayout(table_row)
        self.show_summed_table_checkbox.stateChanged.connect(self.toggle_summed_table)
        self.show_fitted_table_checkbox.stateChanged.connect(self.toggle_fitted_table)

        # Set navigator widget geometry
        nav_width = 320
        nav_height = 600
        self.setFixedSize(nav_width, nav_height)

        # Create dummy figure for window arrangement
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geom = screen.availableGeometry()
        fig_size = nav_height  # Square plot window

        # Center both windows horizontally
        total_width = nav_width + int(fig_size*1.2) + 40
        x0 = screen_geom.center().x() - total_width // 2
        y0 = screen_geom.center().y() - nav_height // 2

        self.move(x0, y0)

        # Create dummy figure and position it
        self.fig = plt.figure(figsize=(fig_size*1.2 / 100, fig_size / 100), dpi=100)
        fig_manager = self.fig.canvas.manager
        fig_win = fig_manager.window
        fig_win.setWindowIcon(QIcon(ICON_PATH))
        fig_win.show()  # Show the window so Qt computes the frame geometry
        QtWidgets.QApplication.processEvents()  # Ensure geometry is updated
        frame_height = fig_win.frameGeometry().height() - fig_win.geometry().height()
        fig_win.move(x0 + nav_width + 20, y0)
        fig_win.resize(int(fig_size*1.2), fig_size)
        plt.close(self.fig)  # Don't show yet, just store geometry

        self.ax = None

        # Set current row after all widgets are created
        self.list.setCurrentRow(0)
        
        self.update_plot()
        
    def on_spectrum_changed(self, idx):
        if idx < 0 or idx >= self.list.count():
            return
        name = self.list.item(idx).text()
        if self.session.active_name == name:
            return  # No change, skip recomputation
        self.session.set_active(name)
        self.el_edit.setText(",".join(self.session.active_record.elements))
        # Sync radio buttons
        rec = self.session.active_record
        if rec is not None:
            quantity = rec.signal.metadata.get_item('Signal.quantity', default='X-rays (Counts)')
            self.unit_counts_radio.setChecked("Counts" in quantity)
            self.unit_cps_radio.setChecked("CPS" in quantity)
            self.bg_checkbox.setChecked("BG" in quantity)
            self.bg_checkbox.setEnabled(rec._background is not None)
        self.update_plot()

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
        rec = self.session.active_record
        if rec is None:
            return

        fig, ax = rec.plot(
            use_model=None,  # default: use model if available
            ax=self.ax,
            fig=self.fig,
            show_residual=self.residual_checkbox.isChecked()
        )
        
        self.fig = fig
        self.ax = ax 
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
        rec.fit_model()
        # Always show global table, auto-check if needed
        if not self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_table_checkbox.setChecked(True)
        else:
            self.show_fitted_intensity_table()
        self.update_plot(force_replot=True)

    def fit_spectrum_all(self):
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
            rec.model = None
            rec.fitted_intensities = None
            self.update_plot(force_replot=True)
            # Update the fitted table view if open
            if self.show_fitted_table_checkbox.isChecked():
                self.show_fitted_intensity_table()

    def remove_fit_all(self):
        for rec in self.session.records.values():
            rec.model = None
            rec.fitted_intensities = None
        self.update_plot(force_replot=True)
        for title in list(self.table_views.keys()):
            if "Fitted Line Intensities" in title:
                self.table_views[title].close()
                del self.table_views[title]

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
        if ax is not None:
            scale = "log" if self.log_checkbox.isChecked() else "linear"
            ax.set_yscale(scale)
            if scale == 'log':
                ax.set_ylim(bottom=1)
            if fig is not None:
                fig.canvas.draw_idle()

    def toggle_residual(self):
        self.update_plot(force_replot=True)

    def reset_zoom(self):
        ax = self.ax
        fig = self.fig
        rec = self.session.active_record
        if ax is not None and rec is not None:
            xaxis = rec.signal.axes_manager.signal_axes[0]
            ax.set_xlim(xaxis.low_value, xaxis.high_value)
            if ax.get_yscale() == 'log':
                ax.autoscale(enable=True, axis='y', tight=True)
                ax.set_ylim(bottom=1)
            else:
                ax.autoscale(enable=True, axis='y')
            if fig is not None:
                fig.canvas.draw_idle()

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

    def _on_signal_type_changed(self):
        if self.unit_counts_radio.isChecked():
            unit = "counts"
        elif self.unit_cps_radio.isChecked():
            unit = "cps"
        else:
            return
        # Determine BG correction state (only if BG is loaded)
        bg_loaded = any(rec._background is not None for rec in self.session.records.values())
        bg_active = self.bg_checkbox.isChecked() if bg_loaded else False

        # Actually set the signal type and BG correction
        try:
            self.session.set_unit_and_bg(unit, bg_active)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Signal Type Error", str(e))

        # Update plot and tables
        self.update_plot()
        if self.show_summed_table_checkbox.isChecked():
            self.show_summed_intensity_table()
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()

        # Disable BG correction checkbox if no BG loaded
        self.bg_checkbox.setEnabled(bg_loaded)
        if not bg_loaded:
            self.bg_checkbox.setChecked(False)

    def _on_bg_correction_changed(self):
        active = self.bg_checkbox.isChecked()
        self.session.set_bg_correction(active)
        self.update_plot()
        # Update tables if open
        if self.show_summed_table_checkbox.isChecked():
            self.show_summed_intensity_table()
        if self.show_fitted_table_checkbox.isChecked():
            self.show_fitted_intensity_table()

    def _on_bg_open(self):
        # Start in the folder of the active spectrum
        start_dir = ""
        rec = self.session.active_record
        if rec is not None and hasattr(rec, "path"):
            start_dir = os.path.dirname(rec.path)
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Background Spectrum", start_dir, "EDS Files (*.eds)"
        )
        if fname:
            try:
                self.session.set_background(fname)
                self.bg_file_label.setText(f"Background file: {os.path.basename(fname)}")
                QtWidgets.QMessageBox.information(self, "Background Loaded", f"Background spectrum loaded:\n{fname}")
                self.bg_checkbox.setEnabled(True)
                self.bg_checkbox.setChecked(True)
                self._on_signal_type_changed()  # Ensure everything is updated
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Background Error", str(e))

def main():
    from glob import glob
    p = argparse.ArgumentParser(description="EDS Spectrum Viewer")
    p.add_argument("spectra", nargs="*", help="List of spectra files, or directories to search for .eds files")
    p.add_argument("--elements", type=str, help="Comma‑separated element symbols (e.g. Fe,O,Cu)")
    args = p.parse_args()
    paths = []
    for p in args.spectra:
        if os.path.isfile(p):
            paths.append(p)
        else:
            paths.extend(glob(os.path.join(p,'**','*.eds'), recursive=True))
    
    # if not paths:
    #     print("No spectra files provided. Please provide at least one .eds file or directory containing .eds files.")
    #     sys.exit(1)
    
    session = EDSSession(paths)
    if args.elements:
        session.set_elements([e.strip() for e in args.elements.split(',') if e.strip()])
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    nav = NavigatorWidget(session)
    nav.show()
    app.exec_()

if __name__ == "__main__":
    main()