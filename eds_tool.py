import sys
from qtpy import QtWidgets, QtCore
import hyperspy.api as hs
import matplotlib, matplotlib.figure, matplotlib.axes
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import exspy
import os
import argparse
import svgutils.transform as sg
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Spacer, Paragraph
from reportlab.platypus import Table as RLTable
from reportlab.lib.styles import getSampleStyleSheet

class NavigatorWidget(QtWidgets.QWidget):

    def __init__(self, signal: exspy.signals.EDSTEMSpectrum, filenames: list[str]):
        super().__init__()
        self.signal = signal
        self.filenames = filenames
        self.model: None | exspy.models.EDSTEMModel = None
        self.setWindowTitle("EDS signals")  # Changed title
        layout = QtWidgets.QVBoxLayout(self)

        # Elements entry
        el_layout = QtWidgets.QHBoxLayout()
        self.el_edit = QtWidgets.QLineEdit(",".join(self.signal.metadata.get_item('Sample.elements', default=[]))) # type: ignore
        el_apply = QtWidgets.QPushButton("Apply elements")
        el_layout.addWidget(QtWidgets.QLabel("Elements:"))
        el_layout.addWidget(self.el_edit)
        el_layout.addWidget(el_apply)
        layout.addLayout(el_layout)
        el_apply.clicked.connect(self.apply_elements)

        # List of spectra (filenames)
        self.list = QtWidgets.QListWidget()
        for fname in self.filenames:
            self.list.addItem(os.path.basename(fname))
        layout.addWidget(self.list)
        self.list.currentRowChanged.connect(self.update_plot)
        self.list.setCurrentRow(0)
        
        # Compute Intensities button
        self.intensity_btn = QtWidgets.QPushButton("Compute Intensities")
        layout.addWidget(self.intensity_btn)
        self.intensity_btn.clicked.connect(self.compute_intensities)

        # Fit Spectrum button
        self.fit_btn = QtWidgets.QPushButton("Fit Spectrum")
        layout.addWidget(self.fit_btn)
        self.fit_btn.clicked.connect(self.fit_spectrum)
        self.remove_fit_btn = QtWidgets.QPushButton("Delete Fit Model")
        layout.addWidget(self.remove_fit_btn)
        self.remove_fit_btn.clicked.connect(self.remove_fit)        

        # Log Y axis checkbox
        self.log_checkbox = QtWidgets.QCheckBox("Log Y axis")
        layout.addWidget(self.log_checkbox)
        self.log_checkbox.stateChanged.connect(self.toggle_log_y)

        # Show Residual checkbox
        self.residual_checkbox = QtWidgets.QCheckBox("Show Residual")
        layout.addWidget(self.residual_checkbox)
        self.residual_checkbox.setChecked(True)
        self.residual_checkbox.stateChanged.connect(self.toggle_residual)

        # Reset Zoom button
        self.reset_zoom_btn = QtWidgets.QPushButton("Reset Zoom")
        layout.addWidget(self.reset_zoom_btn)
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)

        # Create popup dialog with QTextBrowser
        self.popup = QtWidgets.QDialog(self)
        self.popup.setWindowTitle("X-ray lines")
        self.popup.setModal(False)
        popup_layout = QtWidgets.QVBoxLayout(self.popup)
        self.popup_browser = QtWidgets.QTextBrowser()
        popup_layout.addWidget(self.popup_browser)
        self.popup_browser.anchorClicked.connect(self._on_popup_link_clicked)
        
        self.table_views: dict[str, QtWidgets.QDialog] = {}

        self.update_plot(0)

        # Report for selected button
        self.report_btn = QtWidgets.QPushButton("Report for selected")
        layout.addWidget(self.report_btn)
        self.report_btn.clicked.connect(self.make_report)

        # Report for all button
        self.report_all_btn = QtWidgets.QPushButton("Report for all")
        layout.addWidget(self.report_all_btn)
        self.report_all_btn.clicked.connect(self.make_report_all)

    @property
    def fig(self) -> matplotlib.figure.Figure | None:
        if self.signal._plot is None:
            return None
        fh = self.signal._plot.signal_plot
        if fh is None:
            return None
        return fh.figure # pyright: ignore[reportAttributeAccessIssue]

    @property
    def ax(self) -> matplotlib.axes.Axes | None:
        if self.signal._plot is None:
            return None
        fh = self.signal._plot.signal_plot
        if fh is None:
            return None
        return fh.ax # pyright: ignore[reportAttributeAccessIssue]
    
    def apply_elements(self):
        els = [e.strip() for e in self.el_edit.text().split(",") if e.strip()]
        self.signal.set_elements(els)
        if self.model is None:
            self.update_plot(self.list.currentRow(), force_replot=True)
        else:
            self.fit_spectrum()

    def update_plot(self, idx, force_replot=False):
                        
        if force_replot or (self.fig is None):            
                            
            if self.ax is not None:
                assert self.fig is not None
                xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim()
                yscale = self.ax.get_yscale()
                win = self.fig.canvas.manager.window
                win_geom = win.geometry()
            else:
                xlim, ylim, yscale, win_geom = None, None, None, None
                
            if self.model is None:
                self.signal.plot(True, navigator=None)
            else:
                self.model.plot(
                    xray_lines=True,
                    plot_residual=self.residual_checkbox.isChecked(),
                    navigator=None
                )
                
            plt.show(block=False)

            if xlim is not None:
                assert (self.fig is not None) and (self.ax is not None)
                self.ax.set_yscale(yscale)
                self.ax.set_xlim(xlim)
                self.ax.set_ylim(ylim)
                win = self.fig.canvas.manager.window
                if win_geom:
                    win.setGeometry(win_geom)
                                        
        if self.signal.axes_manager.navigation_dimension:
            self.signal.axes_manager.indices = (idx,)
            
        # Connect right-click handler after plotting
        if self.fig is not None:
            self.fig.canvas.mpl_connect("button_press_event", self._on_right_click)

    def _on_right_click(self, event):
        # Only respond to right-clicks in the axes
        if event.button == 3 and event.inaxes == self.ax and event.xdata is not None:
            energy = event.xdata
            lines = exspy.utils.eds.get_xray_lines_near_energy(energy, only_lines=['a', 'b'])
            msg = "\n".join(lines)
            self._show_lines_popup(energy, msg)

    def _show_lines_popup(self, energy, msg):
        # Render each line as a hyperlink
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

        self.popup.close()  # Close the popup after selection

    def compute_intensities(self):
        # Estimate background windows and compute intensities
        if not self.signal.metadata.get_item('Sample.elements', default=[]):
            QtWidgets.QMessageBox.warning(self, "No Elements Defined", "Please define elements first before computing intensities.")
            return
        
        bw = self.signal.estimate_background_windows()
        intensities = self.signal.get_lines_intensity(background_windows=bw)

        # Each item in intensities is a signal for one line
        line_names = [sig.metadata.get_item('Sample.xray_lines')[0] for sig in intensities]
        num_spectra = intensities[0].data.shape[0] if intensities else 0

        # Prepare table data: one row per spectrum
        table_data = []
        for i in range(num_spectra):
            row = [os.path.basename(self.filenames[i])]
            for sig in intensities:
                val = sig.data[i]
                row.append(val)
            table_data.append(row)

        # Show results in a popup table
        self._show_intensity_table(line_names, table_data, title='Summed Line Intensities')

    def fit_spectrum(self):
        # Create and fit model
        self.model = self.signal.create_model()
        self.model.fit()

        # Get fitted line intensities
        intensities = self.model.get_lines_intensity()

        # Each item in intensities is a signal for one line
        line_names = [sig.metadata.get_item('Sample.xray_lines')[0] for sig in intensities]
        num_spectra = intensities[0].data.shape[0] if intensities else 0

        # Prepare table data: one row per spectrum
        table_data = []
        for i in range(num_spectra):
            row = [os.path.basename(self.filenames[i])]
            for sig in intensities:
                val = sig.data[i]
                row.append(val)
            table_data.append(row)

        # Show results in a popup table
        self._show_intensity_table(line_names, table_data, title='Fitted Line Intensities')

        # Open model plot
        self.update_plot(self.list.currentRow(), force_replot=True)
        # self.model.plot(xray_lines=True, plot_residual=True, navigator=None)
        # plt.show(block=False)
        
    def remove_fit(self):
        self.model = None
        self.update_plot(self.list.currentRow(), force_replot=True)
        if 'Fitted Line Intensities' in self.table_views:
            self.table_views['Fitted Line Intensities'].close()

    def _show_intensity_table(self, line_names, table_data, title="Line Intensities"):
        # Store geometry if dialog exists
        geom = None
        if title in self.table_views:
            old_dialog = self.table_views[title]
            geom = old_dialog.geometry()
            old_dialog.close()

        dialog = self.table_views[title] = QtWidgets.QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(False)
        layout = QtWidgets.QVBoxLayout(dialog)
        table = QtWidgets.QTableWidget(dialog)
        table.setRowCount(len(table_data))
        table.setColumnCount(len(line_names) + 1)
        
        header = ["Spectrum"] + line_names
        table.setHorizontalHeaderLabels(header)

        # Use fixed-width font for all items
        font = table.font()
        font.setFamily("Courier New")
        font.setPointSize(10)

        for i, row in enumerate(table_data):
            for j, val in enumerate(row):
                # Format as fixed-point with one decimal if possible
                if j == 0:
                    # Spectrum name: left-aligned, normal font
                    item = QtWidgets.QTableWidgetItem(str(val))
                    item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
                else:
                    try:
                        sval = f"{float(val):.1f}"
                    except Exception:
                        sval = str(val)
                    item = QtWidgets.QTableWidgetItem(sval)
                    item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    item.setFont(font)
                table.setItem(i, j, item)

        layout.addWidget(table)
        dialog.resize(800, 300)
        if geom is not None:
            dialog.setGeometry(geom)
        dialog.show()

    def toggle_log_y(self):
        if self.ax is not None:
            scale = "log" if self.log_checkbox.isChecked() else "linear"
            self.ax.set_yscale(scale)
            if scale == 'log':
                self.ax.set_ylim(bottom=1)  # Avoid log(0)
            self.fig.canvas.draw_idle()

    def toggle_residual(self):
        self.update_plot(self.list.currentRow(), force_replot=True)

    def reset_zoom(self):
        if self.ax is not None:
            # X axis: full energy range
            xaxis = self.signal.axes_manager.signal_axes[0]
            self.ax.set_xlim(xaxis.low_value, xaxis.high_value)
            # Y axis: auto
            if self.ax.get_yscale() == 'log':
                self.ax.autoscale(enable=True, axis='y', tight=True)
                self.ax.set_ylim(bottom=1)  # Avoid log(0)
            else:
                self.ax.autoscale(enable=True, axis='y')
            self.fig.canvas.draw_idle()

    def closeEvent(self, event):
        # Close the plot window if open
        if self.fig is not None:
            plt.close(self.fig)
        event.accept()

    def make_report(self):
        report = EDSReport(self.signal, self.model, self.filenames)
        report.export_report(spectrum_idx=self.list.currentRow())

    def make_report_all(self):
        report = EDSReport(self.signal, self.model, self.filenames)
        indices = list(range(len(self.filenames)))
        report.export_report(spectrum_idx=indices)

class EDSReport:
    def __init__(self, signal, model=None, paths=None):
        self.signal = signal
        self.model = model
        self.paths = paths

    def export_report(self, spectrum_idx: int | list[int] = 0, pdf_path=None):
        
        if isinstance(spectrum_idx, list):
            for idx in spectrum_idx:
                self.export_report(idx, pdf_path=None)
            return        
        
        # Get line intensities from the full model or signal
        if self.model is not None:
            intensities = self.model.get_lines_intensity()
        else:
            intensities = self.signal.get_lines_intensity()

        if pdf_path is None:
            pdf_path = os.path.splitext(self.paths[spectrum_idx])[0] + '.pdf'
            
        spectrum_name = os.path.splitext(os.path.basename(self.paths[spectrum_idx]))[0]
        
        # Prepare transposed table data: one row per line (no energy)
        table_data = [["Line", "Intensity"]]
        for sig in intensities:
            line = sig.metadata.get_item('Sample.xray_lines')[0]
            val = sig.data[spectrum_idx]
            table_data.append([line, f"{val:.1f}"])

        # Split table into two columns if too long
        n = len(table_data)
        split = (n + 1) // 2
        left_table = table_data[:split]
        right_table = table_data[0:1] + table_data[split:]  # repeat header for right table

        # Create PDF
        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        elements.append(Paragraph(f"EDS Spectrum and Intensities<br/><b>{spectrum_name}</b>", styles['Title']))
        elements.append(Spacer(1, 0.2 * inch))

        # Save the current figure as PNG and preserve aspect ratio
        plot_png = pdf_path.replace('.pdf', '_spectrum.png')
        plot_pdf = pdf_path.replace('.pdf', '_spectrum.pdf')
        
        fig = self.signal._plot.signal_plot.figure if self.signal._plot and self.signal._plot.signal_plot else None
        
        if fig is not None:
            fig.savefig(plot_png, dpi=600)
            fig.savefig(plot_pdf)
            fig_width_inch, fig_height_inch = fig.get_size_inches()
            pdf_img_width = 6.5 * inch
            pdf_img_height = pdf_img_width * (fig_height_inch / fig_width_inch)
            elements.append(Image(plot_png, width=pdf_img_width, height=pdf_img_height))
            elements.append(Spacer(1, 0.2 * inch))

        # Add left and right tables side by side
        tbl_left = Table(left_table, hAlign='LEFT')
        tbl_right = Table(right_table, hAlign='LEFT')
        style = TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Courier'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ])
        tbl_left.setStyle(style)
        tbl_right.setStyle(style)

        elements.append(Table([[tbl_left, tbl_right]], colWidths=[3*inch, 3*inch]))
        elements.append(Spacer(1, 0.2 * inch))

        doc.build(elements)
        print(f"PDF report saved to {pdf_path}")
        if sys.platform.startswith("win"):
            os.startfile(pdf_path)

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
    
    specs = hs.load(paths, stack=True) # pyright: ignore[reportCallIssue]
    specs.metadata['General']['title'] = os.path.basename(os.path.commonpath(paths))
    
    if args.elements:
        specs.add_elements([e.strip() for e in args.elements.split(',') if e.strip()])

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    nav = NavigatorWidget(specs, paths)
    nav.show()
    app.exec_()

if __name__ == "__main__":
    main()