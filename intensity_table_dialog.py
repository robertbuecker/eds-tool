from qtpy import QtWidgets
from qtpy import QtCore
from qtpy.QtCore import Qt
import csv

import numpy as np
import pandas as pd
from math import log10, floor

class IntensityTableDialog(QtWidgets.QDialog):
    def __init__(self, parent, line_names, table_data, title="Line Intensities"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.line_names = line_names
        self.selected_lines = [True] * len(line_names)
        self.norm_idx = None
    # Sorting is disabled for now

        # Store original data as DataFrame: index = spectrum name, columns = line_names
        # table_data: list of [spectrum, val1, val2, ...]
        if not table_data:
            self.spectrum_names = []
            self._df = pd.DataFrame(columns=self.line_names)
        else:
            arr = np.array(table_data)
            self.spectrum_names = arr[:, 0]
            self._df = pd.DataFrame(
                data=arr[:, 1:].astype(float),
                index=self.spectrum_names,
                columns=self.line_names
            )
        # The DataFrame self._df is never mutated; all display is based on views of this

        # --- Main layout: horizontal ---
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # --- Line selection list ---
        self.line_list = QtWidgets.QListWidget()
        self.line_list.setFixedWidth(100)
        self.line_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for i, name in enumerate(line_names):
            item = QtWidgets.QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.line_list.addItem(item)
        self.line_list.itemChanged.connect(self._on_line_selection_changed)
        line_list_container = QtWidgets.QWidget()
        line_list_layout = QtWidgets.QVBoxLayout(line_list_container)
        line_list_layout.setContentsMargins(0, 0, 0, 0)
        line_list_layout.setSpacing(4)
        line_list_layout.addWidget(QtWidgets.QLabel("Lines:"))
        line_list_layout.addWidget(self.line_list)

        # Add "All" and "None" buttons below the list, stacked vertically
        all_btn = QtWidgets.QPushButton("All")
        none_btn = QtWidgets.QPushButton("None")
        line_list_layout.addWidget(all_btn)
        line_list_layout.addWidget(none_btn)

        def select_all():
            for i in range(self.line_list.count()):
                item = self.line_list.item(i)
                item.setCheckState(Qt.Checked)
        def select_none():
            for i in range(self.line_list.count()):
                item = self.line_list.item(i)
                item.setCheckState(Qt.Unchecked)
        all_btn.clicked.connect(select_all)
        none_btn.clicked.connect(select_none)

        main_layout.addWidget(line_list_container)

        # --- Right side: grid layout ---
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QGridLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Normalization radio buttons (pre-create all, just hide/show)
        norm_widget = QtWidgets.QWidget()
        norm_layout = QtWidgets.QHBoxLayout(norm_widget)
        norm_layout.setContentsMargins(0, 0, 0, 0)
        norm_layout.setSpacing(4)
        norm_layout.addWidget(QtWidgets.QLabel("Normalize:"))
        self.norm_group = QtWidgets.QButtonGroup(self)
        self._norm_radio_none = QtWidgets.QRadioButton("None")
        self._norm_radio_none.setChecked(True)
        self.norm_group.addButton(self._norm_radio_none, -1)
        norm_layout.addWidget(self._norm_radio_none)
        self._norm_radio_none.toggled.connect(lambda checked: self._on_normalize_changed(None) if checked else None)
        self._norm_radio_buttons = []
        for i, name in enumerate(line_names):
            btn = QtWidgets.QRadioButton(name)
            self.norm_group.addButton(btn, i)
            norm_layout.addWidget(btn)
            btn.toggled.connect(lambda checked, idx=i: self._on_normalize_changed(idx) if checked else None)
            self._norm_radio_buttons.append(btn)
        norm_layout.addStretch(1)
        right_layout.addWidget(norm_widget, 0, 0, 1, 2)

        # Table widget (expanding in both directions)
        self.table = QtWidgets.QTableWidget()
        self.table.setMinimumWidth(500)
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.table.setColumnCount(len(line_names) + 1)
        self.table.setHorizontalHeaderLabels(["Spectrum"] + line_names)
        self.table.setSortingEnabled(False)
        right_layout.addWidget(self.table, 1, 0, 1, 2)
        right_layout.setRowStretch(1, 1)  # Table gets all extra vertical space

        # Export button (bottom right)
        export_btn = QtWidgets.QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        right_layout.addWidget(export_btn, 2, 1, alignment=Qt.AlignRight)

        main_layout.addWidget(right_widget, stretch=1)  # Right side expands

        self._update_norm_radios()
        self._update_table()

    def _on_line_selection_changed(self, item):
        idx = self.line_list.row(item)
        self.selected_lines[idx] = (item.checkState() == Qt.Checked)
        if self.norm_idx is not None and not self.selected_lines[self.norm_idx]:
            self.norm_idx = None
        self._update_norm_radios()
        self._update_table()

    def _on_normalize_changed(self, idx):
        self.norm_idx = idx
        self._update_table()

    def _update_norm_radios(self):
        for i, btn in enumerate(self._norm_radio_buttons):
            btn.setVisible(self.selected_lines[i])
            if self.norm_idx == i and self.selected_lines[i]:
                btn.setChecked(True)
        if self.norm_idx is None or not (self.norm_idx < len(self.selected_lines) and self.selected_lines[self.norm_idx]):
            self._norm_radio_none.setChecked(True)

    def _update_table(self):
        col_indices = [i for i, sel in enumerate(self.selected_lines) if sel]
        visible_line_names = [self.line_names[i] for i in col_indices]
        headers = ["Spectrum"] + visible_line_names
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        df_view = self._df[visible_line_names].copy()
        digits = 2
        normalization_factor = None
        if self.norm_idx is not None:
            norm_col_name = self.line_names[self.norm_idx]
            norm_vals = self._df[norm_col_name].values
            safe_norm_vals = np.where(norm_vals == 0, np.nan, norm_vals)
            normalization_factor = np.nanmax(np.abs(safe_norm_vals))
            if normalization_factor > 1:
                digits += int(round(max(0, log10(normalization_factor))))
            df_view = df_view.div(safe_norm_vals, axis=0)
        fmt = f"{{:.{digits}f}}"
        # Always display in original spectrum order
        df_view = df_view.copy()
        df_view.insert(0, "Spectrum", df_view.index)
        # No sorting, just keep original order
        self.table.setRowCount(len(df_view))
        for i, (_, row) in enumerate(df_view.iterrows()):
            item = QtWidgets.QTableWidgetItem(str(row["Spectrum"]))
            self.table.setItem(i, 0, item)
            for j, col in enumerate(visible_line_names):
                val = row[col]
                try:
                    sval = fmt.format(val)
                except Exception:
                    sval = str(val)
                item = QtWidgets.QTableWidgetItem(sval)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, j + 1, item)

    def _export_csv(self):
        result = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if isinstance(result, tuple):
            path = result[0]
        else:
            path = result
        if not path:
            return
        col_indices = [i for i, sel in enumerate(self.selected_lines) if sel]
        headers = ["Spectrum"] + [self.line_names[i] for i in col_indices]
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for i in range(self.table.rowCount()):
                row = [self.table.item(i, j).text() for j in range(self.table.columnCount())]
                writer.writerow(row)