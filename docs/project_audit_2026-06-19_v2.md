# DBand Studio — 极致代码审计报告 v2

**审计日期**：2026-06-19 23:30
**审计模式**：冷酷审查模式（逐行）
**审计范围**：48 个源文件 / 约 4200 行
**审计基线**：41 个单元测试全部通过（`pytest tests/ -q` → 41 passed in 1.12s）

---

## 一、审计方法论

本次审计以"顶尖计算化学软件架构师"视角，按四个维度逐行拷问：

1. **科学计算逻辑严谨性**（致命级）—— 积分算法精度、费米能级对齐、自旋极化切片
2. **代码健壮性与异常处理**（严重级）—— 文件读取脆弱性、数组运算边界、NaN/Inf 防护
3. **工程架构与可维护性**（警告级）—— 单一职责、命名规范、重复代码
4. **打包分发与通用性**（常规级）—— 硬编码路径、依赖轻量化

**与 v1 审计文档的差异**：v1 文档部分结论已过时（如 P0-2.1 pyqtgraph 残留、P0-2.2 np.trapz、P1-3.5 annotate_center 迁移均已修复）。本次审计发现 v1 未记录的 **1 个新 P0 致命 BUG**。

---

## 二、致命问题（P0 — 必须立即修复）

### P0-1：`ui/charts/pdos_chart.py` 缺少 QMenu/QAction 导入【新发现，v1 未记录】

**位置**：`ui/charts/pdos_chart.py` L11-15（import 块）、L120、L122

**症状**：`_show_color_menu` 方法使用了 `QMenu` 和 `QAction`，但 import 块只导入了 `QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QColorDialog, QColor, Qt, Signal`。用户点击 "🎨 Style" → "Color" 按钮时，立即触发 `NameError: name 'QMenu' is not defined`。

**根因**：v4.0 重构时 import 块遗漏。PySide6 中 `QMenu` 在 `PySide6.QtWidgets`，`QAction` 在 `PySide6.QtGui`。

**影响**：轨道颜色自定义功能完全不可用。这是用户高频操作路径。

**修复方案**：
```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QColorDialog, QMenu
)
from PySide6.QtGui import QColor, QAction
```

### P0-2：`core/calculator.py` numpy≥2.0 trapz 兼容性【v1 已记录，实际已修复，残留边缘风险】

**位置**：`core/calculator.py` L41

**现状**：`_trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)` —— 已正确处理 numpy≥2.0 移除 `np.trapz` 的问题（v1 文档描述的 `np.trapz` 直接访问已不存在）。

**残留风险**：若 numpy 极老版本两者皆无（理论上 numpy 1.x 都有 `trapz`），`_trapz` 为 `None`，后续 `_trapz(total, ec)` 抛 `TypeError` 而非有意义的错误。

**修复方案**：加导入时防护：
```python
_trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)
if _trapz is None:
    raise ImportError("NumPy trapezoidal integration unavailable; requires numpy>=1.10")
```

### P0-3：pyqtgraph 残留导致 PDOS 保存崩溃【v1 已记录，已修复】

**位置**：`ui/main_window.py` L616-621

**现状**：已改为 `fig = self.pdos_chart.get_figure(); DataExporter.save_figure(fig, path)`。**已修复，无需再动**。

---

## 三、重要问题（P1 — 分享前必须修复）

### P1-1：VASPKIT 缺少 `parse_vaspkit_spin_all`【v1 已记录，未修复】

**位置**：`core/loader.py` L101-108 回退分支、`core/parsers/vaspkit.py`（无此函数）

**症状**：
1. `DataLoader.load_spin_all` 对 VASPKIT 走回退分支，调用两次 `cls.load()` —— 文件被解析两次。
2. **更严重**：对于非自旋 VASPKIT 文件（文件名不含 `_UP/_DW`），`_detect_spin_channel` 返回 `"unknown"`，`parse_vaspkit` 在 `spin="up"` 和 `spin="down"` 时都返回同一文件数据。导致 `rho_up == rho_dn`，`CalculationWorker` L84-88 检测 `is_spin=True`（误判），UI 显示错误的自旋极化状态。

**修复方案**：在 `vaspkit.py` 实现 `parse_vaspkit_spin_all`，单次解析返回四元组；`loader.py` 调用专用路径。

### P1-2：VASPKIT `ef=0.0` 无 UI 提示【v1 已记录，未修复】

**位置**：`core/parsers/vaspkit.py` L181

**症状**：VASPKIT PDOS 文件不含费米能级，解析器硬编码 `ef=0.0`。用户不知道能量未对齐，d 带中心计算结果有偏差。

**修复方案**：在 `CalculationWorker` 中检测 VASPKIT 文件类型，通过新信号 `ef_warning` 通知 UI 层显示一次性提示。

### P1-3：`hybridization_win.py` ValueError 死代码分支【v1 部分记录，未完全修复】

**位置**：`ui/hybridization_win.py` L570-588

**症状**：
- L583 `elif exc_cls == ValueError:` —— `ValueError` 不在 `_WARN_EXCEPTIONS` 元组中，`exc_cls` 永远为 `None`，此分支永不执行（死代码）。
- `HybridizationWorker` L71-72 会 emit `("ValueError", str(e))`，但 UI 层 L587 `else: QMessageBox.critical` 会把 ValueError 当成严重错误弹窗，语义错误。

**修复方案**：在 `_on_parse_error` 开头单独处理 `err_type == "ValueError"` 分支。

### P1-4：版本号散落不一致【v1 已记录，未修复】

| 位置 | 当前值 | 语义 |
|------|--------|------|
| `main.py:2` | `v1.0.0` | 软件版本（docstring） |
| `pyproject.toml:7` | `1.0.0` | 软件版本（打包元数据） |
| `models/app_state.py:124` | `_WORKSPACE_VERSION = "1.0"` | 序列化格式版本（语义不同） |
| `ui/splash_screen.py:61` | `v1.0` | 启动屏显示 |

**修复方案**：软件版本统一从 `pyproject.toml` 读取（通过 `importlib.metadata`）；工作区版本号独立保留但文档化注释说明语义差异。

### P1-5：`annotate_center` 迁移【v1 已记录，已完成】

**现状**：已迁移到 `utils/styling.py` L130-180。`core/calculator.py` 不再包含 matplotlib 代码。**已修复，无需再动**。

---

## 四、警告级问题（P2 — 提升健壮性）

### P2-1：`vaspkit.py` `np.loadtxt` 无异常防护
**位置**：`core/parsers/vaspkit.py` L68
**症状**：数据行含非数字字符时直接抛 `ValueError`，未被捕获。文件格式轻微损坏即崩溃。
**修复**：包裹 try/except 转 `DbandError`。

### P2-2：`vasprun.py` `_STRUCT_CACHE` 无大小上限
**位置**：`core/parsers/vasprun.py` L18
**症状**：全局字典无上限，长期运行加载多个文件会内存泄漏。
**修复**：改为 `OrderedDict` + 32 条上限的简易 LRU。

### P2-3：`hybridization_worker.py` local_cache 兜底不一致
**位置**：`core/services/hybridization_worker.py` L91-94
**症状**：local_cache 命中时 `if o in r_up` 跳过缺失轨道；shared_cache/全解析路径用 `.get(o, zeros)` 兜底。行为不一致。
**修复**：统一用 `.get(o, zeros)`。

### P2-4：`exporter.py` hybridization CSV 长度不匹配错位
**位置**：`core/services/exporter.py` L62
**症状**：两个片段能量轴长度不同时，`max(len(e1), len(e2))` 逐行输出会错位。
**修复**：分两段输出（Fragment 1 表 + Fragment 2 表），或插值对齐。

### P2-5：dark mode 硬编码色值散落
**位置**：`ui/charts/pdos_chart.py` L257/262/321/327、`ui/hybridization_win.py` L761/773/908-943
**症状**：`"#1E1E1E"`, `"#FFFFFF"`, `"#E0E0E0"`, `"black"`, `"#666666"` 等硬编码，违反"配色集中化"约定。
**修复**：迁移到 `utils/styling.py` 定义 `DARK_BG`, `DARK_FG`, `LIGHT_BG`, `LIGHT_FG`, `ZERO_LINE_DARK`, `ZERO_LINE_LIGHT` 等常量。

### P2-6：`plugins.py` `_PLUGIN_DIR` 打包路径问题
**位置**：`core/plugins.py` L44-47
**症状**：PyInstaller 打包后 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 指向临时解压目录，plugins 目录不存在。
**修复**：支持 `DBAND_PLUGINS_DIR` 环境变量覆盖；同时检查用户目录 `~/.dband/plugins/`。

---

## 五、常规级问题（P3 — 用户明确要求砍 numba）

### P3-1：砍掉 numba 依赖【用户明确要求】

**现状审计**：
- `core/calculator.py`：**已完全移除 numba**（无 `import numba`、无 `@jit`、docstring 明确说明移除原因）。
- `requirements.txt`：numba 已注释（L9-10）。
- `pyproject.toml` L35-38：仍保留 `[project.optional-dependencies] accel = ["numba>=0.58"]`。
- `tests/test_calculator.py` L165-190：`TestNumbaConsistency` 类名残留（实际测试不依赖 numba，只是断言结果有限）。

**结论**：numba 在运行时已无任何作用，仅 pyproject.toml 元数据和测试类名残留。

**修复方案**：
1. 从 `pyproject.toml` 移除 `[project.optional-dependencies] accel` 段。
2. `test_calculator.py` 的 `TestNumbaConsistency` 改名为 `TestNumericalStability`，更新注释。
3. `calculator.py` docstring 已经说明移除原因，无需再动。

**砍 numba 的合理性论证**：
- DOS 数组规模 10³–10⁵ 点，纯 NumPy trapz 已是亚毫秒级，numba JIT 首次调用多秒编译成本远超收益。
- numba 与 numpy 2.0、Python 3.13 兼容性历史不佳，PyInstaller 打包冲突频发。
- 移除后依赖链精简 4 个包（numba + llvmlite + 其依赖），打包体积减少约 80MB。

---

## 六、科学计算逻辑严谨性专项审查

### 6.1 积分算法精度 ✅

`core/calculator.py` 使用梯形法则（trapezoidal rule），对 DOS 网格足够密（NEDOS≥500）的情况精度满足要求。Simpson 法则理论上更高阶，但 VASP 网格通常均匀且密集，梯形法则误差 O(ΔE²) 可接受。

### 6.2 费米能级对齐 ✅

- `calc_metrics` L173：`e = energy - ef` 正确对齐。
- `CalculationWorker` L91-94：缓存原始 `energy + ef`，调用方计算 `e = energy - ef` 并传真实 ef。
- `HybridizationWorker` L106/L126：`e_aligned = energy - ef` 正确。
- `pdos_chart.py` L170：`e = e_raw - ef` 正确。
- `hybridization_win.py` L841：`calc_metrics(e1, rho1_export, ef=0.0, ...)` —— e1 已对齐，ef=0.0 正确。

### 6.3 自旋极化切片 ✅（VASPKIT 除外）

- `vasprun.py`：`spin 1` / `spin 2` 通道独立提取，`_ensure_positive` 逐通道应用。
- `doscar.py`：基于列数检测自旋（≥4 列），`rho_dn` 保留 VASP 原始负号约定，`rho_total = |up| + |dn|`。
- **VASPKIT 问题**：见 P1-1，非自旋文件被误判。

### 6.4 filling 精度 ✅

`_filling_core` L66-104 对跨 Ef 的 bin 做线性插值分裂，消除 O(ΔE) 系统误差。`TestFillingPrecision` 验证对称 DOS filling=50%±0.5%。这是相比 v3.x 的关键改进。

### 6.5 width 定义 ✅

`_integrate_core` L60-62：`width = sqrt(∫(E-center)²·ρ dE / ∫ρ dE)`，即二阶矩标准差。docstring 明确说明与 VASPKIT task-11x 的 FWHM 定义不同，避免用户混淆。

---

## 七、修复优先级路线图（v2）

| 优先级 | 问题 | 影响 | 状态 |
|--------|------|------|------|
| **P0-1** | pdos_chart.py QMenu/QAction 缺失 | 颜色按钮崩溃 | 待修复 |
| **P0-2** | calculator.py _trapz None 防护 | 边缘环境崩溃 | 待修复 |
| **P1-1** | VASPKIT spin_all 缺失 | 自旋误判+双重解析 | 待修复 |
| **P1-2** | VASPKIT ef=0 无提示 | 结果偏差无感知 | 待修复 |
| **P1-3** | hybridization_win ValueError 死代码 | 错误弹窗语义错误 | 待修复 |
| **P1-4** | 版本号散落 | 分享时混乱 | 待修复 |
| **P2-1** | vaspkit np.loadtxt 无防护 | 格式损坏即崩溃 | 待修复 |
| **P2-2** | _STRUCT_CACHE 无上限 | 内存泄漏 | 待修复 |
| **P2-3** | local_cache 兜底不一致 | 轨道静默丢失 | 待修复 |
| **P2-5** | dark mode 硬编码色值 | 配色约定违反 | 待修复 |
| **P2-6** | plugins 打包路径 | 分发后插件失效 | 待修复 |
| **P3-1** | 砍 numba 残留 | 依赖精简 | 待修复 |

---

## 八、架构亮点（值得保持）

1. **惰性导入 + 线程安全锁**：`core/parsers/__init__.py` 双重检查锁，QThread 并发安全。
2. **MemoryAwareLRUCache**：按内存淘汰，512MB 硬上限，防 OOM。
3. **DataLoader 注册表模式**：OCP 友好，插件扩展零侵入。
4. **filling 线性插值分裂**：消除 Ef 跨 bin 系统误差，科学严谨。
5. **能量契约统一**：缓存原始 energy+ef，调用方对齐，避免重复减法。
6. **持久化 axes**：hybridization_win 避免 cla→subplots→tight_layout 抖动。
7. **5 级异常体系**：UI 分级响应，用户体验清晰。
8. **异步 Worker + 三级缓存**：UI 不阻塞，主题/范围变化只重渲染。
