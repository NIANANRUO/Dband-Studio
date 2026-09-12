"""Adversarial coverage of selection semantics, batch plans and real parser reuse."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from core.parsers.common import resolve_selection
from core.exceptions import DbandError
from core.services.hybridization_batch import (
    MODES, pair_selections, prepare_row, BatchAnalysisWorker, read_result,
)


@pytest.fixture(scope='module')
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize('text', ['67, 68, 69, 70', '67，68，69，70', '67、68、69、70', '67 68 69 70', '67 - 70'])
def test_selection_separators(text):
    assert resolve_selection(text, 71) == [66,67,68,69]


@pytest.mark.parametrize('text', ['0', '-1', '67,999', '70-67', '0-5', '1-999', '1,,2', '1,bogus'])
def test_selection_rejects_partial_or_invalid_input(text):
    with pytest.raises(DbandError):
        resolve_selection(text, 71)


def test_order_and_duplicates_are_explicit():
    assert resolve_selection('4,2,4,1', 5) == [3,1,0]
    assert pair_selections([4,2], [1,3], MODES[3]) == [((4,),(1,)), ((2,),(3,))]


@pytest.mark.parametrize('left,right,mode,count', [
    ([1],[2],MODES[0],1), ([1],[2,3,4],MODES[1],3),
    ([1],[2,3,4],MODES[2],1), ([1,2],[3,4],MODES[3],2),
    ([1,2],[3,4],MODES[4],4), ([1,2],[3,4],MODES[5],1),
])
def test_six_pairing_modes(left,right,mode,count):
    assert len(pair_selections(left,right,mode)) == count


def test_pairing_never_silently_truncates_or_self_pairs():
    for left,right,mode in [([1,2],[3],MODES[3]), ([1,2],[3],MODES[1]), ([1],[1],MODES[0])]:
        with pytest.raises(ValueError):
            pair_selections(left,right,mode)


def write_doscar(path):
    with path.open('w') as f:
        f.write('3 3 1 0\n0 0 0\n0\nCAR\nbatch-test\n1 -1 2 0 1\n-1 1 0\n1 1 1\n')
        for atom in range(1,4):
            f.write('1 -1 2 0 1\n')
            for energy in (-1,1):
                f.write(str(energy)+' '+' '.join(str(atom*(i+1)) for i in range(9))+'\n')


def make_row(path):
    return dict(entry={'path':str(path),'label':path.parent.name,'capabilities':{'source_format':'DOSCAR'}},
        left='1',right='2,3',element1='',element2='')


def test_batch_doscar_reads_once_and_preserves_total_components(qapp,tmp_path,monkeypatch):
    import core.parsers.doscar as module
    path=tmp_path/'DOSCAR'; write_doscar(path)
    tasks=prepare_row(make_row(path), ['d','dxy'], ['p','py'], 'total', ('Mo','N'), MODES[1])
    original=module.parse_doscar_spin_all
    calls=[]
    def counted(*args,**kwargs):
        calls.append(args[1]); return original(*args,**kwargs)
    monkeypatch.setattr(module,'parse_doscar_spin_all',counted)
    worker=BatchAnalysisWorker(list(enumerate(tasks)),tmp_path)
    results=[];worker.task_ready.connect(lambda *args:results.append(args))
    worker.run()
    assert len(calls)==1
    assert len(results)==2 and all(not r[2] for r in results)
    data=read_result(results[0][1])
    np.testing.assert_allclose(data[0][1]['d'],35.)
    np.testing.assert_allclose(data[0][1]['dxy'],5.)
    np.testing.assert_allclose(data[1][1]['p'],18.)
    assert data[0][2] is None


def test_batch_failure_does_not_abort_other_system(qapp,tmp_path):
    path=tmp_path/'DOSCAR';write_doscar(path)
    good=prepare_row(make_row(path),['d'],['p'],'total',('Mo','N'),MODES[1])[0]
    bad=replace(good,context=replace(good.context,primary_path=str(tmp_path/'missing')))
    worker=BatchAnalysisWorker([(0,bad),(1,good)],tmp_path)
    results=[];worker.task_ready.connect(lambda *args:results.append(args));worker.run()
    assert results[0][2] and not results[1][2]


def test_file_changed_after_preview_is_rejected(qapp,tmp_path):
    path=tmp_path/'DOSCAR';write_doscar(path)
    tasks=prepare_row(make_row(path),['d'],['p'],'total',('Mo','N'),MODES[1])
    path.write_text(path.read_text()+'\n')
    worker=BatchAnalysisWorker(list(enumerate(tasks)),tmp_path)
    results=[];worker.task_ready.connect(lambda *args:results.append(args));worker.run()
    assert all('changed after preview' in r[2] for r in results)


def write_xml(path):
    fields=['energy','s','py','pz','px','dxy','dyz','dz2','dxz','x2-y2']
    ions=''
    for i in (1,2,3):
        rows=''.join('<r>'+str(e)+' '+' '.join(str(i*(j+1)) for j in range(9))+'</r>' for e in (-1,1))
        ions+=f'<set comment="ion {i}"><set comment="spin 1">{rows}</set></set>'
    path.write_text('<modeling><generator><i name="version">6.4.3</i></generator>'
        '<atominfo><array name="atoms"><set><rc><c>Mo</c></rc><rc><c>N</c></rc><rc><c>N</c></rc></set></array></atominfo>'
        '<structure name="finalpos"><crystal><varray name="basis"><v>5 0 0</v><v>0 5 0</v><v>0 0 5</v></varray></crystal>'
        '<varray name="positions"><v>0 0 0</v><v>0.2 0 0</v><v>0 0.2 0</v></varray></structure>'
        '<calculation><dos><i name="efermi">0</i><total><array><set><set comment="spin 1"><r>-1 1 0</r><r>1 1 1</r></set></set></array></total>'
        '<partial><array>'+''.join('<field>'+f+'</field>' for f in fields)+'<set>'+ions+'</set></array></partial></dos></calculation></modeling>')


def test_xml_per_atom_output_matches_single_parse_and_group_sum(tmp_path):
    from core.parsers.vasprun import parse_vasprun_spin_all
    path=tmp_path/'vasprun.xml';write_xml(path)
    atoms={}
    aggregate=parse_vasprun_spin_all(str(path),'1,2,3',orbitals=['dxy','py'],per_atom_output=atoms)
    assert set(atoms)=={1,2,3}
    single=parse_vasprun_spin_all(str(path),'2',orbitals=['dxy','py'])
    for orb in ['dxy','py']:
        np.testing.assert_allclose(atoms[2][1][orb],single[1][orb])
        np.testing.assert_allclose(aggregate[1][orb],sum(atoms[i][1][orb] for i in atoms))


def test_xml_preflight_element_validation(tmp_path):
    path=tmp_path/'vasprun.xml';write_xml(path)
    row=make_row(path);row['entry']['capabilities']['source_format']='vasprun.xml'
    row.update(left='Mo',right='N',element1='Mo',element2='N')
    assert len(prepare_row(row,['d'],['p'],'total',('Mo','N'),MODES[1]))==2
    row['element2']='Mo'
    with pytest.raises(ValueError,match='expected element'):
        prepare_row(row,['d'],['p'],'total',('Mo','N'),MODES[1])


def test_result_view_uses_batch_atom_identity(qapp,tmp_path):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    path=tmp_path/'DOSCAR';write_doscar(path)
    task=prepare_row(make_row(path),['d'],['p'],'total',('Mo','N'),MODES[1])[0]
    worker=BatchAnalysisWorker([(0,task)],tmp_path);worker.run()
    window=HybridizationWindow(AppState())
    window.frag1.entry_atoms.setText('99')
    window._show_batch_result(task,read_result(tmp_path/'00000.npz'))
    assert '[Atoms: 1]' in window._ax_mid.get_title(loc='left')
    assert '[Atoms: 2]' in window._ax_bot.get_title(loc='left')
    assert '99' not in window._ax_mid.get_title(loc='left')
    window.close()

def pump_until(app, predicate, seconds=20):
    import time
    deadline=time.monotonic()+seconds
    while not predicate():
        app.processEvents()
        if time.monotonic()>deadline:
            raise AssertionError('Asynchronous operation did not complete')
        time.sleep(.01)
    app.processEvents()


def test_batch_dialog_preview_run_switch_export_and_invalidation(qapp,tmp_path,monkeypatch):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    from ui.hybridization_batch_dialog import HybridizationBatchDialog
    from ui.i18n import get_language_manager, set_combo_value
    from PySide6.QtWidgets import QFileDialog
    manager=get_language_manager();manager.set_language('en',persist=False)
    path=tmp_path/'DOSCAR';write_doscar(path)
    state=AppState();state.file_entries=[make_row(path)['entry']]
    window=HybridizationWindow(state)
    window.frag1.entry_atoms.setText('1');window.frag2.entry_atoms.setText('2,3')
    window.frag1._orbital_checks['d'].setChecked(True)
    window.frag2._orbital_checks['p'].setChecked(True)
    dialog=HybridizationBatchDialog(window)
    dialog.result_selected.connect(window._show_batch_result)
    set_combo_value(dialog.mode,MODES[1])
    dialog._preview()
    pump_until(qapp,lambda: dialog.preview.isEnabled())
    assert len(dialog.tasks)==2
    assert dialog.run_button.isEnabled()
    dialog._run()
    pump_until(qapp,lambda: dialog.preview.isEnabled())
    assert len(dialog.results)==2 and not dialog.errors
    dialog._select(1)
    assert '[Atoms: 3]' in window._ax_bot.get_title(loc='left')
    previous=window._cached_data
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:str(tmp_path))
    dialog._export()
    pump_until(qapp,lambda: dialog._export_queue is None,seconds=30)
    assert not dialog._export_errors
    root=dialog._export_root
    assert len(list(root.glob('*.png')))==2
    assert len(list(root.glob('*.svg')))==2
    assert (root/'tasks.json').exists() and (root/'summary.csv').exists()
    assert window._cached_data is previous
    assert '[Atoms: 3]' in window._ax_bot.get_title(loc='left')
    dialog.sources.item(0,2).setText('3')
    assert not dialog.tasks and not dialog.run_button.isEnabled()
    dialog.close();window.close()


def test_preview_rejects_partial_plan(qapp,tmp_path):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    from ui.hybridization_batch_dialog import HybridizationBatchDialog
    from ui.i18n import set_combo_value
    path=tmp_path/'DOSCAR';write_doscar(path)
    state=AppState();state.file_entries=[make_row(path)['entry'],make_row(path)['entry']]
    window=HybridizationWindow(state)
    window.frag1.entry_atoms.setText('1');window.frag2.entry_atoms.setText('2,3')
    window.frag1._orbital_checks['d'].setChecked(True)
    window.frag2._orbital_checks['p'].setChecked(True)
    dialog=HybridizationBatchDialog(window);set_combo_value(dialog.mode,MODES[1])
    dialog.sources.item(1,2).setText('999')
    dialog._preview();pump_until(qapp,lambda:dialog.preview.isEnabled())
    assert not dialog.tasks and not dialog.run_button.isEnabled()
    assert '999' in dialog.status.text()
    dialog.close();window.close()


def test_cancellation_preserves_completed_results_and_resumes(qapp,tmp_path):
    path=tmp_path/'DOSCAR';write_doscar(path)
    tasks=prepare_row(make_row(path),['d'],['p'],'total',('Mo','N'),MODES[1])
    worker=BatchAnalysisWorker(list(enumerate(tasks)),tmp_path)
    stop={'requested':False};results=[]
    worker.isInterruptionRequested=lambda:stop['requested']
    def completed(*args):
        results.append(args);stop['requested']=True
    worker.task_ready.connect(completed);worker.run()
    assert len(results)==1 and not results[0][2]
    retry=BatchAnalysisWorker([(1,tasks[1])],tmp_path)
    retry.task_ready.connect(lambda *args:results.append(args));retry.run()
    assert len(results)==2 and not results[1][2]


def test_batch_workspace_mapping_roundtrip(tmp_path):
    from models.app_state import AppState
    path=tmp_path/'DOSCAR';write_doscar(path)
    state=AppState();state.hybridization_batch={'rows':[make_row(path)],'mode':MODES[1]}
    saved=tmp_path/'workspace.json';state.save_workspace(str(saved))
    other=AppState();other.load_workspace(str(saved))
    assert other.hybridization_batch==state.hybridization_batch

@pytest.mark.parametrize('fmt',['xml','doscar'])
def test_noncollinear_atom_output_preserves_sum(tmp_path,fmt):
    from core.pdos_metadata import PDOSInputContext
    if fmt=='xml':
        from core.parsers.vasprun import parse_vasprun_spin_all as parser
        from xml.etree import ElementTree as ET
        path=tmp_path/'vasprun.xml';write_xml(path)
        tree=ET.parse(path)
        for ion in tree.findall('.//partial/array/set/set'):
            i=int(ion.attrib['comment'].split()[-1])
            for r in ion.findall('.//r'):
                e=r.text.split()[0]
                r.text=e+' '+' '.join(str(v) for j in range(9) for v in (i+j+1,0,0,(i+j+1)/4))
        tree.write(path)
        context=PDOSInputContext(str(path),'vasprun.xml')
        orbitals=['dxy','py']
    else:
        from core.parsers.doscar import parse_doscar_spin_all as parser
        path=tmp_path/'DOSCAR'
        with path.open('w') as f:
            f.write('3 3 1 0\n0 0 0\n0\nCAR\nnoncollinear\n1 -1 2 0 1\n-1 1 0\n1 1 1\n')
            for i in (1,2,3):
                f.write('1 -1 2 0 1\n')
                for e in (-1,1):
                    f.write(str(e)+' '+' '.join(str(v) for j in range(4) for v in (i+j+1,0,0,(i+j+1)/4))+'\n')
        incar=tmp_path/'INCAR';incar.write_text('LNONCOLLINEAR = .TRUE.\n')
        context=PDOSInputContext(str(path),'DOSCAR',metadata_path=str(incar))
        orbitals=['d','p']
    atoms={}
    total=parser(str(path),'1,2,3',orbitals=orbitals,input_context=context,per_atom_output=atoms)
    for spin in (1,2,3):
        for orb in orbitals:
            np.testing.assert_allclose(total[spin][orb],sum(atoms[i][spin][orb] for i in (1,2,3)))
