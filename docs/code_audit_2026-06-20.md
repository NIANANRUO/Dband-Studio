# DBand Studio 代码审计报告 — 2026-06-20

> 审查范围: 全部 46 个 .py 源文件，约 9,300 行 | 审查标准: 科学计算正确性 > 健壮性 > 架构 > 分发

---

## 一、🚨 严重缺陷 (Critical Bugs / Logic Errors)

### C-1. lxml 依赖未声明 —— 运行时必然崩溃

**文件**: `core/parsers/vasprun.py` L61
**问题**: 

```python
from lxml import etree as ET
```

`lxml` 既不在 `pyproject.toml` 也不在 `requirements.txt` 中。pymatgen 官方虽然常与 lxml 一同安装，但 **lxml 不是 pymatgen 的强制依赖**。在任何干净的 venv 中执行 `pip install -r requirements.txt` 后，`from lxml import etree` 将直接抛出 `ModuleNotFoundError`，导致 vasprun.xml 解析完全不可用。

**严重性**: 致命。对 vasprun.xml 用户，程序无法启动（懒加载首次调用时崩溃）。

**修复**:

```toml
# pyproject.toml [project] dependencies 追加:
"lxml>=4.9.0",

# requirements.txt 追加:
lxml>=4.9.0
```

---

### C-2. multi_pdos_chart 直接调用已弃用的 np.trapz

**文件**: `ui/charts/multi_pdos_chart.py` L416–418

```python
sum_dos = np.trapz(dos, e)                # NumPy >= 2.0 已移除
center = np.trapz(e * dos, e) / sum_dos   # 直接崩溃
```

`np.trapz` 在 NumPy 2.0 中被移除，改为 `np.trapezoid`。项目其他位置通过 `calculator._trapz` 做了安全别名:

```python
# core/calculator.py L41
_trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)
```

但 `multi_pdos_chart.py` 绕过了这一层保护，直接调用原始名。任一 NumPy >= 2.0 环境打开多系统 PDOS 图即崩溃。

**严重性**: 致命。直接影响一个核心图表功能。

**修复**:

```python
# multi_pdos_chart.py 顶部导入
from core.calculator import _trapz

# L416-418 替换为
sum_dos = _trapz(dos, e)
center = _trapz(e * dos, e) / sum_dos
```

---

### C-3. vasprun.xml 解析: 冗余的 if ev == 'end' 分支

**文件**: `core/parsers/vasprun.py` L76–112

```python
elif ev == 'end':          # L85: 已经在此分支内
    if tag == 'array' and in_atoms:
        ...
    elif tag == 'structure' and in_finalpos:
        ...

    if ev == 'end':        # L93: 永远为 True —— 死代码
        if in_atoms and tag == 'rc':
            ...
```

L93 的 `if ev == 'end':` 嵌套在 `elif ev == 'end':` 内，条件永远为 True。不造成崩溃，但污染逻辑，且在多人维护时容易引入重构错误。

**严重性**: 中等（不影响运行，但属代码腐化）。

**修复**: 删除 L93 的冗余 `if ev == 'end':`，将其代码块缩进一提级。

---

### C-4. 版本号硬编码不一致

**文件**: `ui/help_dialogs.py` L113

```python
lbl_version = QLabel("Version v1.0.0")  # 硬编码
```

所有其他组件均调用 `utils.helpers.get_app_version()` 动态获取版本号，唯独此处硬编码。用户将永远看到 "v1.0.0"，与实际版本脱节。

**修复**:

```python
from utils.helpers import get_app_version
lbl_version = QLabel(f"Version v{get_app_version()}")
```

---

## 二、⚠️ 隐患与坏味道 (Code Smells / Performance Issues)

### S-1. 164 行重复暗色模式代码（4 文件几乎完全相同）

| 文件 | 行数 | 方法 |
|---|---|---|
| `ui/charts/bar_chart.py` | 376–410 (35行) | `_apply_dark_mode` |
| `ui/charts/pdos_chart.py` | 255–302 (48行) | `_apply_dark_mode` |
| `ui/charts/multi_pdos_chart.py` | 313–358 (46行) | `_apply_dark_mode` |
| `ui/hybridization_win.py` | 909–956 (48行) | `_apply_dark_mode` |

四个实现 90% 逻辑相同：设置前景/背景色 → tick_params → spine 颜色 → legend 颜色。任何修改必须在 4 处同步，极易遗漏。

**修复方案**: 提取到 `utils/styling.py` 作为函数 `apply_matplotlib_dark_mode(fig, axes_list, is_dark)`。

---

### S-2. matplotlib 初始化重复

| 文件 | 位置 | 内容 |
|---|---|---|
| `ui/charts/pdos_chart.py` | L42–55 | `_init_matplotlib` |
| `ui/charts/multi_pdos_chart.py` | L43–56 | `_init_matplotlib` |
| `utils/styling.py` | L24–30 | `init_matplotlib()` |

前两者有各自的内联实现，而 `utils/styling.py` 已有统一版本。应全部调用 `init_matplotlib()`。

---

### S-3. _read_vaspkit_blocks: 三趟扫描 I/O 反模式

**文件**: `core/parsers/vaspkit.py` L69–290

当前流程:
1. **第一趟**: `f.readlines()` 扫描所有 `#` 行找头部（全量 IO）
2. **第二趟**: `f.seek() + f.readline()` 计算每个 block 行数（全量 IO）
3. **第三趟**: `np.loadtxt(f"{filepath}#block_{i}")` 逐块回读（每块独立 IO）

一个大 PDOS 文件被全文读取 **3 次**。可重构为单趟流式解析。

**优化方案**: 单趟遍历所有行，记录 block 边界位置，然后按需 `np.loadtxt` 切片（一次 IO + 零散 loadtxt）。

---

### S-4. _read_doscar_raw: 全量 readlines OOM 风险

**文件**: `core/parsers/doscar.py` L69

```python
raw = f.readlines()  # 全部行加载到内存
```

对于 200+ 原子 × 2000 NEDOS 的超胞体系，DOSCAR 可达数百 MB。`readlines()` 将整个文件塞入内存，极易触发 OOM。

**优化方案**: 改为流式解析或分块读取。对于 VASP DOSCAR 格式，可以按 "行数 = NEDOS + 1（能头）" 逐原子块读取，每次仅保留当前原子的数据。

---

### S-5. VASP_FIELD_MAP 在循环内被反复构建

**文件**: `core/parsers/vasprun.py` L297–303

```python
for idx in target_indices:   # LOOP START
    field_map = { ... }       # ← 每次迭代重新创建同一字典
```

该映射不依赖 `idx`，纯常量。应提到模块级别。

---

### S-6. _accumulate 每原子重复调用 _select_orbital_columns

**文件**: `core/parsers/doscar.py` L199

```python
col_map = _select_orbital_columns(arr.shape[1], is_spin, target_orbs)
```

对于同一次解析，`n_cols` 和 `is_spin` 不变，此调用对每个原子重复一次。应提到 `_accumulate` 循环外部。

---

### S-7. RangeSelectorWidget 焦点外更改不生效

**文件**: `ui/widgets/range_selector.py`

`QLineEdit` 仅绑定 `returnPressed` 和 Apply 按钮的 `clicked`。用户在输入框中修改数值后如果直接点击图表（不按 Enter 也不点 Apply），新值不会触发重绘。对于实时预览场景，应补充 `textChanged` 信号连接（或至少添加 `editingFinished` 信号）。

---

### S-8. calculation_worker L90 全量 abs 开销

```python
total_check = sum(np.sum(np.abs(v)) for v in rho_d.values())
```

`np.abs(v)` 对每个轨道数组创建完整副本。若仅判断是否存在非零值，可用惰性版本:

```python
total_check = sum(np.count_nonzero(v) for v in rho_d.values())
```

---

### S-9. axes_config_dialog.py 字典重复键

**文件**: `ui/widgets/axes_config_dialog.py` L24–25

```python
"spine_bottom": True,   # L24
"spine_bottom": True,   # L25 ← 重复（后者覆盖前者，功能无害但代码脏）
```

`get_config()` 方法的返回值字典（L156–157）同样重复。

---

## 三、📦 工程与分发建议 (Packaging Advice)

### P-1. pyproject.toml 构建后端陈旧

当前使用 `setuptools` 的旧版后端声明:

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta:_legacy:_Backend"   # ← 已弃用
```

`_legacy_backend` 是过渡方案，现代 setuptools 直接使用 `setuptools.build_meta`。

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"
```

---

### P-2. config/ 和 assets/ 未纳入打包

`pyproject.toml` 中未声明 `[tool.setuptools.package-data]`，`pip install` 或 PyInstaller 不会自动包含非 `.py` 资源文件。

后果:
- `config/themes.json` 缺失 → 主题加载失败
- `assets/icon.png` / `assets/splash_bg.png` 缺失 → 程序仍然启动但无图标

**修复**:

```toml
[tool.setuptools.package-data]
"*" = ["*.json", "*.png", "*.jpg", "*.svg"]
```

或在 `MANIFEST.in` 中追加:

```
include config/themes.json
recursive-include assets *.png *.jpg *.svg
```

---

### P-3. splash_screen 三次 time.sleep 人为 1.2s 延迟

**文件**: `main.py` L57–73

```python
time.sleep(0.4)   # L61
time.sleep(0.4)   # L66
time.sleep(0.4)   # L71
```

合计 1.2s 空等。建议改为实际加载进度驱动（如监听 plugin 加载完成信号），或至少用 `QTimer.singleShot` 异步推进而非阻塞 sleep。

---

### P-4. __init__.py 懒加载锁的全局作用域

**文件**: `core/parsers/__init__.py` L15

```python
_lock = threading.Lock()
```

在模块级别创建锁通常是安全的，但如果该模块在多个 Python 进程间共享（如 multiprocessing 场景），`Lock` 不可跨进程序列化。当前项目不使用多进程，无实际风险，但值得加注释说明。

---

### P-5. DOSCAR 行格式容错缺口

**文件**: `core/parsers/doscar.py` L132–134

```python
except (ValueError, IndexError):
    if ragged:
        break       # 静默丢弃剩余数据行
    ragged = True
```

遇到格式异常行时直接 `break`，丢弃后续所有合法数据。更安全的做法是记录 WARNING 日志后 `continue` 跳过该行继续解析。

---

### P-6. PyInstaller 打包注意事项

当前项目依赖:
- `pymatgen` + `lxml` → PyInstaller 需显式声明隐藏导入 (`--hidden-import lxml.etree`)
- `matplotlib` → 需要 `--collect-data matplotlib` 收集字体/样式文件
- `PySide6` → 需要 Qt 平台插件 (`--collect-binaries PySide6`)

建议创建 `installer/hooks/` 目录存放 PyInstaller hook 文件。

---

## 四、汇总

| 优先级 | 数量 | 关键词 |
|---|---|---|
| 🚨 致命 | 4 | lxml 依赖 / np.trapz 弃用 / 死代码分支 / 版本硬编码 |
| ⚠️ 严重 | 9 | 重复代码(164行) / I/O 三趟扫描 / OOM 风险 / 循环内常量重定义 |
| 📦 建议 | 6 | 构建后端 / 资源打包 / splash 延迟 / PyInstaller |

**建议修复顺序**: C-1 → C-2 → C-4 → S-1 → S-2 → P-2 → P-1 → 余下按优先级递减。
