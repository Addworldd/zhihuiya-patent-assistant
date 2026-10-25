#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧芽 (PatSnap) 移动端专利报告自包含 HTML 渲染引擎
特点：
1. 100% 零外部依赖（纯内联 CSS + 原生轻量 JS + 内联 SVG 图表，离线/内网/手机端秒开）
2. 采用“首屏看板 + 顶部标签页 (Tabs) + 手风琴折叠 (Accordion) + 状态筛选器 + 附图点击放大 (Lightbox)”
3. 在不损失任何信息总量的前提下，将多屏长文浓缩为一页式移动端交互应用
"""

import datetime
import html
import re
from pathlib import Path


def _esc(text: object) -> str:
    if text is None:
        return ""
    return html.escape(str(text))


def _status_badge(status_str: str) -> tuple:
    """返回 (HTML徽章, 筛选分类key)"""
    s = str(status_str or "未知")
    if "有效" in s:
        return f'<span class="badge badge-valid">🟢 {_esc(s)}</span>', "valid"
    if "审中" in s or "PCT" in s:
        return f'<span class="badge badge-pending">🟡 {_esc(s)}</span>', "pending"
    if "失效" in s:
        return f'<span class="badge badge-invalid">⚪ {_esc(s)}</span>', "invalid"
    return f'<span class="badge badge-unknown">🔵 {_esc(s)}</span>', "other"


COMMON_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: #f4f6f9;
  color: #1d2129;
  line-height: 1.55;
  font-size: 14px;
  padding-bottom: 40px;
}
.container { max-width: 760px; margin: 0 auto; padding: 12px; }
.hero {
  background: linear-gradient(135deg, #0f40c5 0%, #165dff 60%, #3b82f6 100%);
  color: #fff;
  border-radius: 12px;
  padding: 18px 16px;
  margin-bottom: 12px;
  box-shadow: 0 4px 14px rgba(22, 93, 255, 0.18);
}
.hero-tag {
  display: inline-block;
  font-size: 12px;
  background: rgba(255,255,255,0.2);
  padding: 2px 8px;
  border-radius: 99px;
  margin-bottom: 6px;
}
.hero h1 { font-size: 18px; font-weight: 700; line-height: 1.35; margin-bottom: 8px; }
.hero-meta { font-size: 12px; opacity: 0.9; display: flex; flex-wrap: wrap; gap: 10px; }
.hero-summary {
  margin-top: 10px;
  background: rgba(255,255,255,0.14);
  border-left: 3px solid #fff;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}
@media (max-width: 480px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}
.kpi-card {
  background: #ffffff;
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid #e5e6eb;
  text-align: center;
}
.kpi-val { font-size: 20px; font-weight: 700; color: #165dff; }
.kpi-lbl { font-size: 12px; color: #86909c; margin-top: 2px; }
.tabs {
  display: flex;
  background: #e8ebf0;
  padding: 4px;
  border-radius: 10px;
  margin-bottom: 12px;
  position: sticky;
  top: 6px;
  z-index: 20;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.tab-btn {
  flex: 1;
  text-align: center;
  padding: 8px 4px;
  font-size: 13px;
  font-weight: 600;
  color: #4e5969;
  border-radius: 8px;
  cursor: pointer;
  border: none;
  background: transparent;
  transition: all 0.15s;
}
.tab-btn.active {
  background: #ffffff;
  color: #165dff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.card {
  background: #ffffff;
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid #e5e6eb;
}
.card-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e5e6eb;
  padding-bottom: 8px;
}
.bar-row { display: flex; align-items: center; margin-bottom: 8px; font-size: 12px; }
.bar-label { width: 72px; flex-shrink: 0; color: #4e5969; font-weight: 500; }
.bar-track { flex: 1; background: #f2f3f5; height: 10px; border-radius: 99px; overflow: hidden; margin: 0 8px; }
.bar-fill { background: linear-gradient(90deg, #165dff, #6aa1ff); height: 100%; border-radius: 99px; }
.bar-val { width: 52px; text-align: right; color: #1d2129; font-weight: 600; flex-shrink: 0; }
.acc-item {
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  margin-bottom: 8px;
  overflow: hidden;
  background: #fafbfc;
}
.acc-header {
  padding: 10px 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  user-select: none;
}
.acc-header:hover { background: #f7f9fc; }
.acc-title { font-weight: 600; font-size: 13.5px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.acc-body { display: none; padding: 10px 12px; border-top: 1px solid #e5e6eb; font-size: 12.5px; background: #fcfdfe; }
.acc-item.open .acc-body { display: block; }
.acc-arrow { font-size: 12px; color: #86909c; transition: transform 0.2s; }
.acc-item.open .acc-arrow { transform: rotate(180deg); }
.badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.badge-valid { background: #e8ffea; color: #00b42a; }
.badge-pending { background: #fff7e8; color: #ff7d00; }
.badge-invalid { background: #f2f3f5; color: #86909c; }
.badge-unknown { background: #e8f3ff; color: #165dff; }
.sub-tag {
  display: inline-block;
  padding: 3px 8px;
  margin: 3px 4px 3px 0;
  background: #fff;
  border: 1px solid #d9e1ec;
  border-radius: 6px;
  font-size: 12px;
}
.filter-bar { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
.filter-pill {
  padding: 4px 10px;
  border-radius: 99px;
  font-size: 12px;
  border: 1px solid #e5e6eb;
  background: #fff;
  cursor: pointer;
  color: #4e5969;
}
.filter-pill.active { background: #165dff; color: #fff; border-color: #165dff; font-weight: 600; }
.pat-card {
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 10px;
  background: #fff;
  transition: box-shadow 0.2s;
}
.pat-card:hover { box-shadow: 0 3px 10px rgba(22,93,255,0.08); }
.pat-main-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.pat-info-col { flex: 1; min-width: 0; }
.pat-thumb-box {
  flex-shrink: 0;
  width: 104px;
  height: 78px;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  background: #f8fafc;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
  cursor: zoom-in;
}
.pat-thumb-box img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 3px;
}
.pat-thumb-tag {
  position: absolute;
  right: 3px;
  bottom: 3px;
  background: rgba(29,33,41,0.68);
  color: #fff;
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  pointer-events: none;
}
.pat-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.pat-num { font-family: monospace; font-weight: 700; color: #165dff; font-size: 13px; background: #e8f3ff; padding: 2px 6px; border-radius: 4px; }
.pat-title { font-weight: 600; font-size: 14px; color: #1d2129; margin-bottom: 4px; }
.pat-meta { font-size: 12px; color: #86909c; display: flex; flex-wrap: wrap; gap: 10px; }
.pat-abs {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e5e6eb;
  font-size: 12.5px;
  color: #4e5969;
  display: none;
}
.pat-card.open .pat-abs { display: block; }
.pat-abs-fig {
  margin-top: 8px;
  padding: 8px;
  background: #f8fafc;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  text-align: center;
}
.pat-abs-fig img {
  max-width: 100%;
  max-height: 220px;
  object-fit: contain;
  cursor: zoom-in;
  border-radius: 4px;
  background: #fff;
}
.fig-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}
.fig-card {
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  padding: 8px;
  background: #fff;
  text-align: center;
}
.fig-card img {
  max-width: 100%;
  max-height: 220px;
  object-fit: contain;
  cursor: zoom-in;
  border-radius: 4px;
}
.fig-cap { font-size: 12px; color: #4e5969; margin-top: 6px; text-align: left; }
.lightbox {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.88);
  z-index: 999;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 16px;
}
.lightbox.open { display: flex; }
.lightbox img { max-width: 96vw; max-height: 82vh; object-fit: contain; background: #fff; border-radius: 8px; padding: 6px; }
.lightbox-cap { color: #fff; font-size: 13px; margin-top: 10px; max-width: 90vw; text-align: center; }
.btn-link {
  display: inline-block;
  background: #165dff;
  color: #fff;
  text-decoration: none;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}
.pdf-pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: #eff4ff;
  color: #165dff;
  border: 1px solid #94bfff;
  text-decoration: none;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.15s;
}
.pdf-pill:hover {
  background: #165dff;
  color: #fff;
  border-color: #165dff;
}
.sec-text { white-space: pre-line; font-size: 13px; color: #4e5969; line-height: 1.65; }
.bi-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #eff4ff;
  border: 1px solid #b8d4ff;
  border-radius: 10px;
  padding: 7px 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.bi-bar-label { font-size: 12.5px; font-weight: 600; color: #165dff; display: flex; align-items: center; gap: 4px; }
.bi-switch-group { display: flex; gap: 6px; flex-wrap: wrap; }
.bi-btn {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  border: 1px solid #94bfff;
  background: #ffffff;
  color: #165dff;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.15s;
}
.bi-btn.active { background: #165dff; color: #ffffff; border-color: #165dff; }
.bi-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
@media (max-width: 640px) {
  .bi-pair { grid-template-columns: 1fr; }
}
body[data-lang-mode="cn"] .bi-pair,
body[data-lang-mode="orig"] .bi-pair {
  grid-template-columns: 1fr;
}
body[data-lang-mode="cn"] .bi-orig { display: none !important; }
body[data-lang-mode="orig"] .bi-cn { display: none !important; }
.bi-cn {
  background: #f7faff;
  border-left: 3px solid #165dff;
  border-radius: 6px;
  padding: 8px 10px;
}
.bi-orig {
  background: #f8fafc;
  border-left: 3px solid #86909c;
  border-radius: 6px;
  padding: 8px 10px;
}
.bi-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  margin-bottom: 4px;
}
.bi-tag-cn { background: #e8f3ff; color: #165dff; }
.bi-tag-orig { background: #e5e6eb; color: #4e5969; }
.para-pair { margin-bottom: 10px; }
.para-pair:last-child { margin-bottom: 0; }
.src-note {
  font-size: 12px;
  color: #4e5969;
  line-height: 1.6;
  background: #f7f8fa;
  border-left: 3px solid #165dff;
  border-radius: 6px;
  padding: 8px 10px;
  margin: 0 0 10px 0;
}
"""

COMMON_JS = """
function switchTab(group, tabId, btn) {
  document.querySelectorAll('[data-tab-group="' + group + '"]').forEach(function(el) {
    el.classList.remove('active');
  });
  document.querySelectorAll('[data-btn-group="' + group + '"]').forEach(function(el) {
    el.classList.remove('active');
  });
  var target = document.getElementById(tabId);
  if (target) target.classList.add('active');
  if (btn) btn.classList.add('active');
}
function toggleAcc(el) {
  el.parentElement.classList.toggle('open');
}
function filterPatents(statusKey, btn) {
  document.querySelectorAll('.filter-pill').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  document.querySelectorAll('.pat-card').forEach(function(card) {
    if (statusKey === 'all' || card.getAttribute('data-status') === statusKey) {
      card.style.display = 'block';
    } else {
      card.style.display = 'none';
    }
  });
}
function setLangMode(mode, btn) {
  document.body.setAttribute('data-lang-mode', mode);
  document.querySelectorAll('.bi-btn').forEach(function(b) { b.classList.remove('active'); });
  if (btn) btn.classList.add('active');
}
function openLightbox(src, cap) {
  var lb = document.getElementById('lightbox');
  document.getElementById('lb-img').src = src;
  document.getElementById('lb-cap').textContent = cap || '';
  lb.classList.add('open');
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('open');
}
"""


def _split_paragraphs(text: str) -> list:
    """按换行切分段落并去空段（用于段落级中外对照配对）"""
    if not text:
        return []
    parts = [p.strip() for p in str(text).split("\n")]
    return [p for p in parts if p]


def _render_bi_block(
    cn_text: str,
    orig_text: str,
    is_bilingual: bool = False,
    cn_tag: str = "中文",
    orig_tag: str = "原文",
) -> str:
    """渲染中外文双语对照块（若非外文或无译文则渲染普通单语块）

    译文来源统一在各 Tab 顶部的 src-note 提示一次，段内只保留极简的
    「中文 / 原文」语言标识，避免逐段重复来源标注造成噪声。
    当原文与译文段落数一致时，按段逐段配对（段落级对照），否则整块对照。
    """
    orig_s = (orig_text or "").strip()
    cn_s = (cn_text or "").strip()
    if not (is_bilingual and cn_s and cn_s != orig_s):
        return f'<div class="sec-text">{_esc(orig_s or cn_s or "暂无内容")}</div>'

    tag_cn_html = f'<div class="bi-tag bi-tag-cn">{cn_tag}</div>' if cn_tag else ""
    tag_orig_html = f'<div class="bi-tag bi-tag-orig">{orig_tag}</div>' if orig_tag else ""

    cn_paras = _split_paragraphs(cn_s)
    orig_paras = _split_paragraphs(orig_s)
    if len(orig_paras) > 1 and len(cn_paras) == len(orig_paras):
        blocks = []
        for c_p, o_p in zip(cn_paras, orig_paras):
            blocks.append(
                f'<div class="bi-pair para-pair">'
                f'  <div class="bi-cn">'
                f'    {tag_cn_html}'
                f'    <div class="sec-text">{_esc(c_p)}</div>'
                f'  </div>'
                f'  <div class="bi-orig">'
                f'    {tag_orig_html}'
                f'    <div class="sec-text">{_esc(o_p)}</div>'
                f'  </div>'
                f'</div>'
            )
        return "".join(blocks)

    return (
        f'<div class="bi-pair">'
        f'  <div class="bi-cn">'
        f'    {tag_cn_html}'
        f'    <div class="sec-text">{_esc(cn_s)}</div>'
        f'  </div>'
        f'  <div class="bi-orig">'
        f'    {tag_orig_html}'
        f'    <div class="sec-text">{_esc(orig_s or "暂无原文")}</div>'
        f'  </div>'
        f'</div>'
    )


def build_translation_segments(
    pn: str,
    title_str: str,
    abstract_str: str,
    parsed_clms: dict,
) -> list:
    """导出待模型翻译的片段（标题 / 摘要 / 独立权利要求 / 从属权利要求）

    说明书部分不使用本任务，直接采用智慧芽官方机翻（description_translated）。
    id 约定：title、abstract、indep{n}、dep{n}（整段整项，不做二次切分）。
    """
    segs = []
    if title_str:
        segs.append({"id": "title", "section": "专利标题", "text": str(title_str)})
    if abstract_str:
        segs.append({"id": "abstract", "section": "摘要", "text": str(abstract_str)})
    for idx, ic in enumerate((parsed_clms or {}).get("independent") or [], 1):
        if str(ic).strip():
            segs.append({"id": f"indep{idx}", "section": f"独立权利要求#{idx}", "text": str(ic)})
    for idx, dc in enumerate((parsed_clms or {}).get("dependent") or [], 1):
        if str(dc).strip():
            segs.append({"id": f"dep{idx}", "section": f"从属权利要求#{idx}", "text": str(dc)})
    return segs


def render_overview_html(
    query_text: str,
    total_count: int,
    sample_count: int,
    granted_count: int,
    year_counter: dict,
    auth_counter: dict,
    inventor_counter: dict,
    corp_analysis: dict,
    enriched_top: list,
    title_label: str = "专利概览看板",
    summary_text: str = "",
    tech_list: list = None,
    grant_rate_str: str = "",
    raw_rank_list: list = None,
) -> str:
    """生成主体/领域专利概览的单文件交互式 HTML 报告"""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    grouped_corps = (corp_analysis or {}).get("grouped_corporations") or []
    raw_curr = (corp_analysis or {}).get("raw_curr_counter") or {}

    # 1. 年度趋势条形图 HTML
    sorted_years = sorted(year_counter.items(), key=lambda x: x[0], reverse=True)[:8]
    max_yr = max((v for _, v in sorted_years), default=1)
    year_bars_html = []
    for yr, cnt in sorted_years:
        pct = int(round((cnt / max_yr) * 100)) if max_yr else 0
        year_bars_html.append(
            f'<div class="bar-row">'
            f'<div class="bar-label">{_esc(yr)}年</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f'<div class="bar-val">{cnt}件</div>'
            f'</div>'
        )

    # 2. 受理局分布条形图
    sorted_auth = auth_counter.most_common(6) if hasattr(auth_counter, "most_common") else (
        sorted(auth_counter.items(), key=lambda x: x[1], reverse=True)[:6] if isinstance(auth_counter, dict) else []
    )
    max_auth = max((v for _, v in sorted_auth), default=1)
    auth_bars_html = []
    for auth, cnt in sorted_auth:
        pct = int(round((cnt / max_auth) * 100)) if max_auth else 0
        auth_bars_html.append(
            f'<div class="bar-row">'
            f'<div class="bar-label">{_esc(auth)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:#00b42a"></div></div>'
            f'<div class="bar-val">{cnt}件</div>'
            f'</div>'
        )

    # 3. 核心技术领域构成 (IPC) 条形图
    tech_bars_html = []
    lead_ipc_val = ""
    lead_ipc_lbl = ""
    if tech_list:
        max_tech = max((item.get("num", 0) for item in tech_list), default=1)
        lead_ipc = tech_list[0].get("ipc", "")
        lead_cnt = tech_list[0].get("num", 0)
        lead_pct = f"{round(lead_cnt / total_count * 100, 1)}%" if total_count else ""
        lead_ipc_val = f"{lead_ipc} ({lead_pct})"
        lead_ipc_lbl = f"主导技术大类 (全量IPC)"
        for item in tech_list[:8]:
            ipc = item.get("ipc", "")
            cnt = item.get("num", 0)
            desc = item.get("content", "")
            pct = int(round((cnt / max_tech) * 100)) if max_tech else 0
            tech_bars_html.append(
                f'<div class="bar-row">'
                f'<div class="bar-label" style="font-weight:700;color:#165dff">{_esc(ipc)}</div>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:#722ed1"></div></div>'
                f'<div class="bar-val">{cnt}件</div>'
                f'</div>'
                f'<div style="font-size:11.5px;color:#86909c;margin:-2px 0 8px 0;line-height:1.35;">{_esc(desc[:65])}</div>'
            )
    else:
        lead_ipc_val = f"{len(grouped_corps)} 个"
        lead_ipc_lbl = "识别核心集团系"

    # 4. 集团公司树手风琴卡片
    corp_acc_html = []
    for idx, grp in enumerate(grouped_corps[:10], 1):
        open_cls = " open" if idx <= 3 else ""
        tot_num = grp["sum_member_totals"] if grp["member_count"] > 1 else grp["max_domain_total"]
        filing_inst = grp.get("filing_instances", tot_num)
        if filing_inst > tot_num:
            badge_cnt_html = f'<span class="badge badge-valid">全景排重约 {tot_num:,} 件 <small style="font-weight:400;opacity:0.85">(成员累计申报 {filing_inst:,} 件次)</small></span>'
        elif grp["member_count"] > 1 and tot_num != grp.get("primary_domain_total"):
            badge_cnt_html = f'<span class="badge badge-valid">领域约 {tot_num:,} 件次 <small style="font-weight:400;opacity:0.85">(含联合申请)</small></span>'
        else:
            badge_cnt_html = f'<span class="badge badge-valid">领域约 {tot_num:,} 件</span>'

        subs_html = []
        for sub in grp.get("sub_entities", []):
            role_icon = "🏢" if ("核心" in sub["role"] or "母公司" in sub["role"]) else ("🌍" if re.match(r"^[A-Za-z0-9\s.,&-]+$", sub["name"]) else "🔗")
            cnt_txt = f" ({sub['domain_count']}件)" if sub["domain_count"] is not None else (
                f" (抽样{sub['sample_count']}件)" if sub["sample_count"] else ""
            )
            subs_html.append(
                f'<span class="sub-tag">{role_icon} <strong>{_esc(sub["name"])}</strong>{_esc(cnt_txt)} <small style="color:#86909c">[{_esc(sub["role"])}]</small></span>'
            )
        corp_acc_html.append(
            f'<div class="acc-item{open_cls}">'
            f'  <div class="acc-header" onclick="toggleAcc(this)">'
            f'    <div class="acc-title">'
            f'      <span class="badge badge-unknown">#{idx}</span>'
            f'      <span>{_esc(grp["group_label"])}</span>'
            f'      {badge_cnt_html}'
            f'    </div>'
            f'    <span class="acc-arrow">▼</span>'
            f'  </div>'
            f'  <div class="acc-body">'
            f'    <div style="margin-bottom:4px;color:#4e5969;font-weight:600;">智慧芽公司树 (ANCS/ANS) 穿透关联主体明细：</div>'
            f'    <div>{"".join(subs_html)}</div>'
            f'  </div>'
            f'</div>'
        )

    # 5. 官方全量主要申请人或高频列表
    raw_app_rows = []
    if raw_rank_list:
        for item in raw_rank_list[:12]:
            name = item.get("name", "")
            cnt = item.get("num", 0)
            raw_app_rows.append(f'<span class="sub-tag">📌 {_esc(name)} <strong>({cnt}件)</strong></span>')
    elif hasattr(raw_curr, "most_common"):
        for name, cnt in raw_curr.most_common(12):
            raw_app_rows.append(f'<span class="sub-tag">📌 {_esc(name)} <strong>({cnt}件)</strong></span>')

    # 6. 核心发明人
    inv_tags = []
    if hasattr(inventor_counter, "most_common"):
        for name, cnt in inventor_counter.most_common(12):
            inv_tags.append(f'<span class="sub-tag">👤 {_esc(name)} ({cnt}件)</span>')

    # 6. 代表专利卡片（含常驻摘要附图缩略图 + 官方 PDF 一键下载 + 中外文双语对照 + 点击展开完整摘要与大图 + 状态筛选）
    pat_cards_html = []
    for idx, p in enumerate(enriched_top, 1):
        badge_html, status_key = _status_badge(p.get("legal_status", "未知"))
        abs_text = p.get("abstract") or "（点击单篇精读可拉取完整说明书与附图）"
        abs_cn = (p.get("abstract_cn") or "").strip()
        title_orig = (p.get("title") or "").strip()
        title_cn = (p.get("title_cn") or "").strip()
        is_pat_bi = bool((title_cn and title_cn != title_orig) or (abs_cn and abs_cn != abs_text))
        abs_img_url = p.get("abs_img_url") or ""
        pdf_url = p.get("pdf_url") or ""
        open_cls = " open" if idx <= 3 else ""
        disp_title_for_cap = f"{title_cn} ({title_orig})" if (title_cn and title_cn != title_orig) else title_orig
        cap_label = f"#{idx} {p.get('pn')} 《{disp_title_for_cap}》 摘要附图"

        pdf_pill_html = ""
        pdf_btn_html = ""
        if pdf_url:
            pdf_pill_html = (
                f'<a class="pdf-pill" href="{_esc(pdf_url)}" target="_blank" onclick="event.stopPropagation()" title="在新窗口打开/下载官方 PDF 原文">'
                f'📄 官方PDF'
                f'</a>'
            )
            pdf_btn_html = (
                f'<div style="margin-top:8px;text-align:right;">'
                f'  <a class="btn-link" href="{_esc(pdf_url)}" target="_blank" onclick="event.stopPropagation()">📄 查看/下载 { _esc(p.get("pn")) } 官方 PDF 全文</a>'
                f'</div>'
            )

        bi_pill_html = '<span class="badge badge-unknown">🌐 中外对照</span>' if is_pat_bi else ""
        if title_cn and title_cn != title_orig:
            title_block_html = (
                f'<div class="pat-title">🇨🇳 {_esc(title_cn)}'
                f'<div style="font-size:12px;color:#4e5969;font-weight:400;margin-top:2px;">🌐 {_esc(title_orig)}</div>'
                f'</div>'
            )
        else:
            title_block_html = f'<div class="pat-title">{_esc(title_orig)}</div>'

        if abs_cn and abs_cn != abs_text:
            abs_block_html = _render_bi_block(abs_cn, abs_text, True)
        else:
            abs_block_html = f'<div><strong>摘要：</strong>{_esc(abs_text)}</div>'

        thumb_html = ""
        abs_fig_html = ""
        if abs_img_url:
            thumb_html = (
                f'<div class="pat-thumb-box" onclick="event.stopPropagation();openLightbox(\'{_esc(abs_img_url)}\', \'{_esc(cap_label)}\')" title="点击放大查看摘要附图">'
                f'  <img src="{_esc(abs_img_url)}" alt="摘要附图" loading="lazy">'
                f'  <span class="pat-thumb-tag">🔍附图</span>'
                f'</div>'
            )
            abs_fig_html = (
                f'<div class="pat-abs-fig" onclick="event.stopPropagation();openLightbox(\'{_esc(abs_img_url)}\', \'{_esc(cap_label)}\')">'
                f'  <img src="{_esc(abs_img_url)}" alt="摘要附图" loading="lazy">'
                f'  <div style="font-size:11.5px;color:#86909c;margin-top:4px;">🖼️ 摘要附图（点击图片全屏高清放大）</div>'
                f'</div>'
            )

        pat_cards_html.append(
            f'<div class="pat-card{open_cls}" data-status="{status_key}" onclick="this.classList.toggle(\'open\')" style="cursor:pointer">'
            f'  <div class="pat-main-row">'
            f'    <div class="pat-info-col">'
            f'      <div class="pat-top">'
            f'        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
            f'          <span class="pat-num">#{idx} {_esc(p.get("pn"))}</span>'
            f'          {badge_html}'
            f'          {bi_pill_html}'
            f'          {pdf_pill_html}'
            f'        </div>'
            f'      </div>'
            f'      {title_block_html}'
            f'      <div class="pat-meta">'
            f'        <span>🏢 {_esc(p.get("current_assignee") or p.get("original_assignee"))}</span>'
            f'        <span>📅 申请日: {_esc(p.get("apdt"))}</span>'
            f'        <span style="color:#165dff">👉 点击展开/收起摘要与附图</span>'
            f'      </div>'
            f'    </div>'
            f'    {thumb_html}'
            f'  </div>'
            f'  <div class="pat-abs">'
            f'    {abs_block_html}'
            f'    {abs_fig_html}'
            f'    {pdf_btn_html}'
            f'  </div>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title_label)} - 智慧芽专利看板</title>
<style>{COMMON_CSS}</style>
</head>
<body>
<div class="container">
  <div class="hero">
    <div class="hero-tag">智慧芽 PatSnap 移动端交互看板</div>
    <h1>📊 {_esc(title_label)}</h1>
    <div class="hero-meta">
      <span>🔍 检索式: <code>{_esc(query_text)}</code></span>
      <span>🕒 生成时间: {now_str}</span>
    </div>
    {f'<div class="hero-summary">{_esc(summary_text)}</div>' if summary_text else ''}
  </div>

  <div style="background:#eef4ff;border:1px solid #adc6ff;border-radius:10px;padding:9px 12px;margin-bottom:12px;font-size:12px;color:#1d39c4;line-height:1.55;">
    <div style="font-weight:700;margin-bottom:3px;display:flex;align-items:center;gap:4px;">
      <span>📌 数据统计与分析口径声明</span>
    </div>
    <div>• <strong>基准去重总库（{total_count:,} 件）</strong>：当前检索式命中全球唯一专利总量（已剔除跨主体/联合申请重复件），全量趋势、IPC构成、近十年授权率及抽样池均以此为唯一基准。</div>
    <div style="margin-top:2px;">• <strong>穿透微观分析池*（{sample_count} 件）</strong>：基于基准总库按综合权重抽样前 {sample_count} 篇进行多模态附图对齐、代表专利精选及核心团队画像分析（标 * 所示）。</div>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card"><div class="kpi-val">{total_count:,}</div><div class="kpi-lbl">全球检索命中总数</div></div>
    <div class="kpi-card"><div class="kpi-val">{lead_ipc_val}</div><div class="kpi-lbl">{lead_ipc_lbl}</div></div>
    <div class="kpi-card"><div class="kpi-val">{len(grouped_corps)} 个</div><div class="kpi-lbl">穿透核心集团系</div></div>
    {f'<div class="kpi-card"><div class="kpi-val">{grant_rate_str}</div><div class="kpi-lbl">全库近十年授权率</div></div>' if grant_rate_str else f'<div class="kpi-card"><div class="kpi-val">{granted_count}</div><div class="kpi-lbl">抽样含授权(B)数*</div></div>'}
  </div>

  <div class="tabs">
    <button class="tab-btn active" data-btn-group="main" onclick="switchTab('main','tab-corps',this)">🏢 集团与申请人</button>
    <button class="tab-btn" data-btn-group="main" onclick="switchTab('main','tab-patents',this)">📑 代表专利*({len(enriched_top)})</button>
    <button class="tab-btn" data-btn-group="main" onclick="switchTab('main','tab-trends',this)">📈 趋势与领域</button>
  </div>

  <div id="tab-corps" class="tab-panel active" data-tab-group="main">
    <div class="card">
      <div class="card-title">
        <span>🏢 主要申请主体（智慧芽公司树控股归并）</span>
        <small style="font-weight:normal;color:#86909c">点击卡片展开/折叠子公司</small>
      </div>
      {"".join(corp_acc_html) if corp_acc_html else '<div style="color:#86909c">暂无集团归并数据</div>'}
    </div>
    <div class="card">
      <div class="card-title"><span>📌 智慧芽全库主要申请人真实排名（Top 10 全量零抽样）</span></div>
      <div>{"".join(raw_app_rows)}</div>
    </div>
  </div>

  <div id="tab-patents" class="tab-panel" data-tab-group="main">
    <div class="card">
      <div class="card-title">
        <span>📑 核心代表专利精选*（已按申请号去重）</span>
        <small style="font-weight:normal;color:#86909c">点击卡片展开摘要</small>
      </div>
      <div style="font-size:12px;color:#86909c;margin:-4px 0 10px 0;">* 遴选自当前检索高相关专利样本池（Top {sample_count}），优先覆盖各核心集团授权作与高清附图</div>
      <div class="filter-bar">
        <button class="filter-pill active" onclick="filterPatents('all',this)">全部 ({len(enriched_top)})</button>
        <button class="filter-pill" onclick="filterPatents('valid',this)">🟢 仅看有效</button>
        <button class="filter-pill" onclick="filterPatents('pending',this)">🟡 审中/PCT</button>
        <button class="filter-pill" onclick="filterPatents('invalid',this)">⚪ 失效</button>
      </div>
      {"".join(pat_cards_html)}
    </div>
  </div>

  <div id="tab-trends" class="tab-panel" data-tab-group="main">
    <div class="card">
      <div class="card-title"><span>📈 近十年申请趋势与授权统计（官方全量无抽样）</span></div>
      {"".join(year_bars_html)}
    </div>
    {f'''<div class="card">
      <div class="card-title"><span>🧩 核心技术领域构成（官方全量 IPC 分析）</span></div>
      {''.join(tech_bars_html)}
    </div>''' if tech_bars_html else ''}
    <div class="card">
      <div class="card-title"><span>🌍 受理局/国家地区分布（官方全量统计）</span></div>
      {"".join(auth_bars_html)}
    </div>
    <div class="card">
      <div class="card-title"><span>👥 核心发明人团队*（高频研发骨干画像）</span></div>
      <div style="font-size:12px;color:#86909c;margin-bottom:8px;">* 该项基于 Top {sample_count} 高相关代表专利抽样提取，非全量发明人枚举</div>
      <div>{"".join(inv_tags) if inv_tags else '暂无发明人数据'}</div>
    </div>
  </div>
  <div style="margin-top:14px;font-size:11.5px;color:#86909c;text-align:center;line-height:1.6;">
    * 标注项基于 Top {sample_count} 高相关代表专利样本池精选与分析；检索总量、逐年趋势、授权率、IPC 分布及 Top 10 申请人均为智慧芽官方全库全量聚合计算（零抽样偏差）。
  </div>
</div>

<div id="lightbox" class="lightbox" onclick="closeLightbox()">
  <img id="lb-img" src="" alt="放大预览">
  <div id="lb-cap" class="lightbox-cap"></div>
  <div style="color:#86909c;font-size:12px;margin-top:6px;">（点击任意位置关闭预览）</div>
</div>

<script>{COMMON_JS}</script>
</body>
</html>"""


def render_detail_html(
    pn: str,
    apno: str,
    pid: str,
    title_str: str,
    simple_status: str,
    exdt: str,
    assignees: list,
    applicants: list,
    inventors: list,
    apdt: str,
    pbdt: str,
    abstract_str: str,
    abs_img_url: str,
    parsed_clms: dict,
    parsed_desc: dict,
    pdf_url: str = "",
    family_list: list = None,
    citation_list: list = None,
    is_bilingual: bool = False,
    title_cn: str = "",
    abstract_cn: str = "",
    parsed_clms_cn: dict = None,
    parsed_desc_cn: dict = None,
    model_translations: dict = None,
    translator_label: str = "AI 模型",
) -> str:
    """生成单篇专利深度精读的单文件交互式 HTML 报告（含高清附图点击放大画廊与非中文专利中外文双语对照）

    译文来源约定：
    - 标题 / 摘要 / 权利要求：由大模型翻译，标签显示「🇨🇳 模型译文 · {translator_label}」
    - 说明书各章节：直接采用智慧芽官方机翻，标签显示「🇨🇳 智慧芽机翻」
    """
    badge_html, _ = _status_badge(simple_status)
    indep_clms = (parsed_clms or {}).get("independent") or []
    dep_clms = (parsed_clms or {}).get("dependent") or []
    indep_clms_cn = (parsed_clms_cn or {}).get("independent") or []
    dep_clms_cn = (parsed_clms_cn or {}).get("dependent") or []
    paired_figs = (parsed_desc or {}).get("paired_figures") or []
    desc_cn_map = parsed_desc_cn or {}

    # 模型译文覆盖（优先级高于 MCP 返回的中文翻译）
    mt = model_translations or {}
    if mt.get("title"):
        title_cn = mt["title"]
    if mt.get("abstract"):
        abstract_cn = mt["abstract"]
    if mt:
        mt_indep = [mt.get(f"indep{i}", "") for i in range(1, len(indep_clms) + 1)]
        mt_dep = [mt.get(f"dep{i}", "") for i in range(1, len(dep_clms) + 1)]
        if any(mt_indep) or any(mt_dep):
            parsed_clms_cn = {"independent": mt_indep, "dependent": mt_dep}
            indep_clms_cn = mt_indep
            dep_clms_cn = mt_dep

    # 译文来源强约束：
    # - 标题 / 摘要 / 权利要求：严禁使用机翻，必须由大模型翻译，注明「{translator_label} 翻译」；若未翻译则保留原文待模型翻译
    # - 说明书：只允许拉取智慧芽官方机翻，统一注明「智慧芽官方机器翻译」
    label_model = f"{translator_label} 翻译" if translator_label else "AI 模型翻译"
    label_api = "智慧芽官方机器翻译"
    claim_src = label_model if mt else f"外文原文（待 {label_model}）"
    abstract_src = label_model if (mt.get("abstract") or mt.get("title")) else f"外文原文（待 {label_model}）"
    note_summary_html = (
        f'<div class="src-note">📌 译文来源 ｜ 摘要：{abstract_src} ｜ 说明书附图图注：{label_api}</div>'
        if is_bilingual else ""
    )
    note_claims_html = (
        f'<div class="src-note">📌 译文来源 ｜ 权利要求：{claim_src}</div>'
        if is_bilingual else ""
    )
    note_desc_html = (
        f'<div class="src-note">📌 译文来源 ｜ 说明书全文各章节：{label_api}</div>'
        if is_bilingual else ""
    )

    # 独立权利要求（支持中外文对照）
    indep_html = []
    max_indep = max(len(indep_clms), len(indep_clms_cn)) if is_bilingual else len(indep_clms)
    for idx in range(1, max_indep + 1):
        ic_orig = indep_clms[idx - 1] if idx - 1 < len(indep_clms) else ""
        ic_cn = indep_clms_cn[idx - 1] if idx - 1 < len(indep_clms_cn) else ""
        body_html = _render_bi_block(ic_cn, ic_orig, is_bilingual)
        indep_html.append(
            f'<div class="acc-item open">'
            f'  <div class="acc-header" onclick="toggleAcc(this)">'
            f'    <div class="acc-title"><span class="badge badge-unknown">独立权利要求 #{idx}</span></div>'
            f'    <span class="acc-arrow">▼</span>'
            f'  </div>'
            f'  <div class="acc-body">{body_html}</div>'
            f'</div>'
        )

    # 从属权利要求（默认折叠，点击展开，支持逐项中外文对照）
    dep_html = ""
    max_dep = max(len(dep_clms), len(dep_clms_cn)) if is_bilingual else len(dep_clms)
    if max_dep > 0:
        dep_rows = []
        for idx in range(max_dep):
            dc_orig = dep_clms[idx] if idx < len(dep_clms) else ""
            dc_cn = dep_clms_cn[idx] if idx < len(dep_clms_cn) else ""
            dep_rows.append(
                f'<div style="margin-bottom:10px;padding-bottom:10px;border-bottom:1px dashed #e5e6eb">'
                f'{_render_bi_block(dc_cn, dc_orig, is_bilingual)}'
                f'</div>'
            )
        dep_html = (
            f'<div class="acc-item">'
            f'  <div class="acc-header" onclick="toggleAcc(this)">'
            f'    <div class="acc-title"><span class="badge badge-invalid">从属权利要求（共 {max_dep} 项，点击展开全部）</span></div>'
            f'    <span class="acc-arrow">▼</span>'
            f'  </div>'
            f'  <div class="acc-body">{"".join(dep_rows)}</div>'
            f'</div>'
        )

    # 附图画廊（支持中外文图注对照）
    figs_html = []
    if abs_img_url:
        figs_html.append(
            f'<div class="fig-card">'
            f'  <img src="{_esc(abs_img_url)}" alt="摘要附图" onclick="openLightbox(this.src, \'摘要附图\')">'
            f'  <div class="fig-cap"><strong>【摘要附图】</strong>（点击图片全屏放大）</div>'
            f'</div>'
        )
    for fig in paired_figs:
        cap_orig = fig.get("caption", "")
        cap_cn = fig.get("caption_cn", "")
        cap_full = f"{cap_cn} | {cap_orig}" if (is_bilingual and cap_cn and cap_cn != cap_orig) else cap_orig
        cap_js = re.sub(r"['\"\\]", " ", cap_full)
        if is_bilingual and cap_cn and cap_cn != cap_orig:
            fig_cap_html = (
                f'<div class="fig-cap">'
                f'  <div class="bi-cn" style="padding:4px 6px;margin-bottom:4px;"><span class="bi-tag bi-tag-cn">中文</span> {_esc(cap_cn)}</div>'
                f'  <div class="bi-orig" style="padding:4px 6px;"><span class="bi-tag bi-tag-orig">原文</span> {_esc(cap_orig)}</div>'
                f'</div>'
            )
        else:
            fig_cap_html = f'<div class="fig-cap"><strong>{_esc(fig.get("title"))}</strong>：{_esc(cap_orig)}</div>'
        figs_html.append(
            f'<div class="fig-card">'
            f'  <img src="{_esc(fig.get("url"))}" alt="{_esc(fig.get("title"))}" onclick="openLightbox(this.src, \'{_esc(cap_js)}\')">'
            f'  {fig_cap_html}'
            f'</div>'
        )

    pdf_btn = f'<a class="btn-link" href="{_esc(pdf_url)}" target="_blank">📄 下载官方 PDF 全文</a>' if pdf_url else ""

    # 标题与双语切换栏
    bi_hero_badge = '<span class="badge" style="background:rgba(255,255,255,0.22);color:#fff">🌐 中外文对照</span>' if is_bilingual else ""
    if is_bilingual and title_cn and title_cn.strip() != title_str.strip():
        hero_title_html = (
            f'<h1>🇨🇳 {_esc(title_cn)}</h1>'
            f'<div style="font-size:13.5px;opacity:0.92;margin-bottom:8px;font-weight:500;">🌐 原文：{_esc(title_str)}</div>'
        )
        page_title = f"{pn} - {title_cn} ({title_str})"
    else:
        hero_title_html = f'<h1>{_esc(title_str)}</h1>'
        page_title = f"{pn} - {title_str}"

    bi_switch_bar_html = ""
    if is_bilingual:
        bi_switch_bar_html = (
            '<div class="bi-bar">'
            '  <div class="bi-bar-label">🌐 检测到非中文专利，已开启中外文双语对照阅读：</div>'
            '  <div class="bi-switch-group">'
            '    <button class="bi-btn active" onclick="setLangMode(\'both\',this)">🔀 中外对照</button>'
            '    <button class="bi-btn" onclick="setLangMode(\'cn\',this)">🇨🇳 仅看中文</button>'
            '    <button class="bi-btn" onclick="setLangMode(\'orig\',this)">🌐 仅看原文</button>'
            '  </div>'
            '</div>'
        )

    # 说明书各章节中外文拼接
    tf_orig = (parsed_desc or {}).get("technical_field") or ""
    bg_orig = (parsed_desc or {}).get("background") or ""
    full_bg_orig = (f"【技术领域】\n{tf_orig}\n\n【背景技术】\n{bg_orig}".strip() if tf_orig else bg_orig) or "暂无背景技术段落"

    tf_cn = desc_cn_map.get("technical_field") or ""
    bg_cn = desc_cn_map.get("background") or ""
    full_bg_cn = (f"【技术领域】\n{tf_cn}\n\n【背景技术】\n{bg_cn}".strip() if tf_cn else bg_cn)

    sum_orig = (parsed_desc or {}).get("summary") or "暂无发明内容段落"
    sum_cn = desc_cn_map.get("summary") or ""

    emb_orig = ((parsed_desc or {}).get("embodiments") or "暂无具体实施方式")[:8000]
    emb_cn = (desc_cn_map.get("embodiments") or "")[:8000]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(page_title)}</title>
<style>{COMMON_CSS}</style>
</head>
<body data-lang-mode="both">
<div class="container">
  <div class="hero">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:6px;">
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="hero-tag" style="margin-bottom:0">单篇专利精读看板 · {_esc(pn)}</span>
        {bi_hero_badge}
      </div>
      {badge_html}
    </div>
    {hero_title_html}
    <div class="hero-meta">
      <span>🏢 当前权利人: {_esc("、".join(assignees or applicants) or "未知")}</span>
      <span>📅 申请日: {_esc(apdt)}</span>
      <span>📅 公开日: {_esc(pbdt)}</span>
      <span>⏳ 预计到期: {_esc(exdt)}</span>
    </div>
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <span style="font-size:12px;opacity:0.9">👤 发明人: {_esc("、".join(inventors[:8]) or "未知")}</span>
      {pdf_btn}
    </div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" data-btn-group="dt" onclick="switchTab('dt','tab-summary',this)">💡 简述与附图({len(figs_html)})</button>
    <button class="tab-btn" data-btn-group="dt" onclick="switchTab('dt','tab-claims',this)">⚖️ 权利要求</button>
    <button class="tab-btn" data-btn-group="dt" onclick="switchTab('dt','tab-desc',this)">📖 说明书关键段</button>
  </div>

  {bi_switch_bar_html}

  <div id="tab-summary" class="tab-panel active" data-tab-group="dt">
    {note_summary_html}
    <div class="card">
      <div class="card-title"><span>📝 {'专利摘要（中外文对照）' if is_bilingual else '专利摘要原文'}</span></div>
      {_render_bi_block(abstract_cn, abstract_str, is_bilingual)}
    </div>
    <div class="card">
      <div class="card-title">
        <span>🖼️ 摘要附图与配对全文附图画廊</span>
        <small style="font-weight:normal;color:#86909c">点击任意附图可全屏高清放大</small>
      </div>
      <div class="fig-grid">
        {"".join(figs_html) if figs_html else '<div style="color:#86909c">暂无附图数据</div>'}
      </div>
    </div>
  </div>

  <div id="tab-claims" class="tab-panel" data-tab-group="dt">
    {note_claims_html}
    <div class="card">
      <div class="card-title"><span>⚖️ {'独立权利要求与从属权利要求拆解（中外文对照）' if is_bilingual else '独立权利要求与从属权利要求拆解'}</span></div>
      {"".join(indep_html) if indep_html else '<div style="color:#86909c">暂无权利要求文本</div>'}
      {dep_html}
    </div>
  </div>

  <div id="tab-desc" class="tab-panel" data-tab-group="dt">
    {note_desc_html}
    <div class="card">
      <div class="card-title"><span>🎯 {'技术领域与背景技术（中外文对照）' if is_bilingual else '背景技术与行业痛点'}</span></div>
      {_render_bi_block(full_bg_cn, full_bg_orig, is_bilingual)}
    </div>
    <div class="card">
      <div class="card-title"><span>🚀 {'发明内容与有益效果（中外文对照）' if is_bilingual else '发明内容与有益效果'}</span></div>
      {_render_bi_block(sum_cn, sum_orig, is_bilingual)}
    </div>
    <div class="card">
      <div class="card-title"><span>🔧 {'具体实施方式（中外文对照，点击展开/收起）' if is_bilingual else '具体实施方式（全文折叠保护，点击展开）'}</span></div>
      <div class="acc-item open">
        <div class="acc-header" onclick="toggleAcc(this)">
          <div class="acc-title">点击展开/收起【具体实施方式】段落</div>
          <span class="acc-arrow">▼</span>
        </div>
        <div class="acc-body">{_render_bi_block(emb_cn, emb_orig, is_bilingual)}</div>
      </div>
    </div>
  </div>
</div>

<div id="lightbox" class="lightbox" onclick="closeLightbox()">
  <img id="lb-img" src="" alt="放大预览">
  <div id="lb-cap" class="lightbox-cap"></div>
</div>
<script>{COMMON_JS}</script>
</body>
</html>"""
