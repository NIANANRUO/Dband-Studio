# Spin-resolved DOS Design

## Goal

在不删除任何既有功能的前提下，正确处理 VASP 的非自旋、共线自旋、非共线和 SOC PDOS；对无法可靠解释的输入拒绝计算，而不是输出伪物理结果。

## Supported physical modes

| Mode | DOSCAR site-PDOS layout | Results exposed |
|---|---|---|
| `nonspin` | orbital total | total d-DOS、d 带中心 |
| `collinear` | orbital up/down | up、down、magnitude total |
| `noncollinear` / SOC | orbital total, m1, m2, m3 | total、m1/m2/m3、沿 `SAXIS` 的 projected up/down |

非共线投影采用 VASP spinor 基：`rho_up=(rho_total+m3)/2`、`rho_down=(rho_total-m3)/2`。它们必须标记为 “projected along SAXIS”，不得伪称普通共线自旋。若任何能点满足 `abs(m3) > rho_total + tolerance`，文件被拒绝。

## Backward compatibility

- 现有 `DataLoader.load_spin_all()` 的五元组接口保留。
- 非自旋和共线自旋结果、图表、导出和杂化流程不改变。
- `LORBIT=11` 的五个 d 轨道分量不改变。
- `LORBIT=10` 新增总 `d` 通道；它不伪造 dxy/dyz/dz2/dxz/dx2-y2 分解，UI/导出显示 `d-total`。
- VASPKIT、DOSCAR、vasprun.xml 的既有入口继续保留。

## Plot-style compatibility (non-negotiable)

本次不重写、不替换、不删减 `ui/charts/`、`utils/styling.py`、主题 JSON 或任何已有绘图控件。对原有非自旋与共线自旋数据，新增数据模型必须走原绘图数据入口，因此同一输入、同一用户设置下，线型、颜色、透明度、坐标轴、中心标线、字体、图例、镜像自旋显示、注释位置、导出格式和导出尺寸保持不变。

非共线/SOC 只新增可选数据通道；它不得改变默认选择或覆盖已保存的绘图设置。LORBIT=10 仅以 `d-total` 作为附加曲线标签，沿用现有主题和样式解析。

## Data contract

解析器内部新增 `PDOSMetadata`：`mode`、`orbital_resolution`、`spin_axis`、`magnetization`、`source_format`。所有数组必须与能量轴等长、有限且能量严格递增。积分窗口端点通过线性插值加入数组。

对 spin-labelled VASPKIT 文件，缺失 partner 是错误；不得把单通道降级成 total。对未知 DOSCAR 列布局、截断 PDOS、NaN/Inf、结构与 PDOS 原子数不一致，抛出 `DbandError`。

## Scientific traceability

每条结果保存：源路径、SHA-256、文件大小、mtime、费米能级、原子/轨道选择、能窗、积分法、模式与投影轴。`Simpson` 与 `trapezoid` 仅是数值方法，禁止声称天然等同某一 VASPKIT 版本。

## Acceptance criteria

1. 真实 `D:\VASP system\Mo_N4\0.3up\dos\DOSCAR` 在共线模式保持现有解析结果。
2. 合成非共线 DOSCAR 正确恢复 total/m1/m2/m3 和 SAXIS 投影通道。
3. LORBIT=10 正确给出总 d 带中心，且不出现伪造的五分量权重。
4. 非法网格、缺失 partner、列数不符合物理格式均失败且错误信息说明原因。
5. 全部现有测试与新增回归测试通过。
6. 现有绘图模式的 artist/style fingerprint 与导出图基线一致；非共线新增通道不改变原控制项的默认状态。
