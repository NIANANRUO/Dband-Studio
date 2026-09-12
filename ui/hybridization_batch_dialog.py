"""Batch plan preview, asynchronous execution, and hybridization result browser."""
from __future__ import annotations

import copy
import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QAbstractItemView,
)
from core.services.hybridization_batch import (
    MODES, BatchPreviewWorker, BatchAnalysisWorker, read_result,
)
from core.services.exporter import DataExporter
from ui.i18n import tr, combo_value, set_combo_value, get_language_manager


class HybridizationBatchDialog(QDialog):
    result_selected = Signal(object, object)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle(tr('Batch hybridization analysis'))
        self.resize(1120, 760)
        self.setFont(owner.font())
        self._directory = TemporaryDirectory(prefix='dband-hybridization-')
        self.worker = None
        self.tasks = []
        self.results = {}
        self.errors = {}
        self._row_tasks = {}
        self._export_queue = None
        self.entries = copy.deepcopy(owner.state.file_entries)
        layout = QVBoxLayout(self)
        tip = QLabel(tr('Select systems and edit atom mappings. Orbitals and spin are copied from Fragment 1 / Fragment 2 when previewing.'))
        tip.setWordWrap(True)
        layout.addWidget(tip)
        toolbar = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(MODES)
        toolbar.addWidget(QLabel(tr('Pairing:')))
        toolbar.addWidget(self.mode, 1)
        self.copy_button = QPushButton(tr('Copy current atom selections'))
        self.copy_button.clicked.connect(self._copy_atoms)
        toolbar.addWidget(self.copy_button)
        layout.addLayout(toolbar)
        self.sources = QTableWidget(len(self.entries), 5)
        self.sources.setHorizontalHeaderLabels([tr(t) for t in ('System', 'Fragment 1 atoms', 'Fragment 2 atoms', 'Expected element 1 (optional)', 'Expected element 2 (optional)')])
        self.sources.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        config = owner.state.hybridization_batch
        saved = {r['entry']['path']: r for r in config.get('rows', [])}
        for row, entry in enumerate(self.entries):
            item = QTableWidgetItem(entry.get('label', Path(entry['path']).name))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked if not saved or entry['path'] in saved else Qt.Unchecked)
            item.setToolTip(entry['path'])
            self.sources.setItem(row, 0, item)
            prior = saved.get(entry['path'], {})
            values = [prior.get('left', owner.frag1.get_atoms_text()), prior.get('right', owner.frag2.get_atoms_text()), prior.get('element1', ''), prior.get('element2', '')]
            for col, value in enumerate(values, 1):
                self.sources.setItem(row, col, QTableWidgetItem(value))
        if config.get('mode') in MODES:
            set_combo_value(self.mode, config['mode'])
        self.sources.itemChanged.connect(self._invalidate)
        self.mode.currentIndexChanged.connect(self._invalidate)
        layout.addWidget(self.sources, 2)
        buttons = QHBoxLayout()
        self.preview = QPushButton(tr('Preview tasks'))
        self.run_button = QPushButton(tr('Run pending tasks'))
        self.retry = QPushButton(tr('Retry failed tasks'))
        self.cancel = QPushButton(tr('Cancel after current operation'))
        self.export = QPushButton(tr('Export completed results'))
        self.preview.clicked.connect(self._preview)
        self.run_button.clicked.connect(self._run)
        self.retry.clicked.connect(self._retry)
        self.cancel.clicked.connect(self._cancel)
        self.export.clicked.connect(self._export)
        for button in (self.preview, self.run_button, self.retry, self.cancel):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        export_row = QHBoxLayout()
        export_row.addWidget(self.export)
        export_tip = QLabel(tr('Click a completed row to view its plot. Export saves results; workspaces save atom mappings.'))
        export_tip.setWordWrap(True)
        export_row.addWidget(export_tip, 1)
        layout.addLayout(export_row)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([tr(t) for t in ('System', 'Fragment 1 atoms', 'Fragment 2 atoms', 'Orbitals', 'Pairing', 'Status')])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(105)
        self.table.cellClicked.connect(self._select)
        layout.addWidget(self.table, 3)
        self.status = QLabel(tr('Preview tasks before running.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._busy(False)
        get_language_manager().apply(self)

    def _busy(self, value):
        for widget in (self.sources, self.mode, self.copy_button, self.preview):
            widget.setEnabled(not value)
        self.run_button.setEnabled(not value and bool(self.tasks))
        self.retry.setEnabled(not value and bool(self.errors))
        self.cancel.setEnabled(value)
        self.export.setEnabled(not value and bool(self.results))

    def _invalidate(self, *_):
        self.tasks = []
        self.results.clear()
        self.errors.clear()
        self.table.setRowCount(0)
        self._busy(False)
        self.status.setText(tr('Inputs changed. Preview tasks again.'))

    def _copy_atoms(self):
        for row in range(len(self.entries)):
            for col, panel in ((1, self.owner.frag1), (2, self.owner.frag2)):
                self.sources.item(row, col).setText(panel.get_atoms_text())

    def _preview(self):
        self._invalidate()
        rows = []
        for i, entry in enumerate(self.entries):
            if self.sources.item(i, 0).checkState() == Qt.Checked:
                values = [self.sources.item(i, c).text() for c in range(1, 5)]
                rows.append(dict(entry=entry, left=values[0], right=values[1], element1=values[2], element2=values[3]))
        orbs1 = self.owner.frag1.get_selected_orbitals()
        orbs2 = self.owner.frag2.get_selected_orbitals()
        if not rows or not orbs1 or not orbs2:
            self.status.setText(tr('Select systems and orbitals for both fragments first.'))
            return
        self.owner.state.hybridization_batch = {'rows': rows, 'mode': combo_value(self.mode)}
        self._row_tasks = {}
        self._preview_errors = []
        self._preview_rows = rows
        self._busy(True)
        self.status.setText(tr('Checking source capabilities and atom mappings…'))
        self.worker = BatchPreviewWorker(rows, orbs1, orbs2, self.owner._get_spin_mode(),
            (self.owner.frag1.get_fragment_name(), self.owner.frag2.get_fragment_name()), combo_value(self.mode), self)
        self.worker.row_ready.connect(self._preview_row)
        self.worker.finished.connect(self._preview_done)
        self.worker.start()

    def _preview_row(self, row, tasks, error):
        self._row_tasks[row] = tasks
        if error:
            name = self._preview_rows[row]['entry'].get('label', str(row+1))
            self._preview_errors.append(f'{name}: {error}')

    def _preview_done(self):
        self.tasks = [t for i in sorted(self._row_tasks) for t in self._row_tasks[i]]
        self.table.setRowCount(len(self.tasks))
        for row, task in enumerate(self.tasks):
            values = [task.system, ','.join(map(str, task.left)), ','.join(map(str, task.right)),
                '+'.join(o+'-total' if o in ('s','p','d','f') else o for o in task.orbitals1)+' / '+'+'.join(o+'-total' if o in ('s','p','d','f') else o for o in task.orbitals2), tr(task.mode), tr('Pending')]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        cancelled = self.worker.isInterruptionRequested()
        self._busy(False)
        if self._preview_errors or cancelled:
            # A partial plan must never silently omit selected systems.
            self.run_button.setEnabled(False)
            self.tasks = []
        messages = '\n'.join(self._preview_errors)
        self.status.setText(f"{tr('Tasks')}: {self.table.rowCount()}\n{messages}" if not cancelled else tr('Preview cancelled. Preview again to run.'))

    def _run(self):
        self._start([(i,t) for i,t in enumerate(self.tasks) if i not in self.results and i not in self.errors])

    def _retry(self):
        self._start([(i,self.tasks[i]) for i in sorted(self.errors)])

    def _start(self, items):
        if not items:
            return
        self._busy(True)
        for i,_ in items:
            self.errors.pop(i, None)
            self.table.item(i,5).setText(tr('Pending'))
        self.worker = BatchAnalysisWorker(items, self._directory.name, self)
        self.worker.task_ready.connect(self._task_ready)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self._run_done)
        self.worker.start()

    def _task_ready(self, index, path, error):
        if error:
            self.errors[index] = error
            self.table.item(index,5).setText(tr('Failed') + ': ' + error)
        else:
            self.results[index] = path
            self.table.item(index,5).setText(tr('Completed'))
        self.status.setText(f"{tr('Completed')}: {len(self.results)} / {len(self.tasks)}; {tr('Failed')}: {len(self.errors)}")

    def _run_done(self):
        self._busy(False)
        if self.worker.isInterruptionRequested():
            self.status.setText(tr('Cancelled. Completed results are retained; pending tasks can resume.'))

    def _cancel(self):
        if self._export_queue is not None:
            self._export_queue.clear()
        elif self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.status.setText(tr('Cancellation requested. Waiting for current file operation…'))

    def _select(self, row, _column=0):
        if row in self.results and self._export_queue is None:
            self.result_selected.emit(self.tasks[row], read_result(self.results[row]))

    def _export(self):
        if self.owner._worker and self.owner._worker.isRunning():
            self.status.setText(tr('Wait for the single analysis to finish before exporting.'))
            return
        directory = QFileDialog.getExistingDirectory(self, tr('Export completed results'))
        if not directory:
            return
        # Every export gets a fresh folder; existing files are never replaced.
        self._export_root = Path(directory) / ('hybridization_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6])
        try:
            self._export_root.mkdir()
            manifest = {'tasks': [asdict(t) for t in self.tasks], 'errors': self.errors,
                'style': copy.deepcopy(self.owner.state.hybridization_style),
                'energy_reference': 'E - Ef for each source', 'aggregation': 'sum',
                'integration_method': self.owner._integration_method,
                'integration_limits': self.owner._get_integration_limits(), 'png_dpi': 200}
            (self._export_root / 'tasks.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as exc:
            QMessageBox.warning(self, tr('Export Failed'), str(exc))
            return
        self._export_queue = list(sorted(self.results))
        self._export_errors = []
        self._summary = []
        self._restore = (self.owner._cached_data, getattr(self.owner, '_batch_display', None))
        self._busy(True)
        self.owner.left_tabs.setEnabled(False)
        self.owner.btn_plot.setEnabled(False)
        QTimer.singleShot(0, self._export_next)

    def _export_next(self):
        if not self._export_queue:
            self._export_queue = None
            try:
                with (self._export_root / 'summary.csv').open('w', newline='', encoding='utf-8-sig') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['Task', 'System', 'Atoms 1', 'Atoms 2', 'Center 1 (eV)', 'Center 2 (eV)', 'Status'])
                    writer.writerows(self._summary)
            except OSError as exc:
                self._export_errors.append(str(exc))
            data, display = self._restore
            self.owner._batch_display = display
            self.owner._cached_data = data
            self.owner._has_plot_data = bool(data)
            if data:
                self.owner._render_plot(*data)
            else:
                for ax in (self.owner._ax_top, self.owner._ax_mid, self.owner._ax_bot):
                    ax.clear()
                self.owner.fig.suptitle('')
                self.owner.canvas.draw_idle()
            self.owner.left_tabs.setEnabled(True)
            self.owner.btn_plot.setEnabled(True)
            self._busy(False)
            self.status.setText(str(self._export_root) + ('\n' + '\n'.join(self._export_errors) if self._export_errors else ''))
            return
        i = self._export_queue.pop(0)
        task = self.tasks[i]
        import re
        name = re.sub(r'[^\w.-]+', '_', task.system)[:60]
        pair = f"{'-'.join(map(str,task.left))}_vs_{'-'.join(map(str,task.right))}"[:80]
        base = self._export_root / f'{i+1:05d}_{name}_{pair}'
        try:
            data = read_result(self.results[i])
            self.owner._batch_display = (','.join(map(str, task.left)), ','.join(map(str, task.right)), task.spin)
            self.owner._render_plot(*data)
            self.owner.fig.savefig(str(base)+'.png', dpi=200)
            self.owner.fig.savefig(str(base)+'.svg')
            DataExporter.export_hybridization_csv(
                self.owner._plot_e1, self.owner._plot_rho1, self.owner._plot_orbs1, self.owner._plot_label1,
                self.owner._plot_e2, self.owner._plot_rho2, self.owner._plot_orbs2, self.owner._plot_label2, str(base)+'.csv')
            from core.calculator import calc_metrics
            from core.orbital_selection import non_overlapping_orbitals
            limit, custom, _ = self.owner._get_integration_limits()
            centers = []
            for e, up, down, orbs, _ in data:
                rho = {o: (up[o] if up else 0)+(down[o] if down else 0) for o in orbs}
                centers.append(calc_metrics(e, rho, ef=0., orb_names=non_overlapping_orbitals(orbs),
                    limit_fermi=limit, custom_range=custom, method=self.owner._integration_method)[0])
            self._summary.append([i+1, task.system, str(task.left), str(task.right), *centers, 'Completed'])
        except Exception as exc:
            self._export_errors.append(f'{i+1}: {exc}')
            self._summary.append([i+1, task.system, str(task.left), str(task.right), '', '', str(exc)])
        self.status.setText(f"{tr('Exporting')}: {len(self._summary)} / {len(self.results)}")
        QTimer.singleShot(0, self._export_next)

    def closeEvent(self, event):
        if (self.worker and self.worker.isRunning()) or self._export_queue is not None:
            self._cancel()
            event.ignore()
            return
        super().closeEvent(event)
