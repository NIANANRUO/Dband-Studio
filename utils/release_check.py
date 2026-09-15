"""Explicit, opt-in release acceptance check runnable inside the installed EXE."""
from pathlib import Path
import json
import time
import traceback


def run_release_check(output_directory):
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'passed': False}
    window = dialog = None
    try:
        import numpy as np
        from PySide6.QtWidgets import QApplication, QFileDialog
        from core.loader import DataLoader
        from models.app_state import AppState
        from ui.hybridization_win import HybridizationWindow
        from ui.hybridization_batch_dialog import HybridizationBatchDialog
        from ui.i18n import get_language_manager, set_combo_value
        from core.services.hybridization_batch import MODES, read_result
        from utils.helpers import get_app_version
        from main import runtime_preflight
        runtime_preflight()
        report['version'] = get_app_version()
        report['checks'].append('runtime_dependencies')
        app = QApplication.instance() or QApplication([])
        manager = get_language_manager()
        original_language = manager.language
        manager.set_language('en', persist=False)
        def wait_for(predicate):
            deadline = time.monotonic() + 90
            while not predicate():
                app.processEvents()
                if time.monotonic() > deadline:
                    raise RuntimeError('Release check timed out')
                time.sleep(.01)
            app.processEvents()
        state = AppState()
        for name in ('System-A', 'System-B'):
            folder = root / name
            folder.mkdir(exist_ok=True)
            path = folder / 'DOSCAR'
            with path.open('w', encoding='utf-8') as stream:
                stream.write('3 3 1 0\n0 0 0\n0\nCAR\nrelease-check\n1 -1 3 0 1\n-1 1 0\n0 1 1\n1 1 2\n')
                for atom in range(1,4):
                    stream.write('1 -1 3 0 1\n')
                    for energy in (-1,0,1):
                        stream.write(str(energy)+' '+' '.join(str(atom*(i+1)) for i in range(9))+'\n')
            from dataclasses import asdict
            state.file_entries.append({'label': name, 'path': str(path), 'capabilities': asdict(DataLoader.inspect(str(path)))})
        window = HybridizationWindow(state)
        window.frag1.entry_atoms.setText('1')
        window.frag2.entry_atoms.setText('2,3')
        for orbital in ('d','dxy'):
            window.frag1._orbital_checks[orbital].setChecked(True)
        for orbital in ('p','py'):
            window.frag2._orbital_checks[orbital].setChecked(True)
        window._generate_plot()
        wait_for(lambda: window._worker is not None and not window._worker.isRunning())
        assert window._has_plot_data
        report['checks'].append('single_analysis')
        window._fragment_style(0)['colors'] = {'dxy': '#123456'}
        window._on_setting_changed()
        assert window._fragment_color_map(0)['dxy'] == '#123456'
        state.save_workspace(str(root/'workspace.json'))
        restored = AppState()
        restored.load_workspace(str(root/'workspace.json'))
        assert restored.hybridization_style == state.hybridization_style
        report['checks'].append('colors_and_workspace')
        dialog = HybridizationBatchDialog(window)
        dialog.result_selected.connect(window._show_batch_result)
        set_combo_value(dialog.mode, MODES[1])
        dialog._preview()
        wait_for(lambda: dialog.preview.isEnabled())
        assert len(dialog.tasks) == 4
        dialog._run()
        wait_for(lambda: dialog.preview.isEnabled())
        assert len(dialog.results) == 4 and not dialog.errors
        individual = [read_result(dialog.results[i]) for i in (0,1)]
        dialog._select(0)
        assert '[Atoms: 2]' in window._ax_bot.get_title(loc='left')
        report['checks'].append('multi_system_individual_pairs')
        # Supply an explicit output directory without opening a file picker.
        original_picker = QFileDialog.getExistingDirectory
        try:
            QFileDialog.getExistingDirectory = lambda *a, **kw: str(root)
            dialog._export()
            wait_for(lambda: dialog._export_queue is None)
        finally:
            QFileDialog.getExistingDirectory = original_picker
        assert not dialog._export_errors
        export_root = dialog._export_root
        assert len(list(export_root.glob('*.png'))) == 4
        assert len(list(export_root.glob('*.svg'))) == 4
        assert (export_root/'summary.csv').is_file()
        assert '#123456' in next(export_root.glob('*.svg')).read_text(encoding='utf-8')
        report['checks'].append('png_svg_csv_batch_export')
        set_combo_value(dialog.mode, MODES[2])
        dialog._preview()
        wait_for(lambda: dialog.preview.isEnabled())
        assert len(dialog.tasks) == 2
        dialog._run()
        wait_for(lambda: dialog.preview.isEnabled())
        assert len(dialog.results) == 2 and not dialog.errors
        merged = read_result(dialog.results[0])
        for orbital in ('p','py'):
            np.testing.assert_allclose(merged[1][1][orbital], individual[0][1][1][orbital]+individual[1][1][1][orbital])
        report['checks'].append('merged_pair_equivalence')
        manager.set_language('zh_CN', persist=False)
        manager.apply(window)
        assert window.btn_batch.text() == '批量分析…'
        manager.set_language(original_language, persist=False)
        report['checks'].append('chinese_interface')
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if dialog:
            if dialog.worker and dialog.worker.isRunning():
                dialog.worker.requestInterruption()
                dialog.worker.wait()
            dialog.close()
        if window:
            if window._worker and window._worker.isRunning():
                window._worker.wait()
            window.close()
        (root/'release-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1
