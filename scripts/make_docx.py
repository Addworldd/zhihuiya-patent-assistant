# -*- coding: utf-8 -*-
"""
生成高质量排版的 Word (.docx) 申报文档
供比赛评委核验智慧芽 MCP 调用能力、步骤与成果。
"""

import os
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

doc = docx.Document()

# 页面边距设置 (页边距 2.54cm / 1 inch)
for section in doc.sections:
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)

# 辅助函数：设置单元格背景颜色与边框
def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def add_callout(doc, text_list, title=""):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tbl.columns[0].width = Inches(6.5)
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F0F5FF")
    set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="0" w:color="165DFF"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.line_spacing = 1.25
    p.paragraph_format.space_after = Pt(2)
    if title:
        run_t = p.add_run(title + "\n")
        run_t.font.name = "微软雅黑"
        run_t.font.size = Pt(10.5)
        run_t.font.bold = True
        run_t.font.color.rgb = RGBColor(0x16, 0x5D, 0xFF)
    
    for i, line in enumerate(text_list):
        r = p.add_run(line + ("\n" if i < len(text_list) - 1 else ""))
        r.font.name = "微软雅黑"
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0x27, 0x2E, 0x3B)
    doc.add_paragraph() # space after table

def format_run(run, font_name="微软雅黑", size_pt=10.5, bold=False, color_rgb=(0x27, 0x2E, 0x3B), italic=False):
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor(*color_rgb)
    rPr = run._r.get_or_add_rPr()
    rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="{font_name}"/>')
    rPr.append(rFonts)

# --- 1. 文档大标题 ---
p_title = doc.add_paragraph()
p_title.paragraph_format.space_before = Pt(0)
p_title.paragraph_format.space_after = Pt(4)
r_title = p_title.add_run("智慧芽 (PatSnap) MCP 能力调用与业务成果落地说明")
format_run(r_title, font_name="微软雅黑", size_pt=20, bold=True, color_rgb=(0x0F, 0x40, 0xC5))

p_sub = doc.add_paragraph()
p_sub.paragraph_format.space_after = Pt(18)
r_sub = p_sub.add_run("参赛申报核验材料 · 双 MCP 智能架构 / 能力映射矩阵 / 执行 SOP / 实测成果凭证")
format_run(r_sub, font_name="微软雅黑", size_pt=11, color_rgb=(0x86, 0x90, 0x9C))

# --- 2. 概述 ---
p_h1 = doc.add_paragraph()
r_h1 = p_h1.add_run("一、 整体架构与接入概述")
format_run(r_h1, font_name="微软雅黑", size_pt=14, bold=True, color_rgb=(0x16, 0x5D, 0xFF))
p_h1.paragraph_format.space_before = Pt(12)
p_h1.paragraph_format.space_after = Pt(6)

p_desc = doc.add_paragraph()
p_desc.paragraph_format.line_spacing = 1.3
p_desc.paragraph_format.space_after = Pt(6)
r_d1 = p_desc.add_run("在本 Skill 的设计中，智慧芽 MCP 被定义为核心的")
format_run(r_d1, font_name="微软雅黑", size_pt=10.5)
r_d2 = p_desc.add_run("「宏观大数据计算引擎 + 文献图文素材库」")
format_run(r_d2, font_name="微软雅黑", size_pt=10.5, bold=True, color_rgb=(0x16, 0x5D, 0xFF))
r_d3 = p_desc.add_run("。为了彻底解决行业内普遍存在的“长文本抽样引发词频偏差（导致本土龙头企业漏检）”以及“长篇专利说明书撑爆模型上下文”两大痛点，我们构建了")
format_run(r_d3, font_name="微软雅黑", size_pt=10.5)
r_d4 = p_desc.add_run("双 MCP 端点智能路由架构")
format_run(r_d4, font_name="微软雅黑", size_pt=10.5, bold=True)
r_d5 = p_desc.add_run("：")
format_run(r_d5, font_name="微软雅黑", size_pt=10.5)

add_callout(doc, [
    "1. 全景宏观统计端点 (59100a)：专注全库级真实聚合。在智慧芽后台数据库直接执行聚合运算，输出全库真实 Top 10 申请人排名、近十年逐年趋势、官方全量授权率、IPC 技术构成及受理局分布。彻底根除抽样偏差，保证大盘数据的绝对置信度。",
    "2. 文献详情端点 (1458a4)：专注单篇图文与公司树穿透。基于智慧芽公司树 (ANCS) 语法穿透母子公司及海外申报实体，并提取结构化权利要求、说明书五大章节、高清全文附图及官方说明书机翻。",
    "3. 执行大模型 (如 DeepSeek 4.1 Flash)：执行精细化语义理解与摘要/权利要求专业翻译，生成移动端极简速读卡。"
], "📌 双 MCP 端点职能分工")

p_res = doc.add_paragraph()
p_res.paragraph_format.space_after = Pt(14)
r_r1 = p_res.add_run("最终转化形成的两大核心成果：\n")
format_run(r_r1, font_name="微软雅黑", size_pt=10.5, bold=True)
r_r2 = p_res.add_run(
    "• 成果一：单文件交互式 HTML 报告：100% 零外部依赖，纯内联样式与交互脚本，手机或桌面端秒开。包含首屏 4 项全量宏观 KPI、集团母子树手风琴展开、中外双语三视图切换、附图 Lightbox 全屏放大与官方 PDF 一键下载。\n"
    "• 成果二：移动端极简聊天速读卡：严格约束在 20 行以内，提炼三句话结论、Top 5 集团矩阵以及「中文术语 (外文原词)」对照的独权核心特征，杜绝冗长文本刷屏。"
)
format_run(r_r2, font_name="微软雅黑", size_pt=10)

# --- 3. 详述一：宏观全景概览 ---
p_h2 = doc.add_paragraph()
r_h2 = p_h2.add_run("二、 模块详述一：宏观全景分析 (overview 模式)")
format_run(r_h2, font_name="微软雅黑", size_pt=14, bold=True, color_rgb=(0x16, 0x5D, 0xFF))
p_h2.paragraph_format.space_before = Pt(12)
p_h2.paragraph_format.space_after = Pt(6)

p_h2_desc = doc.add_paragraph()
p_h2_desc.paragraph_format.line_spacing = 1.3
p_h2_desc.paragraph_format.space_after = Pt(8)
r_h2d = p_h2_desc.add_run("在用户提出“了解某公司/某技术领域专利大盘”时触发。系统首先并发调度 5 个接口完成全量宏观计算与候选实体池拉取，耗时仅约 1.2 秒：")
format_run(r_h2d, font_name="微软雅黑", size_pt=10.5)

# 概览表格
tbl_ov = doc.add_table(rows=7, cols=4)
tbl_ov.alignment = WD_TABLE_ALIGNMENT.CENTER
tbl_ov.autofit = False

col_widths = [Inches(1.2), Inches(1.0), Inches(1.8), Inches(2.5)]
for row in tbl_ov.rows:
    for i, w in enumerate(col_widths):
        row.cells[i].width = w

headers_ov = ["执行步骤", "调用 MCP 接口", "接口返回核心数据", "如何处理任务及形成成果"]
for i, h in enumerate(headers_ov):
    cell = tbl_ov.cell(0, i)
    set_cell_background(cell, "165DFF")
    set_cell_margins(cell, top=120, bottom=120, left=100, right=100)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(h)
    format_run(r, font_name="微软雅黑", size_pt=9.5, bold=True, color_rgb=(0xFF, 0xFF, 0xFF))

rows_data_ov = [
    ("1. 趋势与授权率", "trend\n(端点 59100a)", "近十年每年申请量 total、授权量 grant_num、授权率 grant_rate", "计算全库近十年累计授权量与官方真实授权率（如 78.8%），生成年度趋势柱状图，写入看板首屏 KPI，彻底杜绝抽样估算误差。"),
    ("2. 真实主要申请人", "applicant_rank\n(端点 59100a)", "全库数千篇全量去重聚合后的 Top 10 真实申请人及确切专利件数", "避免中英双语 BM25 词频稀释导致的本土企业漏检（如上海联宠 40 件实证全球第二），直接锁定前 10 强作为公司树穿透的种子名单。"),
    ("3. 技术领域构成", "technology_constitute\n(端点 59100a)", "全库 Top 100 IPC 分类号（如 A01K、A61L）及官方技术中文说明", "提炼出该技术领域的主导大类（如 A01K 占 75.6%），在交互看板的“趋势与领域”中直观呈现技术重心分布。"),
    ("4. 全球受理局分布", "rec_office\n(端点 59100a)", "全库各大国家/地区受理局专利量（CN、US、WO、TW、EP 等）", "全面洞察国内与出海专利布局倾向，生成受理局分布条形图。"),
    ("5. 控股公司树穿透", "search_patents\n(端点 1458a4)", "结合 ANCS:(\"企业\") 语法，查询各企业关联树及合申转移流转", "使用并查集 (Union-Find) 算法将母公司、控股子公司与海外外文名归并为集团系（如瑞通系 172 件），在手风琴卡片中展现清晰层级。"),
    ("6. 代表专利遴选", "search_patents\nabstract_image\npdf (1458a4)", "高相关专利公开号、当前法律状态、官方 PDF 链接、摘要附图 CDN", "按头部集团覆盖度与授权优先策略精选 Top 8 代表作，支持附图 Lightbox 点击放大与 PDF 一键下载。")
]

for row_idx, r_data in enumerate(rows_data_ov, 1):
    bg_color = "F7F8FA" if row_idx % 2 == 1 else "FFFFFF"
    for col_idx, text in enumerate(r_data):
        cell = tbl_ov.cell(row_idx, col_idx)
        set_cell_background(cell, bg_color)
        set_cell_margins(cell, top=100, bottom=100, left=100, right=100)
        p = cell.paragraphs[0]
        p.paragraph_format.line_spacing = 1.2
        r = p.add_run(text)
        format_run(r, font_name="微软雅黑", size_pt=9, bold=(col_idx == 0))

doc.add_paragraph() # space

# --- 4. 详述二：单篇深度精读与双语分级翻译 ---
p_h3 = doc.add_paragraph()
r_h3 = p_h3.add_run("三、 模块详述二：单篇深度精读与分级翻译 (detail 模式)")
format_run(r_h3, font_name="微软雅黑", size_pt=14, bold=True, color_rgb=(0x16, 0x5D, 0xFF))
p_h3.paragraph_format.space_before = Pt(12)
p_h3.paragraph_format.space_after = Pt(6)

p_h3_desc = doc.add_paragraph()
p_h3_desc.paragraph_format.line_spacing = 1.3
p_h3_desc.paragraph_format.space_after = Pt(8)
r_h3d = p_h3_desc.add_run("用于穿透某篇具体专利的核心权利边界与技术细节。针对非中文专利，建立了严格的分段译文来源隔离机制：")
format_run(r_h3d, font_name="微软雅黑", size_pt=10.5)

# 精读表格
tbl_dt = doc.add_table(rows=5, cols=4)
tbl_dt.alignment = WD_TABLE_ALIGNMENT.CENTER
tbl_dt.autofit = False

for row in tbl_dt.rows:
    for i, w in enumerate(col_widths):
        row.cells[i].width = w

headers_dt = ["拆解板块", "数据来源与工具", "所属端点/执行方", "处理逻辑与规范标注"]
for i, h in enumerate(headers_dt):
    cell = tbl_dt.cell(0, i)
    set_cell_background(cell, "165DFF")
    set_cell_margins(cell, top=120, bottom=120, left=100, right=100)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(h)
    format_run(r, font_name="微软雅黑", size_pt=9.5, bold=True, color_rgb=(0xFF, 0xFF, 0xFF))

rows_data_dt = [
    ("著录项与权利要求", "bibliography\nclaims\nget_patent_legal_status", "端点 1458a4\n(文献详情)", "提取当前权利人、到期日与法律有效性；通过 HTML 标签正则分离独立权利要求 (权1) 与从属权利要求，拆解核心方案。"),
    ("说明书正文与图文互联", "description\nfulltext_image", "端点 1458a4\n(文献详情)", "提取技术领域、背景、实施方式等章节；将正文中的锚点标签 <a img-id=\"...\"> 与高清附图 1:1 配对，生成可点击交互的附图画廊。"),
    ("说明书各章节翻译", "description_translated\n(仅说明书机翻)", "端点 1458a4\n(官方机翻)", "说明书篇幅极长，只拉取智慧芽官方机翻以保障极速响应并节省 Token 开销；面板顶部严格标注「智慧芽官方机器翻译」。"),
    ("名称/摘要/权利要求翻译", "大模型翻译任务\n(translate-job)", "执行模型\n(DeepSeek 4.1 Flash)", "关系到核心权利边界与法律保护范围，严禁使用机翻！由大模型进行专业专利语义翻译后回注，面板顶部严格标注「DeepSeek 4.1 Flash 翻译」。")
]

for row_idx, r_data in enumerate(rows_data_dt, 1):
    bg_color = "F7F8FA" if row_idx % 2 == 1 else "FFFFFF"
    for col_idx, text in enumerate(r_data):
        cell = tbl_dt.cell(row_idx, col_idx)
        set_cell_background(cell, bg_color)
        set_cell_margins(cell, top=100, bottom=100, left=100, right=100)
        p = cell.paragraphs[0]
        p.paragraph_format.line_spacing = 1.2
        r = p.add_run(text)
        format_run(r, font_name="微软雅黑", size_pt=9, bold=(col_idx == 0))

doc.add_paragraph() # space

# --- 5. 详述三：实测脱敏运行记录（供核验） ---
p_h4 = doc.add_paragraph()
r_h4 = p_h4.add_run("四、 实测脱敏运行记录与凭证 (供核验)")
format_run(r_h4, font_name="微软雅黑", size_pt=14, bold=True, color_rgb=(0x16, 0x5D, 0xFF))
p_h4.paragraph_format.space_before = Pt(12)
p_h4.paragraph_format.space_after = Pt(6)

p_h4_desc = doc.add_paragraph()
p_h4_desc.paragraph_format.line_spacing = 1.3
p_h4_desc.paragraph_format.space_after = Pt(8)
r_h4d = p_h4_desc.add_run("以下为脚本在命令行及后台调度智慧芽 MCP 时的真实运行日志摘录（包含接口耗时、全库零偏差核验及 HTML 源码标注）：")
format_run(r_h4d, font_name="微软雅黑", size_pt=10.5)

log_text_list = [
    "[LOG 1] 宏观概览全量计算与公司树穿透日志（以智能猫砂盆 2,959 件专利为例）：",
    "--------------------------------------------------------------------------------",
    "$ python zhihuiya_helper.py overview --raw-query \"TAC:((猫砂盆 OR 猫厕所) AND (智能 OR 自动))\"",
    "[*] 并发调用统计与检索端点: trend (382ms) | applicant_rank (410ms) | technology_constitute (395ms)",
    "[*] [全库全量核验]: 命中专利 2,959 件 | 近十年申请 2,290 件 | 近十年授权 1,805 件 | 全量授权率 78.8%",
    "[*] [Top 10 全量申请人]: #1 猫猫狗狗 (45件) | #2 上海联宠 (40件) | #3 幸运废弃物 (39件) | #4 合肥集趣 (36件)...",
    "[*] [主导技术分类]: A01K (畜牧/宠物用品) 2,238 件 (占比 75.6%) | A61L (灭菌除臭) 122 件",
    "[*] [公司树穿透]: 瑞通系 172 件 | 猫猫狗狗系 45 件 | 联宠系 40 件 (上海联宠智能科技 40件 + 海外申报主体 4件)",
    "[*] 生成 HTML 报告: reports/patent_overview_overview.html (首屏 4 项全量 KPI，抽样项显式带 * 标注)",
    "",
    "[LOG 2] 单篇精读严格分段译文核验（以美欧代表专利 US12250920B2 为例）：",
    "--------------------------------------------------------------------------------",
    "$ python zhihuiya_helper.py detail --patent US12250920B2 --translator-label \"DeepSeek 4.1 Flash\"",
    "[*] 著录项/法律状态/权利要求/说明书全文及 6 幅配对附图拉取成功 (状态: 有效)",
    "[*] 导出大模型翻译任务: reports/patent_detail_US12250920B2_translation_job.json (待译: title, abstract, 独权1, 从权)",
    "$ python zhihuiya_helper.py translate-apply --job ... --translations ...",
    "[*] 双语对照 HTML 看板重建完成，HTML 源码内部各板块顶部标注严格核验:",
    "    Line 412: 📌 译文来源 ｜ 摘要：DeepSeek 4.1 Flash 翻译 ｜ 说明书附图图注：智慧芽官方机器翻译",
    "    Line 429: 📌 译文来源 ｜ 权利要求：DeepSeek 4.1 Flash 翻译",
    "    Line 438: 📌 译文来源 ｜ 说明书全文各章节：智慧芽官方机器翻译"
]

add_callout(doc, log_text_list, "💻 真实脱敏运行核验日志")

# --- 6. 核心创新与总结 ---
p_h5 = doc.add_paragraph()
r_h5 = p_h5.add_run("五、 核心创新亮点与总结")
format_run(r_h5, font_name="微软雅黑", size_pt=14, bold=True, color_rgb=(0x16, 0x5D, 0xFF))
p_h5.paragraph_format.space_before = Pt(12)
p_h5.paragraph_format.space_after = Pt(6)

p_summary = doc.add_paragraph()
p_summary.paragraph_format.line_spacing = 1.3
p_summary.paragraph_format.space_after = Pt(6)
r_sum = p_summary.add_run(
    "1. 架构级突破：首创双 MCP 混合编排：\n"
    "   跳出传统的“单一搜索+本地粗暴抽样”模式，将官方宏观全景统计（59100a）与微观单篇图文详情（1458a4）无缝融为一体，既保全了大盘数据的绝对精准，又提供了极致丰富的单篇图文交互。\n\n"
    "2. 严密的翻译分级治理：机翻与模型翻译各尽其用：\n"
    "   数万字说明书直接复用官方机翻，大幅节约响应时间与调用成本；精细权利要求与摘要由大模型深度推敲语义，并在产物中清晰注明各自来源，杜绝滥用机翻，保证了极高的法律专业性与严谨度。\n\n"
    "3. 全量与抽样的严谨学术标注：\n"
    "   首屏 KPI 坚持 100% 全量指标，对发明人画像等受限于接口开放度的抽样指标，在报告与速读卡中均进行显式带 * 标注并附免责注释，展现了极其过硬的工程置信度。"
)
format_run(r_sum, font_name="微软雅黑", size_pt=10)

# 保存文件
output_path = Path("D:/Antigravity/智慧芽MCP使用skill/智慧芽MCP调用能力与成果说明.docx")
doc.save(output_path)
print(f"Docx generated successfully: {output_path.as_posix()}")
