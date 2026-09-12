"""Runtime English/Chinese localization without changing scientific values."""
from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit,
    QMenu, QTabWidget, QTableWidget, QWidget,
)


SOURCE_ROLE = int(Qt.UserRole) + 417
LAST_RENDERED_ROLE = SOURCE_ROLE + 1
SKIP_TRANSLATION_ROLE = SOURCE_ROLE + 2
_SETTINGS_KEY = "ui/language"


ZH_CN = {
    "Click a completed row to view its plot. Export saves results; workspaces save atom mappings.": "点击已完成任务可查看图像。导出用于保存结果，工作区用于保存原子映射。",
    "Wait for the single analysis to finish before exporting.": "请等待单次分析完成后再导出。",
    "Batch analysis…": "批量分析…",
    "Batch hybridization analysis": "批量轨道杂化分析",
    "Select systems and edit atom mappings. Orbitals and spin are copied from Fragment 1 / Fragment 2 when previewing.": "勾选体系并编辑原子映射。预览时使用片段 1／片段 2 已选的轨道和自旋设置。",
    "Pairing:": "配对方式：",
    "Copy current atom selections": "复制当前原子选择",
    "System": "体系",
    "Fragment 1 atoms": "片段 1 原子",
    "Fragment 2 atoms": "片段 2 原子",
    "Expected element 1 (optional)": "预期元素 1（可选）",
    "Expected element 2 (optional)": "预期元素 2（可选）",
    "Preview tasks": "预览任务",
    "Run pending tasks": "运行待处理任务",
    "Retry failed tasks": "重试失败任务",
    "Cancel after current operation": "完成当前操作后取消",
    "Export completed results": "导出已完成结果",
    "Orbitals": "轨道",
    "Pairing": "配对方式",
    "Status": "状态",
    "Preview tasks before running.": "请先预览任务，再批量运行。",
    "Inputs changed. Preview tasks again.": "输入已改变，请重新预览任务。",
    "Select systems and orbitals for both fragments first.": "请先选择体系以及两个片段的轨道。",
    "Checking source capabilities and atom mappings…": "正在检查数据能力和原子映射…",
    "Pending": "待处理",
    "Tasks": "任务数量",
    "Preview cancelled. Preview again to run.": "预览已取消。请重新预览后再运行。",
    "Failed": "失败",
    "Completed": "已完成",
    "Cancelled. Completed results are retained; pending tasks can resume.": "已取消。已完成结果保留，可继续运行待处理任务。",
    "Cancellation requested. Waiting for current file operation…": "已请求取消，等待当前文件操作结束…",
    "Exporting": "正在导出",
    "One to one": "一对一",
    "One to many (individual)": "一对多：逐对",
    "One to many (merged)": "一对多：合并",
    "Many to many (ordered)": "多对多：按顺序",
    "Many to many (all pairs)": "多对多：全部组合",
    "Group to group": "原子组对原子组",
    "Batch result: bond lengths are not included. Use single analysis for geometry.": "批量结果暂不包含键长。几何分析请使用单次分析入口。",

    "Fill total curves": "填充 total 曲线",
    "Manual orbital colors take priority over themes. Restore defaults to clear them.": "手动轨道颜色优先于主题。点击恢复默认配色可清除手动设置。",
    "Default orbital colors": "默认分轨道配色",
    "Orbital colors…": "轨道颜色…",
    "Import main PDOS colors": "导入主界面 PDOS 配色",
    "Restore default colors": "恢复默认配色",
    "Fill totals alongside components": "同时显示分轨道时填充 total",
    "Select orbitals in the Fragment tab first.": "请先在片段选项卡中选择轨道。",
    # Main navigation and actions
    "File": "文件", "Run": "运行", "View": "视图", "Help": "帮助",
    "Theme": "外观主题", "Add Files...": "添加文件…", "Add Folder...": "添加文件夹…",
    "Save Workspace...": "保存工作区…", "Load Workspace...": "加载工作区…",
    "Export CSV...": "导出 CSV…", "Save Current Image...": "保存当前图片…",
    "Batch Export Images...": "批量导出图片…", "Exit": "退出",
    "Clear All Data": "清空全部数据", "Run DBand Calculation": "运行 d 带计算",
    "Orbital Hybridization Analysis": "轨道杂化分析",
    "Toggle Left Control Panel": "显示/隐藏左侧控制面板",
    "Toggle Results Table": "显示/隐藏结果表",
    "Open Data/Labels Settings": "打开数据/标签设置",
    "Open Style/Legend Settings": "打开样式/图例设置",
    "Open Pattern Settings": "打开图案设置", "Open Axes Settings": "打开坐标轴设置",
    "Reset Chart View": "重置图表视图", "Toggle Global Grid": "显示/隐藏网格",
    "Light Mode": "浅色模式", "Dark Mode": "深色模式",
    "Documentation": "使用说明", "About DBand Studio": "关于 DBand Studio",
    "3. Actions": "3. 操作", "▶  Run Calculation": "▶  运行计算",
    "Export CSV": "导出 CSV", "Export Images ▾": "导出图片 ▾",
    "⚛ Orbital Hybridization Analysis": "⚛ 轨道杂化分析",
    "Comparison Bar Chart": "对比柱状图", "PDOS Curves": "PDOS 曲线",
    "Multi-System PDOS": "多体系 PDOS",
    "Ready — drag files here or click Add Files.": "就绪 — 可将文件拖到此处或点击“添加文件”。",
    "Cleared.": "已清空。", "Waiting for plot generation...": "正在等待生成绘图…",
    "Fragment input changed. Generate a new analysis before interpreting the plot.":
        "片段输入已更改。请重新生成分析后再查看结果。",
    "Parsing data and calculating geometry in background...": "正在后台解析数据并计算几何结构…",
    "Discarded stale analysis result after fragment input changed.":
        "片段输入已更改，已丢弃过期的分析结果。",
    "Hybridization plot and geometry analysis generated.": "杂化图和几何分析已生成。",
    "Calculating d-band centers...": "正在计算 d 带中心…",
    "Preparing image export...": "正在准备图片导出…",
    "Initializing...": "正在初始化…", "Initializing Matplotlib engine...": "正在初始化 Matplotlib 引擎…",
    "Scanning for external plugins...": "正在扫描外部插件…", "Building UI components...": "正在构建界面组件…",
    "Starting DBand Studio...": "正在启动 DBand Studio…",
    "d-band metrics use the VASP d projection. Standard vasprun.xml and DOSCAR data cannot independently select 3d, 4d, or 5d.":
        "d 带指标使用 VASP 的 d 投影。标准 vasprun.xml 和 DOSCAR 数据不能独立选择 3d、4d 或 5d。",

    # File and parameter panels
    "1. Data Source": "1. 数据源", "Type:": "类型：", "Auto Detect": "自动检测",
    "📂 Add Files": "📂 添加文件", "📁 Add Folder": "📁 添加文件夹",
    "Remove": "移除", "Rename": "重命名", "Clear All": "全部清除",
    "Copy Details": "复制详情", "Copied": "已复制", "Aux Files": "辅助文件",
    "Copied import details to the clipboard.": "已将导入详情复制到剪贴板。",
    "Select Structure...": "选择结构文件…", "Select Metadata...": "选择元数据文件…",
    "Select Spin Partner...": "选择自旋配对文件…",
    "Remove Auxiliary Files": "移除辅助文件",
    "System Label": "体系标签", "Data": "数据", "No file selected.": "未选择文件。",
    "Label": "标签", "Range": "范围", "Basic Properties": "基本属性",
    "Orbital Weights (%)": "轨道权重（%）", "Orbital Centers (εd_orb, eV)": "轨道中心（εd_orb，eV）",
    "Width (eV)": "宽度（eV）", "Filling%": "填充率%",
    "Needs input": "需要输入", "Blocked": "已阻止", "Not checked": "未检查",
    "Copy the selected file's import diagnosis for issue reports": "复制所选文件的导入诊断信息，用于问题反馈",
    "Select auxiliary files that DBand Studio is authorized to read": "选择允许 DBand Studio 读取的辅助文件",
    "Double-click the System Label to rename it": "双击体系标签可重命名",
    "This entry predates import preflight; re-add it to inspect.": "此条目早于导入预检功能；请重新添加以执行检查。",
    "2. Calculation Parameters": "2. 计算参数",
    "Target Atoms (e.g. 1,2,5-8 or Fe):": "目标原子（例如 1,2,5-8 或 Fe）：",
    "⚙️ Configure": "⚙️ 配置", "Global Default (leave blank for all)": "全局默认（留空表示全部）",
    "Spin Mode:": "自旋模式：", "Total": "总计", "Spin-Up": "自旋向上",
    "Spin-Down": "自旋向下", "Integration Range:": "积分范围：",
    "All Energy Range": "全部能量范围", "Below Fermi Level (≤ Ef)": "费米能级以下（≤ Ef）",
    "Custom Range (rel. to Ef):": "自定义范围（相对于 Ef）：", "Integration:": "积分方法：",
    "Trapezoid (NumPy)": "梯形积分（NumPy）", "Simpson (SciPy)": "辛普森积分（SciPy）",
    "Configure Target Atoms for each system independently": "为每个体系独立配置目标原子",

    # Shared dialogs and chart controls
    "Data Control": "数据设置", "Style Settings": "样式设置", "Graph Pattern": "图案设置",
    "Labels": "标签", "Axes & Ticks": "坐标轴与刻度", "Legend": "图例",
    "Axes Settings": "坐标轴设置", "Settings": "设置", "Apply": "应用",
    "Close": "关闭", "Cancel": "取消", "Save": "保存", "OK": "确定",
    "Open": "打开", "Yes": "是", "No": "否", "Browse...": "浏览…",
    "Systems:": "体系：", "System:": "体系：", "Theme:": "主题：",
    "Mode:": "模式：", "Orbital:": "轨道：", "Spin:": "自旋：",
    "📊 Data": "📊 数据", "🎨 Style": "🎨 样式", "⚙️ Axes": "⚙️ 坐标轴",
    "🎨 Pattern": "🎨 图案", "🏷️ Labels": "🏷️ 标签", "🗂️ Legend": "🗂️ 图例",
    "🎨 Colors": "🎨 颜色", "🎨 Set Colors": "🎨 设置颜色",
    "Fill": "填充", "Alpha:": "透明度：", "LW:": "线宽：",
    "Show εd line": "显示 εd 标线", "Total d-DOS": "总 d-DOS", "Total d": "总 d",
    "Total (Up+Down)": "总计（向上+向下）", "Spin Up": "自旋向上", "Spin Down": "自旋向下",
    "All Selected Systems": "所有已选体系",
    "All (3 Subplots)": "全部（3 个子图）", "Total Only": "仅总计",
    "Spin-Up Only": "仅自旋向上", "Spin-Down Only": "仅自旋向下",
    "Group Width:": "分组宽度：", "Bar Gap (%):": "柱间距（%）：",
    "Edge Color:": "边框颜色：", "Edge Width:": "边框宽度：",
    "Black": "黑色", "White": "白色", "None": "无", "Same as Fill": "与填充相同",
    "Show Value Labels": "显示数值标签", "Position:": "位置：",
    "Auto (Outside)": "自动（外侧）", "Center": "居中", "Inside Base": "底部内侧",
    "Value Font Size:": "数值字号：", "X-Tick Font Size:": "X 轴刻度字号：",
    "X-Tick Rotation:": "X 轴刻度旋转：", "Spine Width:": "轴框宽度：",
    "Tick Dir X/Y:": "X/Y 刻度方向：", "Ticks:": "刻度：",
    "Bot": "下", "Lft": "左", "Top": "上", "Rgt": "右",
    "Grid": "网格", "Y=0 Line": "Y=0 线", "Show Legend": "显示图例",
    "Font Size:": "字号：", "Marker Scale:": "标记缩放：", "Columns:": "列数：",
    "Frame": "边框", "best": "最佳", "upper right": "右上", "upper left": "左上",
    "lower right": "右下", "lower left": "左下", "outside top": "顶部外侧",
    "outside right": "右侧外部", "out": "向外", "in": "向内", "inout": "双向",
    "Coordinate Ranges": "坐标范围", "X Range:": "X 轴范围：", "Y Range:": "Y 轴范围：",
    "Min": "最小值", "Max": "最大值", "to": "至", "Spines (Borders)": "轴框（边界）",
    "Line Width:": "线宽：", "Show:": "显示：", "Right": "右", "Bottom": "下",
    "Left": "左", "Tick Direction:": "刻度方向：", "Show Grid": "显示网格",

    # Batch image export
    "Batch Export Images": "批量导出图片",
    "Export every analyzed system with the current PDOS style and axes settings.":
        "使用当前 PDOS 样式和坐标轴设置导出每个已分析体系。",
    "Output folder:": "输出文件夹：", "Choose an output folder": "请选择输出文件夹",
    "Format:": "格式：", "Resolution (DPI):": "分辨率（DPI）：",
    "Individual PDOS image for each selected system": "为每个选中体系导出单独的 PDOS 图片",
    "Select All": "全选", "Clear": "清除", "D-band center summary bar chart": "d 带中心汇总柱状图",
    "Current multi-system PDOS comparison": "当前多体系 PDOS 对比图", "Export": "导出",
    "Choose Export Folder": "选择导出文件夹", "Missing Folder": "缺少文件夹",
    "Choose an output folder.": "请选择输出文件夹。", "Nothing Selected": "未选择内容",
    "Select at least one image to export.": "请至少选择一张要导出的图片。",
    "Nothing to Export": "没有可导出的内容", "Export Failed": "导出失败",
    "Export Folder Error": "导出目录错误", "Open Export Folder": "打开导出文件夹",
    "Save Current Image": "保存当前图片", "Save Hybridization Chart": "保存杂化图",

    # Hybridization window
    "Orbital Hybridization Analysis (Async)": "轨道杂化分析（异步）",
    "Fragment 1": "片段 1", "Fragment 2": "片段 2", "Alias (optional):": "别名（可选）：",
    "Data Source:": "数据源：", "Atoms:": "原子：", "e.g. Metal": "例如：金属",
    "Spin Mode": "自旋模式", "Geometry Analysis": "几何分析",
    "Bond Cutoff (Å):": "成键截断距离（Å）：", "All pairs within cutoff": "截断距离内的所有原子对",
    "Shortest bond only": "仅最短键", "Bond Atoms 1:": "成键原子 1：",
    "Bond Atoms 2:": "成键原子 2：", "Integration Settings": "积分设置",
    "Method:": "方法：", "Range:": "范围：", "All": "全部", "Custom": "自定义",
    "Global Style": "全局样式", "Fill Area": "填充区域",
    "Fill Transparency (Alpha)": "填充透明度（Alpha）", "Plot Settings": "绘图设置",
    "Show Center Lines": "显示中心标线",
    "Show d-band Centers on All Panels": "在全部图中显示 d 带中心",
    "Sync X-Range to All": "将 X 轴范围同步到全部",
    "Overlap": "重叠图", "Frag 1": "片段 1", "Frag 2": "片段 2",
    "Follow Overlap (Frag 1)": "跟随重叠图（片段 1）",
    "Follow Overlap (Frag 2)": "跟随重叠图（片段 2）",
    "Export DOS CSV": "导出 DOS CSV", "Save Plot PNG": "保存绘图",
    "⚙️ Settings": "⚙️ 设置", "🚀 Run Comprehensive Analysis": "🚀 运行综合分析",
    "🔬 Generate Hybridization Plot": "🔬 生成杂化图", "Analyzing...": "分析中…",
    "📈 Hybridization Plot": "📈 杂化图", "📥 Export Bond Lengths to CSV": "📥 导出键长 CSV",
    "Fragment 1 Atom": "片段 1 原子", "Fragment 2 Atom": "片段 2 原子",
    "Distance (Å)": "距离（Å）", "📏 Bond Length Statistics": "📏 键长统计",
    "Input changed — generate a new hybridization analysis": "输入已更改 — 请重新生成杂化分析",
    "Hybridization Overlap": "杂化重叠图", "d-band Center (eV)": "d 带中心（eV）",
    "d-band Center Comparison": "d 带中心对比",

    # Help/about
    "Documentation - DBand Studio": "DBand Studio 使用说明",
    "DBand Studio User Guide": "DBand Studio 用户指南", "About DBand Studio": "关于 DBand Studio",
    "Version": "版本", "Author:": "作者：", "Info": "提示", "Warning": "警告",
    "Success": "成功", "Error": "错误", "Processing": "处理中",
    "Invalid Input": "输入无效", "Unknown File Type": "未知文件类型",
    "Parsing Error": "解析错误", "Unexpected Error": "意外错误",
    "Save Failed": "保存失败", "Load Failed": "加载失败",
    "Workspace Saved": "工作区已保存", "Workspace Loaded": "工作区已加载",
    "Fermi Level Notice": "费米能级提示", "Colors": "颜色",
    "Configure Target Atoms per System": "按体系配置目标原子",
    "Leave the input blank to use the global Target Atoms setting.": "留空时使用全局目标原子设置。",
    "Global Default": "全局默认", "Select Files": "选择文件", "Select Folder": "选择文件夹",
    "Rename Label": "重命名标签", "New label:": "新标签：",
    "Please import files first.": "请先导入文件。", "Add files first.": "请先添加文件。",
    "Select a file row first.": "请先选择一个文件条目。",
    "No vasprun.xml / DOSCAR / PDOS_* files found in this folder.":
        "此文件夹中未找到 vasprun.xml、DOSCAR 或 PDOS_* 文件。",
    "Select at least one integration range.": "请至少选择一个积分范围。",
    "Invalid Emin / Emax for custom range.": "自定义范围的 Emin / Emax 无效。",
    "No results.": "没有可导出的结果。", "Generate this chart before exporting it.": "请先生成该图表再导出。",
    "Run a calculation and generate charts before batch exporting.": "请先运行计算并生成图表，再执行批量导出。",
    "Please select a data source file for both fragments.": "请为两个片段都选择数据源文件。",
    "Please select at least one orbital for both fragments.": "请为两个片段都至少选择一个轨道。",
    "Generate a plot first.": "请先生成绘图。", "No systems selected.": "未选择任何体系。",
}


def _translate_html(text: str) -> str | None:
    if "<h3>1. Target Atoms</h3>" in text:
        style = text[:text.index("<h3>")]
        return style + """
<h3>1. 目标原子</h3>
<p>指定需要提取和分析的原子序号。例如输入 <code>1,2,3-5</code>，将解析第 1、2、3、4、5 号原子。<br>
留空时，程序会自动解析体系中<b>全部原子</b>的投影态密度（PDOS）。</p>
<h3>2. 自旋设置</h3>
<ul><li><b>总计（自旋向上 + 自旋向下）</b>：合并两个自旋通道计算总 d 带中心。</li>
<li><b>仅自旋向上</b>：仅提取并分析多数自旋电子态。</li>
<li><b>仅自旋向下</b>：仅提取并分析少数自旋电子态。</li></ul>
<h3>3. 积分范围</h3>
<p>设置用于计算 d 带中心的能量积分窗口 [E_min, E_max]。</p>
<ul><li><b>全部能量范围</b>：对数据提供的完整能量范围积分。</li>
<li><b>费米能级以下</b>：仅对费米能级以下的占据态积分。</li>
<li><b>自定义范围</b>：手动输入相对于费米能级（E_f = 0 eV）的上下限。</li></ul>
<h3>4. 图表与样式控制</h3>
<p>高级图表标签页右上角提供数据、样式和坐标轴设置。可切换主题、调整坐标范围、填充透明度，并导出适合论文使用的高分辨率图片。</p>
"""
    if "A focused, professional, and aesthetic toolkit" in text:
        return (
            "<p style='text-align: center; font-size: 13px; line-height: 1.5; "
            "font-family: \"Segoe UI\", sans-serif;'>专注、专业且美观的科研数据处理工具。<br>"
            "提供高质量的 VASP d 带中心分析、轨道杂化可视化<br>"
            "以及高效的电子结构数据处理流程。</p>")
    if "All rights reserved" in text and "Nian an" in text:
        return (
            "<div style='background-color: rgba(10, 132, 255, 0.08); padding: 15px; "
            "border-radius: 8px; border: 1px solid rgba(10, 132, 255, 0.2);'>"
            "<p style='font-size: 12px; line-height: 1.6; text-align: justify; margin: 0; "
            "font-family: \"Segoe UI\", sans-serif;'><b>© 2026 Nian an。保留所有权利。</b><br><br>"
            "本软件由 <b>Nian an</b> 独立构思、开发和维护。作者保留本软件、源代码及衍生算法的全部所有权、控制权和知识产权。"
            "未经明确授权，严禁以任何形式擅自分发、逆向工程或用于商业用途。</p></div>")
    if text.startswith("Author: <b>Nian an</b>"):
        return text.replace("Author:", "作者：", 1)
    return None


def translate_text(text: str, language: str | None = None) -> str:
    """Translate display text while leaving unknown/user content untouched."""
    if not text:
        return text
    language = language or get_language_manager().language
    if language != "zh_CN":
        return text
    if text in ZH_CN:
        return ZH_CN[text]
    html = _translate_html(text) if "<" in text else None
    if html is not None:
        return html

    for prefix in ("▼ ", "▶ "):
        if text.startswith(prefix):
            return prefix + ZH_CN.get(text[len(prefix):], text[len(prefix):])

    multi_match = re.match(
        r"^Multi-System (.+) PDOS Comparison \((.+)\)$", text)
    if multi_match:
        target, spin = multi_match.groups()
        return f"多体系 {ZH_CN.get(target, target)} PDOS 对比（{ZH_CN.get(spin, spin)}）"

    patterns = (
        (r"^Version (v.+)$", r"版本 \1"),
        (r"^Fragment 1: (.+)$", r"片段 1：\1"),
        (r"^Fragment 2: (.+)$", r"片段 2：\1"),
        (r"^Orbital Hybridization: (.+) vs (.+)$", r"轨道杂化：\1 与 \2"),
        (r"^(.+) Total PDOS$", r"\1 总 PDOS"),
        (r"^Spin-Up d-DOS$", r"自旋向上 d-DOS"),
        (r"^Spin-Down d-DOS$", r"自旋向下 d-DOS"),
        (r"^SAXIS-Projected Up d-DOS$", r"SAXIS 投影自旋向上 d-DOS"),
        (r"^SAXIS-Projected Down d-DOS$", r"SAXIS 投影自旋向下 d-DOS"),
        (r"^(.+) Spin-Up PDOS$", r"\1 自旋向上 PDOS"),
        (r"^(.+) Spin-Down PDOS$", r"\1 自旋向下 PDOS"),
        (r"^(.+) SAXIS-Projected Up PDOS$", r"\1 SAXIS 投影自旋向上 PDOS"),
        (r"^(.+) SAXIS-Projected Down PDOS$", r"\1 SAXIS 投影自旋向下 PDOS"),
        (r"^Color for (.+)$", r"设置 \1 的颜色"),
        (r"^Set color for (.+)\.\.\.$", r"设置 \1 的颜色…"),
        (r"^Ready · (.+)$", r"就绪 · \1"),
        (r"^Loaded (\d+) file\(s\)\.$", r"已加载 \1 个文件。"),
        (r"^Completed: (.+)$", r"已完成：\1"),
        (r"^Calculating (\d+)/(\d+) file\(s\) using (.+)\.\.\.$",
         r"正在使用 \3 计算文件 \1/\2…"),
        (r"^Integration changed to (.+)\. Run Calculation to refresh all results\.$",
         r"积分方法已更改为 \1。请运行计算以刷新全部结果。"),
        (r"^Workspace saved → (.+)$", r"工作区已保存 → \1"),
        (r"^Workspace loaded → (.+)$", r"工作区已加载 → \1"),
        (r"^CSV exported → (.+)$", r"CSV 已导出 → \1"),
        (r"^Chart saved → (.+)$", r"图表已保存 → \1"),
        (r"^Exported individual PDOS: (.+)$", r"已导出单体系 PDOS：\1"),
        (r"^Exported: (.+)$", r"已导出：\1"),
        (r"^Batch export completed — (\d+) saved, (\d+) failed\.$",
         r"批量导出完成 — 已保存 \1 个，失败 \2 个。"),
        (r"^Batch export cancelled — (\d+) saved, (\d+) failed\.$",
         r"批量导出已取消 — 已保存 \1 个，失败 \2 个。"),
        (r"^Cannot save image:\n(.+)$", r"无法保存图片：\n\1"),
        (r"^Cannot save chart:\n(.+)$", r"无法保存图表：\n\1"),
        (r"^Cannot write CSV:\n(.+)$", r"无法写入 CSV：\n\1"),
        (r"^Cannot create the output folder:\n(.+)$", r"无法创建输出文件夹：\n\1"),
        (r"^Cannot open the preferred export folder:\n(.+)$", r"无法打开首选导出文件夹：\n\1"),
        (r"^Chart saved to:\n(.+)$", r"图表已保存至：\n\1"),
        (r"^Data exported to:\n(.+)$", r"数据已导出至：\n\1"),
        (r"^Exported to:\n(.+)$", r"已导出至：\n\1"),
        (r"^Bond lengths exported to (.+)$", r"键长数据已导出至 \1"),
    )
    for pattern, replacement in patterns:
        if re.match(pattern, text):
            return re.sub(pattern, replacement, text)
    return text


def combo_value(combo: QComboBox) -> str:
    """Return the stable English value behind a localized combo item."""
    value = combo.itemData(combo.currentIndex(), SOURCE_ROLE)
    return str(value) if value is not None else combo.currentText()


def find_combo_value(combo: QComboBox, value: str) -> int:
    for index in range(combo.count()):
        source = combo.itemData(index, SOURCE_ROLE)
        if (str(source) if source is not None else combo.itemText(index)) == value:
            return index
    return -1


def set_combo_value(combo: QComboBox, value: str) -> bool:
    index = find_combo_value(combo, value)
    if index < 0:
        return False
    combo.setCurrentIndex(index)
    return True


def configure_matplotlib_language(language: str | None = None) -> None:
    """Select fonts that preserve Times styling or render Chinese reliably."""
    import matplotlib

    language = language or get_language_manager().language
    if language == "zh_CN":
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = [
            "Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
    else:
        matplotlib.rcParams["font.family"] = "serif"
        matplotlib.rcParams["font.serif"] = [
            "Times New Roman", "SimSun", "Arial Unicode MS", "DejaVu Serif"]


def localized_stylesheet(stylesheet: str, language: str | None = None) -> str:
    """Append a Chinese-capable Qt font override only in Chinese mode."""
    language = language or get_language_manager().language
    if language != "zh_CN":
        return stylesheet
    return stylesheet + """

QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Segoe UI", sans-serif;
}
"""


class LanguageManager(QObject):
    language_changed = Signal(str)

    def __init__(self):
        super().__init__()
        saved = str(QSettings("DBandStudio", "DBandStudio").value(
            _SETTINGS_KEY, "en") or "en")
        self.language = saved if saved in {"en", "zh_CN"} else "en"
        configure_matplotlib_language(self.language)
        self._installed_app = None
        self._applying = False

    def install(self, app: QApplication | None):
        if app is not None and self._installed_app is not app:
            app.installEventFilter(self)
            self._installed_app = app

    def set_language(self, language: str, persist: bool = True):
        if language not in {"en", "zh_CN"}:
            raise ValueError(f"Unsupported language: {language}")
        self.language = language
        configure_matplotlib_language(language)
        if persist:
            settings = QSettings("DBandStudio", "DBandStudio")
            settings.setValue(_SETTINGS_KEY, language)
            settings.sync()
        app = QApplication.instance()
        if app is not None:
            for widget in app.topLevelWidgets():
                self.apply(widget)
        self.language_changed.emit(language)

    def toggle(self):
        self.set_language("zh_CN" if self.language == "en" else "en")

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show, QEvent.Polish):
            QTimer.singleShot(0, lambda obj=watched: self._safe_apply(obj))
        return False

    def _safe_apply(self, obj):
        try:
            if isinstance(obj, QObject):
                self.apply(obj)
        except RuntimeError:
            pass

    def _apply_property(self, obj, getter, setter, source_key, last_key):
        current = getter()
        source = obj.property(source_key)
        last = obj.property(last_key)
        if source is None or current != last:
            source = current
            obj.setProperty(source_key, source)
        rendered = translate_text(str(source), self.language)
        if current != rendered:
            setter(rendered)
        obj.setProperty(last_key, rendered)

    def _apply_combo(self, combo):
        current_index = combo.currentIndex()
        combo.blockSignals(True)
        try:
            for index in range(combo.count()):
                current = combo.itemText(index)
                source = combo.itemData(index, SOURCE_ROLE)
                last = combo.itemData(index, LAST_RENDERED_ROLE)
                if source is None or current != last:
                    source = current
                    combo.setItemData(index, source, SOURCE_ROLE)
                skip = bool(combo.property("_i18n_skip_items")) or bool(
                    combo.itemData(index, SKIP_TRANSLATION_ROLE))
                rendered = str(source) if skip else translate_text(
                    str(source), self.language)
                if current != rendered:
                    combo.setItemText(index, rendered)
                combo.setItemData(index, rendered, LAST_RENDERED_ROLE)
            combo.setCurrentIndex(current_index)
        finally:
            combo.blockSignals(False)

    def _apply_tabs(self, tabs):
        sources = dict(tabs.property("_i18n_tab_sources") or {})
        lasts = dict(tabs.property("_i18n_tab_lasts") or {})
        for index in range(tabs.count()):
            current = tabs.tabText(index)
            if index not in sources or current != lasts.get(index):
                sources[index] = current
            rendered = translate_text(str(sources[index]), self.language)
            if current != rendered:
                tabs.setTabText(index, rendered)
            lasts[index] = rendered
        tabs.setProperty("_i18n_tab_sources", sources)
        tabs.setProperty("_i18n_tab_lasts", lasts)

    def _apply_table_items(self, table):
        for column in range(table.columnCount()):
            item = table.horizontalHeaderItem(column)
            if item is not None:
                self._apply_item(item)
        if table.objectName() == "ResultsHeaderTable":
            for row in range(table.rowCount()):
                for column in range(table.columnCount()):
                    item = table.item(row, column)
                    if item is not None:
                        self._apply_item(item)

    def _apply_item(self, item):
        current = item.text()
        source = item.data(SOURCE_ROLE)
        last = item.data(LAST_RENDERED_ROLE)
        if source is None or current != last:
            source = current
            item.setData(SOURCE_ROLE, source)
        rendered = translate_text(str(source), self.language)
        if current != rendered:
            item.setText(rendered)
        item.setData(LAST_RENDERED_ROLE, rendered)

    def apply(self, root):
        if self._applying or not isinstance(root, QObject):
            return
        self._applying = True
        try:
            objects = [root] + root.findChildren(QObject)
            for obj in objects:
                if bool(obj.property("_i18n_skip")):
                    continue
                if isinstance(obj, QAction):
                    self._apply_property(
                        obj, obj.text, obj.setText,
                        "_i18n_source_text", "_i18n_last_text")
                elif isinstance(obj, QMenu):
                    self._apply_property(
                        obj, obj.title, obj.setTitle,
                        "_i18n_source_title", "_i18n_last_title")
                elif isinstance(obj, QAbstractButton):
                    self._apply_property(
                        obj, obj.text, obj.setText,
                        "_i18n_source_text", "_i18n_last_text")
                elif isinstance(obj, QLabel):
                    self._apply_property(
                        obj, obj.text, obj.setText,
                        "_i18n_source_text", "_i18n_last_text")
                if isinstance(obj, QGroupBox):
                    self._apply_property(
                        obj, obj.title, obj.setTitle,
                        "_i18n_source_title", "_i18n_last_title")
                if isinstance(obj, QLineEdit):
                    self._apply_property(
                        obj, obj.placeholderText, obj.setPlaceholderText,
                        "_i18n_source_placeholder", "_i18n_last_placeholder")
                if isinstance(obj, QComboBox):
                    self._apply_combo(obj)
                if isinstance(obj, QTabWidget):
                    self._apply_tabs(obj)
                if isinstance(obj, QTableWidget):
                    self._apply_table_items(obj)
                if isinstance(obj, QWidget) and obj.windowTitle():
                    self._apply_property(
                        obj, obj.windowTitle, obj.setWindowTitle,
                        "_i18n_source_window_title", "_i18n_last_window_title")
                if isinstance(obj, QWidget) and obj.toolTip():
                    self._apply_property(
                        obj, obj.toolTip, obj.setToolTip,
                        "_i18n_source_tooltip", "_i18n_last_tooltip")
        finally:
            self._applying = False


_MANAGER = None


def get_language_manager() -> LanguageManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = LanguageManager()
    return _MANAGER


def tr(text: str) -> str:
    return translate_text(text)


def set_translated_text(widget, source_text: str) -> None:
    """Set dynamic widget text while preserving its reversible English source."""
    rendered = translate_text(source_text)
    widget.setProperty("_i18n_source_text", source_text)
    widget.setProperty("_i18n_last_text", rendered)
    widget.setText(rendered)
