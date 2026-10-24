#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧芽 (PatSnap / Zhihuiya) MCP 聚合查询与模板管理辅助脚本
专为 WorkBuddy + DeepSeek 4.1 Flash 移动端面谈场景设计
特点：
1. 零第三方依赖（仅使用 Python 标准库）
2. 支持“一句话智能模式”快速检索与预设/自定义模板管理
3. 内置智慧芽公司树 (ANCS/ANS) 控股母子主体穿透识别与归并引擎
4. 并发请求提速、HTML 标签清洗、说明书附图锚点与全文附图链接自动配对
"""

import argparse
import concurrent.futures
import html
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from html_renderer import render_overview_html, render_detail_html, build_translation_segments

# 强制标准输出使用 UTF-8 编码，防止 Windows 终端乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
TEMPLATE_FILE = SKILL_DIR / "config" / "templates.json"

DEFAULT_MCP_URL = os.environ.get(
    "ZHIHUIYA_MCP_URL", "https://connect.zhihuiya.com/1458a4/mcp"
)
DEFAULT_MCP_LANDSCAPE_URL = os.environ.get(
    "ZHIHUIYA_LANDSCAPE_MCP_URL", "https://connect.zhihuiya.com/59100a/mcp"
)
DEFAULT_API_KEY = os.environ.get(
    "ZHIHUIYA_MCP_KEY", "sk-loWNFvv4H51k86i1mESGC7JeUoV9X0IDTDZSUaKPSDSkZb6N"
)

# 官方全景宏观统计工具集（走 59100a 聚合计算中心，实现全量数据库级别零抽样偏差）
LANDSCAPE_TOOLS = {
    "applicant_rank",
    "trend",
    "technology_life_cycle",
    "applicant_technology_analysis",
    "applicant_trend",
    "cooperation_applicant_analysis",
    "tech_applicant_dist",
    "technology_constitute",
    "rec_office",
    "get_rec_office_year",
    "refered_rank",
    "famn_rank",
    "domain_map",
    "map_3d",
    "search_patents_facet",
    "search_patents_statistics",
    "search_patents_v3",
}


def call_mcp_tool(tool_name: str, arguments: dict, timeout: int = 25, endpoint: str = None) -> dict:
    """调用智慧芽 Streamable HTTP MCP 工具（自动根据工具类型智能路由至检索中心 1458a4 或全景统计中心 59100a）"""
    target_url = (
        DEFAULT_MCP_LANDSCAPE_URL
        if (endpoint == "landscape" or tool_name in LANDSCAPE_TOOLS)
        else DEFAULT_MCP_URL
    )
    headers = {
        "Authorization": f"Bearer {DEFAULT_API_KEY}",
        "accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "mcp-protocol-version": "2025-11-25",
        "User-Agent": "WorkBuddy-Zhihuiya-Skill/2.0",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(target_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return {"success": False, "error_msg": f"网络请求失败 ({tool_name}): {e}"}
    except Exception as e:
        return {"success": False, "error_msg": f"调用异常 ({tool_name}): {e}"}

    json_str = ""
    for line in raw_text.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("data:"):
            json_str = line_stripped[5:].strip()
            break
    if not json_str:
        json_str = raw_text.strip()

    try:
        rpc_obj = json.loads(json_str)
        result = rpc_obj.get("result", {})
        if "structuredContent" in result and result["structuredContent"]:
            return result["structuredContent"]
        content_list = result.get("content", [])
        if content_list and isinstance(content_list, list) and "text" in content_list[0]:
            return json.loads(content_list[0]["text"])
        return result
    except Exception as e:
        return {"success": False, "error_msg": f"响应解析失败 ({tool_name}): {e}"}


def load_templates() -> dict:
    """加载预设与自定义模板配置"""
    if not TEMPLATE_FILE.exists():
        return {
            "overview": {"available_modules": {}, "presets": [], "custom_templates": []},
            "detail": {"available_modules": {}, "presets": [], "custom_templates": []},
        }
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_templates(data: dict) -> None:
    """保存模板配置到 JSON 文件"""
    TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_template_by_id(mode: str, template_id: str) -> dict:
    """根据模式和模板 ID 获取模板定义"""
    tpl_data = load_templates().get(mode, {})
    all_tpls = tpl_data.get("presets", []) + tpl_data.get("custom_templates", [])
    for t in all_tpls:
        if str(t.get("id")) == str(template_id) or t.get("name") == template_id:
            return t
    return all_tpls[0] if all_tpls else {"id": "1", "name": "默认模板", "modules": ["A", "B", "D", "E"], "custom_prompt": ""}


def clean_html_text(raw_html: str) -> str:
    """清理专利文本中的 HTML 标签，保留段落换行与段落号"""
    if not raw_html:
        return ""
    text = raw_html
    text = re.sub(r'<b\s+class="d_n"\s*>\s*(\[\d+\])\s*</b>', r"\n\1 ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def is_univ_or_inst(name: str) -> bool:
    """判断是否为高校、科研院所或医院（避免产学研合申将两家独立企业误归并为同一集团）"""
    if any(k in name for k in ["公司", "CO.", "CORP", "INC", "LTD", "株式会社", "集团", "有限", "GMBH", "LLC"]):
        return False
    return bool(
        re.search(
            r"大学|学院|研究所|研究院|实验室|中心|医院|科学院|UNIVERSITY|INSTITUTE|ACADEMY|LABORATORY|COLLEGE|HOSPITAL",
            name,
            re.IGNORECASE,
        )
    )


def is_person_name(name: str) -> bool:
    """简单判断是否为自然人申请人（排除在企业集团树合并之外）"""
    if any(
        k in name.upper()
        for k in [
            "公司", "集团", "有限", "厂", "大学", "学院", "研究", "中心", "局", "院", "所", "部",
            "CO.", "LTD", "INC", "CORP", "LLC", "GMBH", "AG", "BV", "SA", "株式会社", "法人",
            "UNIVERSITY", "INSTITUTE", "TECHNOLOGY", "TECHNOLOGIES", "SYSTEM", "GROUP", "SLEEP",
            "ELECTRIC", "ENERGY", "MOTOR", "BATTERY", "CHEMICAL", "INDUSTRY", "HOLDING",
        ]
    ):
        return False
    # 中文 2~4 字人名，或英文带逗号短人名
    if re.match(r"^[\u4e00-\u9fa5]{2,4}$", name):
        return True
    if "," in name and len(name) <= 25:
        return True
    return False


def extract_core_brand(company_name: str) -> str:
    """从企业全称中提取核心商号/集团简称，用于智慧芽公司树 ANCS/ANS 扩展查询与同集团字号归并"""
    s = company_name.strip()
    # 英文主体保持原样或去掉常见后缀
    if re.match(r"^[A-Za-z0-9\s.,&-]+$", s):
        cleaned = re.sub(
            r"\b(?:INC\.?|LTD\.?|LLC\.?|CORP\.?|CORPORATION|CO\.?|LIMITED|COMPANY|GROUP|HOLDINGS?)\b",
            "",
            s,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[,.]+", " ", cleaned).strip()
        return cleaned if len(cleaned) >= 3 else s

    # 1. 去除中间或末尾的地域括号，如 "(天津)"、"（深圳）"、"(佛山)"
    s = re.sub(r"[\(（][^\)）]{1,8}[\)）]", "", s)
    # 2. 去除常见省市地域前缀（仅当去除后剩余长度 >= 4 时才去除）
    s_no_loc = re.sub(
        r"^(?:中国|北京|上海|天津|重庆|深圳|广州|广东|江苏|浙江|山东|安徽|福建|湖北|湖南|河南|河北|四川|陕西|山西|辽宁|吉林|黑龙江|广西|海南|贵州|云南|江西|苏州|无锡|常州|南京|杭州|宁波|温州|嘉兴|合肥|芜湖|福州|厦门|泉州|济南|青岛|烟台|郑州|武汉|长沙|佛山|东莞|惠州|中山|珠海|南宁|成都|西安|太原|晋城|昆山)(?:市|省)?",
        "",
        s,
    )
    if len(s_no_loc) >= 4:
        s = s_no_loc
    # 3. 去除行业通用词与公司组织形式后缀
    s = re.sub(
        r"(?:控股|集团|科技|数据|创新中心|产业示范基地|产业创新中心|智能制造|制造|新能源|新材料|电子|电器|电气|汽车|动力|电池|实业|信息|技术|智能|发展|工业|精密|机械|材料|设备|半导体|通信|数码|软件|网络|互联网|医疗|生物|医药|设计|研究院|研究|工程|自动化)*(?:股份)?(?:有限)?(?:责任)?公司$|集团$|总公司$|公司$|株式会社$",
        "",
        s,
    )
    return s.strip() if len(s.strip()) >= 2 else company_name.strip()


def expand_keyword_clause(kw: str) -> str:
    """
    针对中文复合领域/产品关键词进行智能拆解与【中英文双语】同义词扩展，
    防止模型未传 --raw-query 时仅查单一中文连续词导致漏检或跑偏。
    """
    w = re.sub(r"(?:技术)?(?:领域|行业|方向|概况|情况|专利|相关)$", "", kw.strip()).strip()
    if not w:
        return ""

    # 常见核心产品中英文双语同义词库
    synonym_map = {
        "猫砂盆": "(猫砂盆 OR 猫厕所 OR 宠物厕所 OR (cat AND litter) OR (pet AND toilet) OR (litter AND box))",
        "猫厕所": "(猫砂盆 OR 猫厕所 OR 宠物厕所 OR (cat AND litter) OR (pet AND toilet) OR (litter AND box))",
        "宠物厕所": "(猫砂盆 OR 猫厕所 OR 宠物厕所 OR (cat AND litter) OR (pet AND toilet) OR (litter AND box))",
        "扫地机器人": "(扫地机器人 OR 清洁机器人 OR 扫拖机器人 OR (robot AND vacuum) OR (cleaning AND robot))",
        "洗地机": "(洗地机 OR 擦地机 OR 地面清洁机 OR (floor AND washer) OR (floor AND scrubber))",
        "床垫": "(床垫 OR 睡眠垫 OR 温控床 OR mattress OR (bed AND pad))",
        "电子烟": "(电子烟 OR 气溶胶生成装置 OR 雾化器 OR (electronic AND cigarette) OR (aerosol AND generating) OR atomizer)",
        "激光雷达": "(激光雷达 OR 光学雷达 OR LIDAR OR (laser AND radar))",
        "固态电池": "(固态电池 OR 固态电解质 OR (solid AND state AND battery) OR (solid AND electrolyte))",
        "固态电解质": "(固态电解质 OR 固体电解质 OR (solid AND electrolyte))",
    }

    # 1. 识别“智能/自动/电动 + 核心产品词”复合结构（如“智能猫砂盆”、“自动喂食器”）
    m_prefix = re.match(r"^(智能|全自动|自动|电动|自清洁|智慧)(.{2,})$", w)
    if m_prefix:
        prefix, core = m_prefix.group(1), m_prefix.group(2).strip()
        if prefix in ("智能", "全自动", "自动", "电动", "自清洁", "智慧"):
            prefix_expr = "(智能 OR 自动 OR 电动 OR 自清洁 OR smart OR intelligent OR automatic OR (self AND cleaning))"
        else:
            prefix_expr = prefix
        core_expr = synonym_map.get(core, core)
        return f"({prefix_expr} AND {core_expr})"

    # 2. 直接命中同义词表
    if w in synonym_map:
        return synonym_map[w]

    # 3. 含常见动作/部位连接词时自动拆分 AND（如“床垫温度调节”）
    for prod_key, prod_syn in synonym_map.items():
        if w.startswith(prod_key) and len(w) > len(prod_key):
            tail = w[len(prod_key):].strip()
            return f"({prod_syn} AND {tail})"

    return w


def build_patsnap_query(company: str = "", keyword: str = "", raw_query: str = "") -> str:
    """根据公司名（启用智慧芽公司树 ANCS/ANS）与产品/领域关键词构造高查准、中英双语 PatSnap 检索式"""
    if raw_query:
        return raw_query.strip()
    parts = []
    if company:
        co = company.strip()
        short_co = extract_core_brand(co)
        def fmt_token(t: str) -> str:
            tokens = [x for x in re.split(r"\s+", t.strip()) if x]
            return " AND ".join(tokens) if len(tokens) > 1 else t.strip()

        co_expr = fmt_token(co)
        if short_co and short_co != co and len(short_co) >= 2:
            short_expr = fmt_token(short_co)
            parts.append(
                f"(ANCS:({co_expr}) OR ANS:({co_expr}) OR ANC:({co_expr}) OR ANCS:({short_expr}) OR ANS:({short_expr}))"
            )
        else:
            parts.append(f"(ANCS:({co_expr}) OR ANS:({co_expr}) OR ANC:({co_expr}))")
    if keyword:
        kws = [k.strip() for k in re.split(r"[,，\s]+", keyword.strip()) if k.strip()]
        expanded_clauses = [expand_keyword_clause(k) for k in kws if expand_keyword_clause(k)]
        # 使用 TAC:（标题/摘要/权利要求）精准锚定核心主题，防止说明书背景偶发词导致结果跑偏
        if len(expanded_clauses) == 1:
            parts.append(f"TAC:({expanded_clauses[0]})")
        elif expanded_clauses:
            joined = " AND ".join(expanded_clauses)
            parts.append(f"TAC:({joined})")
    return " AND ".join(parts) if parts else "TAC:(专利)"


def analyze_corporate_tree_and_applicants(
    sample_results: list, base_query: str, company_filter: str = "", seed_corps: list = None
) -> dict:
    """
    利用智慧芽公司树 (ANCS / ANS) 及权利流转/合申共现关系，
    识别特定领域下的【主要申请人】与【主要申请主体（控股集团/母子公司关系）】
    """
    raw_curr_counter = Counter()
    raw_orig_counter = Counter()
    univ_counter = Counter()
    corp_candidates = Counter()

    # 记录样本内同一专利中共同出现或发生过流转 (orig -> curr) 的企业对
    direct_co_links = {}

    for item in sample_results:
        curr_list = [
            a.strip()
            for a in str(item.get("current_assignee") or "").split("|")
            if a.strip()
        ]
        orig_list = [
            a.strip()
            for a in str(item.get("original_assignee") or "").split("|")
            if a.strip()
        ]
        all_entities = list(dict.fromkeys(curr_list + orig_list))

        for a in curr_list or orig_list:
            raw_curr_counter[a] += 1
            if is_univ_or_inst(a):
                univ_counter[a] += 1
            elif not is_person_name(a):
                corp_candidates[a] += 1

        for a in orig_list:
            raw_orig_counter[a] += 1

        # 同一专利内的多个企业主体（如母子公司合申，或原申请人与现权利人发生集团内转移）
        corp_only = [e for e in all_entities if not is_univ_or_inst(e) and not is_person_name(e)]
        if len(corp_only) > 1:
            for i in range(len(corp_only)):
                for j in range(i + 1, len(corp_only)):
                    u, v = corp_only[i], corp_only[j]
                    direct_co_links.setdefault(u, Counter())[v] += 1
                    direct_co_links.setdefault(v, Counter())[u] += 1

    # 优先注入智慧芽全景统计接口 (applicant_rank) 返回的官方全量真实头部申请人（零抽样误差）
    seed_clean = [
        s.strip() for s in (seed_corps or [])
        if s and s.strip() and not is_univ_or_inst(s) and not is_person_name(s)
    ]
    sample_corps = [name for name, _ in corp_candidates.most_common(20)]
    top_corps = list(dict.fromkeys(seed_clean + sample_corps))[:25]

    def probe_corporate_tree(entity_name: str) -> dict:
        # 构造安全的精确短语查询词（HTTP JSON 直传无需担心 Shell 引号转义，用双引号确保不会因通用英文词误匹配无关企业）
        safe_name = re.sub(r'["\\]', " ", entity_name).strip()
        q_exact = f'"{safe_name}"'

        # 1. 查询智慧芽公司树 ANCS:("entity") 获取该主体的母子公司/英文名/曾用名关联树
        r_tree = call_mcp_tool("search_patents", {"query_text": f"ANCS:({q_exact})", "limit": 30})
        tree_members = Counter()
        for p in (r_tree.get("data") or {}).get("results") or []:
            for field in ("current_assignee", "original_assignee"):
                for a in str(p.get(field) or "").split("|"):
                    a = a.strip()
                    if a and not is_univ_or_inst(a) and not is_person_name(a):
                        tree_members[a] += 1

        # 2. 查询该主体及其公司树在当前领域 (base_query) 下的精确专利量与领域内下属主体
        q_dom = f"({base_query}) AND (ANCS:({q_exact}) OR ANS:({q_exact}) OR ANC:({q_exact}))"
        r_dom = call_mcp_tool("search_patents", {"query_text": q_dom, "limit": 35})
        dom_data = r_dom.get("data") or {}
        dom_total = dom_data.get("total_search_result_count") or 0
        dom_members = Counter()
        for p in dom_data.get("results") or []:
            for field in ("current_assignee", "original_assignee"):
                for a in str(p.get(field) or "").split("|"):
                    a = a.strip()
                    if a and not is_univ_or_inst(a) and not is_person_name(a):
                        dom_members[a] += 1

        return {
            "entity": entity_name,
            "domain_total": dom_total,
            "domain_members": dom_members,
            "tree_members": tree_members,
        }

    probed_list = []
    if top_corps:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            probed_list = list(executor.map(probe_corporate_tree, top_corps))

    # 若某个子公司在 ANCS 公司树中穿透发现了更高频的母公司（不在 top_corps 中），补充探测母公司在该领域的总量
    extra_parents = set()
    probed_names = set(top_corps)
    for info in probed_list:
        ent = info["entity"]
        for rel_name, cnt in info["tree_members"].most_common(5):
            if rel_name != ent and cnt >= 2 and rel_name not in probed_names:
                extra_parents.add(rel_name)

    if extra_parents:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            extra_probed = list(executor.map(probe_corporate_tree, list(extra_parents)[:6]))
            probed_list.extend(extra_probed)
            probed_names.update(x["entity"] for x in extra_probed)

    # 使用并查集 (Union-Find) 将具有明显母子控股/公司树重叠的主体归并为集团系
    parent_map = {info["entity"]: info["entity"] for info in probed_list}

    def find_root(x: str) -> str:
        while parent_map[x] != x:
            parent_map[x] = parent_map[parent_map[x]]
            x = parent_map[x]
        return x

    def union_nodes(a: str, b: str) -> None:
        ra, rb = find_root(a), find_root(b)
        if ra != rb:
            parent_map[rb] = ra

    info_by_name = {info["entity"]: info for info in probed_list}
    all_probed_names = list(info_by_name.keys())

    for i in range(len(all_probed_names)):
        for j in range(i + 1, len(all_probed_names)):
            u, v = all_probed_names[i], all_probed_names[j]
            u_tree = info_by_name[u]["tree_members"]
            v_tree = info_by_name[v]["tree_members"]
            # 条件1：一方在另一方的智慧芽公司树 (ANCS) 中高频共现 (>=2次)，或在样本专利中直接共同申请/流转
            co_linked = direct_co_links.get(u, {}).get(v, 0) >= 1
            # 条件2：核心商号相同或存在明确集团字号包含关系
            brand_u, brand_v = extract_core_brand(u), extract_core_brand(v)
            generic_loc_words = ("中国", "上海", "北京", "深圳", "广东", "广州", "江苏", "浙江", "天津", "杭州", "佛山", "南宁")
            same_brand = (
                len(brand_u) >= 2
                and len(brand_v) >= 2
                and brand_u not in generic_loc_words
                and brand_v not in generic_loc_words
                and (
                    brand_u == brand_v
                    or (len(brand_u) >= 2 and len(brand_v) >= 4 and (brand_u in brand_v))
                    or (len(brand_v) >= 2 and len(brand_u) >= 4 and (brand_v in brand_u))
                )
            )
            if u_tree.get(v, 0) >= 2 or v_tree.get(u, 0) >= 2 or co_linked or same_brand:
                union_nodes(u, v)

    # 聚合每个集团系
    clusters = {}
    for name, info in info_by_name.items():
        root = find_root(name)
        clusters.setdefault(root, []).append(info)

    def _score_as_headquarters(m_info: dict, all_members: list, company_hint: str) -> tuple:
        """
        评估某个成员作为【集团母公司/总部抬头】的优先级：
        优先选择含“集团/股份/控股”、不含地方分支括号(如“(天津)”/“(佛山)”)、且在公司树中高频出现的总部主体，
        避免因某个地方工厂子公司专利量更大而将地方子公司误标为集团母公司。
        """
        ename = m_info["entity"]
        dom_cnt = m_info["domain_total"]
        raw_cnt = raw_curr_counter.get(ename, 0)
        is_en = bool(re.match(r"^[A-Za-z0-9\s.,&-]+$", ename))
        has_branch_paren = bool(re.search(r"[\(（][^\)）]{1,8}[\)）]", ename))
        is_listed_or_group = any(k in ename for k in ("股份", "集团", "控股"))
        # 统计该主体在其他成员的 ANCS 公司树中出现的次数
        tree_presence = sum(1 for other in all_members if other["entity"] != ename and other["tree_members"].get(ename, 0) >= 1)

        hq_score = 0
        if not is_en:
            hq_score += 150  # 优先采用本土中文母公司抬头，避免外文申报主体反客为主
        if raw_cnt > 0:
            hq_score += 80
        if is_listed_or_group:
            hq_score += 200
        if not has_branch_paren:
            hq_score += 80
        else:
            hq_score -= 100
        if len(all_members) > 1 and tree_presence >= max(1, len(all_members) // 2):
            hq_score += 60
        if company_hint:
            clean_hint = re.sub(r"\s+", "", company_hint.strip())
            # 支持简称字集匹配（如“工业富联”4个字全部出现在“富士康工业互联网股份有限公司”中）
            all_chars_in = len(clean_hint) >= 2 and all(c in ename for c in clean_hint)
            if clean_hint and (clean_hint in ename or extract_core_brand(clean_hint) in ename or all_chars_in):
                hq_score += 300 if not has_branch_paren else 100

        return (hq_score, dom_cnt, raw_cnt)

    grouped_corporations = []
    for root, member_infos in clusters.items():
        # 1. 按专利量降序排列所有子主体
        member_infos.sort(key=lambda x: (x["domain_total"], raw_curr_counter.get(x["entity"], 0)), reverse=True)
        max_dom_total = max(m["domain_total"] for m in member_infos)
        top_filer_name = member_infos[0]["entity"]

        # 2. 选出最适合作为【集团总部/母公司抬头】的核心主体 (head_info)
        head_info = max(member_infos, key=lambda x: _score_as_headquarters(x, member_infos, company_filter))
        primary_name = head_info["entity"]
        primary_dom_total = head_info["domain_total"]
        brand_label = extract_core_brand(primary_name)
        if company_filter:
            cf = company_filter.strip()
            if len(cf) >= 2 and all(c in primary_name for c in cf):
                brand_label = cf

        # 将集团母公司排在列表第一位，直属申请子公司（样本内高频出现）排在前面，外部母集团关联方排在后面
        other_members = [m for m in member_infos if m["entity"] != primary_name]
        other_members.sort(
            key=lambda x: (1 if raw_curr_counter.get(x["entity"], 0) > 0 else 0, x["domain_total"], raw_curr_counter.get(x["entity"], 0)),
            reverse=True,
        )
        ordered_members = [head_info] + other_members

        # 汇总该集团系在当前领域下的所有具体申请主体及关联主体
        sub_entities = []
        seen_subs = set()
        for m_info in ordered_members:
            m_name = m_info["entity"]
            m_dom = m_info["domain_total"]
            m_raw = raw_curr_counter.get(m_name, 0)
            if m_name not in seen_subs:
                seen_subs.add(m_name)
                if m_name == primary_name:
                    if len(member_infos) > 1 and m_name != top_filer_name:
                        role_str = "集团母公司/上市主体"
                    else:
                        role_str = "核心母公司/主力主体"
                elif re.match(r"^[A-Za-z0-9\s.,&-]+$", m_name):
                    role_str = "海外/英文申请主体"
                elif m_raw == 0:
                    role_str = "上级控股母集团/关联方"
                elif m_dom >= max(10, int(max_dom_total * 0.25)):
                    role_str = "主力研发/申请子公司"
                else:
                    role_str = "控股/关联申请子公司"

                sub_entities.append({
                    "name": m_name,
                    "domain_count": m_dom,
                    "sample_count": m_raw,
                    "role": role_str,
                })

        # 补充从 domain_members 和 tree_members 中识别到的同集团其他子公司/外文主体
        for m_info in ordered_members:
            for sub_name, cnt in m_info["domain_members"].most_common(6):
                if sub_name not in seen_subs and cnt >= 1:
                    if m_info["tree_members"].get(sub_name, 0) >= 2 or extract_core_brand(sub_name) == brand_label:
                        seen_subs.add(sub_name)
                        sub_entities.append({
                            "name": sub_name,
                            "domain_count": None,
                            "sample_count": cnt,
                            "role": "海外/英文申请主体" if re.match(r"^[A-Za-z0-9\s.,&-]+$", sub_name) else "领域内关联/下属申请主体",
                        })
            for sub_name, cnt in m_info["tree_members"].most_common(5):
                if sub_name not in seen_subs and cnt >= 2:
                    seen_subs.add(sub_name)
                    sub_entities.append({
                        "name": sub_name,
                        "domain_count": None,
                        "sample_count": 0,
                        "role": "海外/英文申请主体" if re.match(r"^[A-Za-z0-9\s.,&-]+$", sub_name) else "智慧芽公司树关联主体",
                    })

        sum_distinct_subs = sum(m["domain_total"] for m in member_infos)
        grouped_corporations.append({
            "group_label": f"{brand_label}系（{primary_name}）" if brand_label != primary_name else primary_name,
            "primary_entity": primary_name,
            "primary_domain_total": primary_dom_total,
            "max_domain_total": max_dom_total,
            "sum_member_totals": sum_distinct_subs if len(member_infos) > 1 else max_dom_total,
            "member_count": len(member_infos),
            "sub_entities": sub_entities[:10],
        })

    # 按集团在当前领域的专利规模降序排列
    grouped_corporations.sort(
        key=lambda g: (g["sum_member_totals"], g["max_domain_total"]), reverse=True
    )

    return {
        "sample_size": len(sample_results),
        "raw_curr_counter": raw_curr_counter,
        "univ_counter": univ_counter,
        "grouped_corporations": grouped_corporations,
    }


def parse_claims_structured(raw_claim_html: str) -> dict:
    """解析权利要求 HTML，分离独立权利要求 (indep-clm) 与从属权利要求 (dep-clm)"""
    if not raw_claim_html:
        return {"independent": [], "dependent": []}

    indep_map = {}
    dep_map = {}

    pattern = re.compile(
        r'<div\s+class="(indep-clm|dep-clm)"\s+num="(\d+)"(?:\s+parent="([^"]*)")?\s*>(.*?)</div>',
        re.DOTALL,
    )
    matches = pattern.findall(raw_claim_html)
    if not matches:
        cleaned = clean_html_text(raw_claim_html)
        return {"independent": [cleaned], "dependent": []}

    for clm_type, num_str, parent_str, inner_html in matches:
        num = int(num_str)
        seg_text = clean_html_text(inner_html)
        if clm_type == "indep-clm":
            indep_map.setdefault(num, []).append(seg_text)
        else:
            dep_map.setdefault(num, []).append(seg_text)

    indep_list = ["\n".join(parts) for _, parts in sorted(indep_map.items())]
    dep_list = ["\n".join(parts) for _, parts in sorted(dep_map.items())]
    return {"independent": indep_list, "dependent": dep_list}


def is_non_chinese_text(text: str) -> bool:
    """判断文本是否为非中文（如英文、日文、德文、韩文等），需要提供中外文对照"""
    if not text or not str(text).strip():
        return False
    s = str(text).strip()
    # 含有日文平假名/片假名或韩文谚文，判定为非中文
    if re.search(r"[\u3040-\u30ff\uac00-\ud7af]", s):
        return True
    cjk_count = len(re.findall(r"[\u4e00-\u9fa5]", s))
    alpha_num_cjk = len(re.sub(r"[\s\d\W_]", "", s))
    if alpha_num_cjk == 0:
        return False
    return (cjk_count / alpha_num_cjk) < 0.2


def extract_fig_captions_from_text(drawing_desc_text: str) -> list:
    """从附图说明段落纯文本中按序提取各附图的图注行（兼容 FIG. 1 / Figure 1 / 图1）"""
    if not drawing_desc_text:
        return []
    captions = []
    fig_line_pat = re.compile(
        r"(?:\[\d+\]\s*)?((?:FIG(?:URE)?S?\.?\s*\d+[A-Za-z0-9()-]*|图\s*\d+[A-Za-z0-9()-]*|附图\s*\d+[A-Za-z0-9()-]*)[^\n；;。]*)",
        re.IGNORECASE,
    )
    for line in drawing_desc_text.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        m = fig_line_pat.search(line_s)
        if m:
            cap = m.group(1).strip(" ；;。，,")
            if len(cap) >= 4:
                captions.append(cap)
    return captions


def parse_description_and_figures(raw_desc_html: str, fulltext_images: list) -> dict:
    """
    解析说明书章节（技术领域、背景技术、发明内容、附图说明、具体实施方式）
    并将 <a class="see-img-anchor" img-id="..." img-title="图1A"> 与全文附图 URL 自动配对
    """
    result = {
        "technical_field": "",
        "background": "",
        "summary": "",
        "drawing_desc": "",
        "embodiments": "",
        "paired_figures": [],
    }
    if not raw_desc_html:
        return result

    img_url_map = {}
    ordered_urls = []
    for item in fulltext_images or []:
        url = item.get("path", "")
        if not url:
            continue
        ordered_urls.append(url)
        m = re.search(r"/([^/?]+)\.(?:png|jpg|jpeg|gif|tif|webp)", url, re.IGNORECASE)
        if m:
            img_url_map[m.group(1)] = url

    anchor_pattern = re.compile(
        r'<a\s+[^>]*img-id="([^"]+)"[^>]*img-title="([^"]+)"[^>]*>.*?</a>([^<\n]*)',
        re.DOTALL,
    )
    draw_sec_match = re.search(
        r"(?:附图说明|附图简述|【附图说明】|BRIEF DESCRIPTION OF (?:THE )?DRAWINGS)(.*?)(?:具体实施方式|实施例|【具体实施方式】|DETAILED DESCRIPTION|EMBODIMENTS|$)",
        raw_desc_html,
        re.DOTALL | re.IGNORECASE,
    )
    search_blocks = [draw_sec_match.group(1), raw_desc_html] if draw_sec_match else [raw_desc_html]

    seen_img_ids = set()
    for block in search_blocks:
        for img_ids_str, img_titles_str, caption_tail in anchor_pattern.findall(block):
            img_ids = [x.strip() for x in img_ids_str.split(",") if x.strip()]
            img_titles = [x.strip() for x in img_titles_str.split(",") if x.strip()]
            clean_tail = html.unescape(caption_tail).strip(" ；;。，,")
            for idx, img_id in enumerate(img_ids):
                if img_id in seen_img_ids:
                    continue
                title = img_titles[idx] if idx < len(img_titles) else img_titles[-1]
                url = img_url_map.get(img_id)
                if url:
                    seen_img_ids.add(img_id)
                    result["paired_figures"].append({
                        "img_id": img_id,
                        "title": title,
                        "caption": f"{title}{clean_tail}" if clean_tail else title,
                        "url": url,
                    })

    cleaned_full = clean_html_text(raw_desc_html)
    section_headers = [
        ("technical_field", r"^(?:技术领域|发明领域|【技术领域】|\[技术领域\]|TECHNICAL FIELD|FIELD OF THE INVENTION|FIELD)"),
        ("background", r"^(?:背景技术|发明背景|【背景技术】|\[背景技术\]|BACKGROUND|BACKGROUND TECHNOLOGY|BACKGROUND OF THE INVENTION)"),
        ("summary", r"^(?:发明内容|发明概述|实用新型内容|发明摘要|【发明内容】|【实用新型内容】|SUMMARY|SUMMARY OF THE INVENTION)"),
        ("drawing_desc", r"^(?:附图说明|附图简述|附图简要说明|【附图说明】|\[附图说明\]|BRIEF DESCRIPTION OF THE DRAWINGS|BRIEF DESCRIPTION OF DRAWINGS|DESCRIPTION OF THE DRAWINGS)"),
        ("embodiments", r"^(?:具体实施方式|实施例|发明详述|详细描述|具体实施例|【具体实施方式】|\[具体实施方式\]|DETAILED DESCRIPTION|EMBODIMENTS|DESCRIPTION OF EMBODIMENTS)"),
    ]

    current_key = "summary"
    buffers = {k: [] for k, _ in section_headers}
    for line in cleaned_full.splitlines():
        matched_header = False
        for key, regex in section_headers:
            if re.match(regex, line.strip(), re.IGNORECASE):
                current_key = key
                matched_header = True
                break
        if not matched_header:
            buffers[current_key].append(line)

    for key, lines in buffers.items():
        result[key] = "\n".join(lines).strip()

    # 若原文无 <a img-id="..."> 锚点（常见于 US/EP/WO 等外文专利），按序关联附图说明中的图注行
    if not result["paired_figures"] and ordered_urls:
        extracted_caps = extract_fig_captions_from_text(result["drawing_desc"])
        for i, url in enumerate(ordered_urls, 1):
            cap_text = extracted_caps[i - 1] if i - 1 < len(extracted_caps) else f"全文附图 {i}"
            result["paired_figures"].append({
                "img_id": f"FIG_{i}",
                "title": f"附图{i}",
                "caption": cap_text,
                "url": url,
            })

    return result


def cmd_menu(args: argparse.Namespace) -> None:
    """输出预设模板与自定义模板选择菜单"""
    tpl_data = load_templates()
    mode = args.mode
    mode_cfg = tpl_data.get(mode, {})
    mode_title = "主体/领域专利概览" if mode == "overview" else "单篇专利深度精读"

    if args.builder:
        print(f"### 🛠 新建/自定义【{mode_title}】模板")
        print("请从以下可用信息模块中选择（可多选，如回复 `A,B,D,E`），并可直接用自然语言补充你关注的重点：\n")
        print("| 模块代号 | 模块名称 | 包含内容说明 |")
        print("| :--- | :--- | :--- |")
        for code, info in mode_cfg.get("available_modules", {}).items():
            print(f"| **{code}** | {info['name']} | {info['description']} |")
        print("\n**操作示例**：")
        print("- 仅本次使用：回复 `模块 A,B,D,E + 重点看近两年授权专利`")
        print("- 保存为常用模板：回复 `保存模板：名称=行业玩家穿透版，模块=A,B,D,F，关注=重点用公司树识别主要申请人与母子集团控股关系`")
        return

    print(f"### 📋 请选择【{mode_title}】输出模板")
    print("（手机端直接回复对应**数字**即可，也可回复 `数字 + 额外关注点`）：\n")
    for p in mode_cfg.get("presets", []):
        mods = ",".join(p.get("modules", []))
        print(f"- **[{p['id']}] {p['name']}** *(包含模块: {mods})*")
    for c in mode_cfg.get("custom_templates", []):
        mods = ",".join(c.get("modules", []))
        print(f"- **[{c['id']}] {c['name']} [自定义]** *(包含模块: {mods} | 关注: {c.get('custom_prompt', '无')})*")
    print("- **[0] ➕ 新增/自定义模板** *(自由勾选关注的模块 + 自然语言定制关注点)*")


def cmd_template(args: argparse.Namespace) -> None:
    """管理自定义模板（列表、新增、删除）"""
    tpl_data = load_templates()
    mode = args.mode
    if mode not in tpl_data:
        print(f"错误：未知模式 {mode}")
        sys.exit(1)

    mode_cfg = tpl_data[mode]
    if args.action == "list":
        cmd_menu(argparse.Namespace(mode=mode, builder=False))
        return

    if args.action == "add":
        presets = mode_cfg.get("presets", [])
        customs = mode_cfg.get("custom_templates", [])
        existing_ids = [int(t["id"]) for t in (presets + customs) if str(t.get("id", "")).isdigit()]
        next_id = str(max(existing_ids, default=3) + 1)
        modules = [m.strip().upper() for m in (args.modules or "A,B,D").split(",") if m.strip()]
        new_tpl = {
            "id": next_id,
            "name": args.name or f"自定义模板{next_id}",
            "modules": modules,
            "custom_prompt": args.prompt or "",
        }
        customs.append(new_tpl)
        mode_cfg["custom_templates"] = customs
        save_templates(tpl_data)
        print(f"✅ 已成功保存自定义模板：**[{next_id}] {new_tpl['name']}**")
        print(f"- 适用场景：`{mode}`")
        print(f"- 包含模块：`{','.join(modules)}`")
        print(f"- 定制关注点：`{new_tpl['custom_prompt'] or '无'}`")
        return

    if args.action == "delete":
        customs = mode_cfg.get("custom_templates", [])
        before_len = len(customs)
        customs = [c for c in customs if str(c.get("id")) != str(args.id) and c.get("name") != args.id]
        mode_cfg["custom_templates"] = customs
        save_templates(tpl_data)
        if len(customs) < before_len:
            print(f"✅ 已删除自定义模板 `{args.id}`")
        else:
            print(f"⚠️ 未找到 ID 或名称为 `{args.id}` 的自定义模板（预设模板不可删除）")


def cmd_overview(args: argparse.Namespace) -> None:
    """执行公司/产品/领域专利概览聚合查询（支持智慧芽公司树控股主体穿透识别）"""
    tpl = get_template_by_id("overview", args.template)
    modules = set(tpl.get("modules", ["A", "B", "D", "E", "C"]))
    if args.modules:
        modules = set(m.strip().upper() for m in args.modules.split(",") if m.strip())

    query_text = build_patsnap_query(args.company, args.keyword, args.raw_query)
    # 若激活模块 B（主要申请人与集团控股主体识别），拉取 100~200 件样本以提高行业玩家覆盖度
    first_batch_size = 100 if "B" in modules else max(args.limit * 2, 30)

    # 并发发起检索与智慧芽官方全量宏观统计 (trend / applicant_rank / technology_constitute / rec_office)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        f_search = executor.submit(
            call_mcp_tool,
            "search_patents",
            {
                "query_text": query_text,
                "limit": first_batch_size,
                "offset": 0,
                "sort_field": "SCORE",
                "sort_order": "DESC",
                "collapse_by": "PBD",
            },
        )
        f_trend = executor.submit(call_mcp_tool, "trend", {"query_text": query_text})
        f_rank = executor.submit(call_mcp_tool, "applicant_rank", {"query_text": query_text})
        f_tech = executor.submit(call_mcp_tool, "technology_constitute", {"query_text": query_text})
        f_office = executor.submit(call_mcp_tool, "rec_office", {"query_text": query_text})

        search_res = f_search.result()
        trend_res = f_trend.result()
        rank_res = f_rank.result()
        tech_res = f_tech.result()
        office_res = f_office.result()

    if not search_res.get("success"):
        print(f"❌ 检索失败：{search_res.get('error_msg', '未知错误')}")
        print(f"- 检索式：`{query_text}`")
        sys.exit(1)

    data = search_res.get("data", {})
    total_count = data.get("total_search_result_count", 0)
    results = list(data.get("results", []))

    # 解析官方全景宏观统计结果（100% 数据库级别零抽样偏差）
    trend_values = (trend_res.get("data") or {}).get("values") or []
    rank_values = (rank_res.get("data") or {}).get("values") or []
    tech_values = (tech_res.get("data") or {}).get("values") or []
    office_values = (office_res.get("data") or {}).get("values") or []

    seed_corps = [item["name"] for item in rank_values if item.get("name")]

    exact_year_counts = {}
    total_10yr_grants = 0
    total_10yr_apps = 0
    for item in trend_values:
        yr = str(item.get("year", ""))
        tot = item.get("total", 0)
        g_num = item.get("grant_num", 0)
        if yr:
            exact_year_counts[yr] = tot
            total_10yr_apps += tot
            total_10yr_grants += g_num
    grant_rate_str = f"{round(total_10yr_grants / total_10yr_apps * 100, 1)}%" if total_10yr_apps else ""

    # 若激活了模块 B 且命中总量超过 100 件，并发追加第 2 页 (100~200) 样本以全面覆盖主要申请人
    if "B" in modules and total_count > 100 and len(results) >= 100:
        page2_res = call_mcp_tool(
            "search_patents",
            {
                "query_text": query_text,
                "limit": 100,
                "offset": 100,
                "sort_field": "SCORE",
                "sort_order": "DESC",
                "collapse_by": "PBD",
            },
        )
        if page2_res.get("success"):
            results.extend((page2_res.get("data") or {}).get("results") or [])

    # 1. 按申请号 apno 去重（同一申请号若同时存在公开A与授权B，优先保留授权版本）
    # 2. 对同一申请人同一申请日（同日发明+实用新型双申或同日连号群申）优先保留授权(B/U)版本
    dedup_map = {}
    dedup_order = []
    for item in results:
        apno = item.get("apno") or item.get("pn") or item.get("patent_id")
        pn = str(item.get("pn", ""))
        is_granted = pn.endswith(("B", "B1", "B2", "C", "U", "Y"))
        if apno not in dedup_map:
            dedup_map[apno] = item
            dedup_order.append(apno)
        elif is_granted:
            dedup_map[apno] = item
    unique_results = [dedup_map[k] for k in dedup_order]

    print(f"# 📊 智慧芽专利概览数据包")
    print(f"- **执行检索式**：`{query_text}`")
    print(f"- **选用模板**：`[{tpl.get('id')}] {tpl.get('name')}` (激活模块: `{','.join(sorted(modules))}`)")
    if args.extra_prompt or tpl.get("custom_prompt"):
        print(f"- **模板分析要求**：{tpl.get('custom_prompt', '')} {args.extra_prompt or ''}")
    print(f"- **全球命中专利总数**：**{total_count}** 件（当前抽样分析前 {len(results)} 件高相关专利）\n")

    if not results:
        print("⚠️ 未检索到匹配的专利，请尝试放宽关键词或检查公司/产品名称。")
        return

    year_counter = Counter()
    inventor_counter = Counter()
    auth_counter = Counter()
    granted_count = 0

    for item in results:
        apdt = str(item.get("apdt", ""))
        if len(apdt) >= 4:
            year_counter[apdt[:4]] += 1
        inv = item.get("inventor") or ""
        for iv in str(inv).split("|"):
            if iv.strip():
                inventor_counter[iv.strip()] += 1
        auth = item.get("authority") or "未知"
        auth_counter[auth] += 1
        pn = str(item.get("pn", ""))
        if pn.endswith(("B", "B1", "B2", "C")):
            granted_count += 1

    # 优先采用官方全景统计的受理局分布
    if office_values:
        auth_counter = Counter({(item.get("code") or item.get("rec_office")): item.get("num", 0) for item in office_values})

    # 优先采用官方全量近 10 年申请趋势
    display_year_counter = exact_year_counts if exact_year_counts else year_counter

    if "A" in modules:
        print("## [模块 A] 专利总量与申请趋势（智慧芽官方全量统计·零抽样偏差）")
        print(f"- **全库命中专利总量**：**{total_count}** 件")
        if grant_rate_str:
            print(f"- **近十年全库授权统计**：累计授权 **{total_10yr_grants:,}** 件 / 申请 **{total_10yr_apps:,}** 件（**官方全量授权率 {grant_rate_str}**）")
        else:
            print(f"- **抽样授权占比**：抽样 {len(results)} 件中含授权公告号（B/B1/B2）约 {granted_count} 件")
        years_str = " | ".join(
            f"{yr}年: {cnt}件" for yr, cnt in sorted(display_year_counter.items(), key=lambda x: str(x[0]), reverse=True)[:8]
        )
        print(f"- **近十年全量申请趋势**：{years_str or '暂无'}\n")

    if "B" in modules:
        print("## [模块 B] 主要申请人与主要申请主体识别（智慧芽全量排行 + 公司树控股穿透）")
        corp_analysis = analyze_corporate_tree_and_applicants(results, query_text, args.company, seed_corps=seed_corps)
        grouped_corps = corp_analysis["grouped_corporations"]

        if grouped_corps:
            print("### 1. 主要申请主体矩阵表（按集团控股/智慧芽公司树 `ANCS/ANS` 穿透归并）")
            print("| 排名 | 集团系 (领域全口径) | 🏢 核心申请主体 (母公司) | 🔗 智慧芽公司树穿透：控股子公司 / 海外 / 关联主体 |")
            print("| :--- | :--- | :--- | :--- |")
            for idx, grp in enumerate(grouped_corps[:8], 1):
                tot_num = grp["sum_member_totals"] if grp["member_count"] > 1 else grp["max_domain_total"]
                core_ent = grp["primary_entity"]
                other_subs = []
                for sub in grp["sub_entities"]:
                    if sub["name"] == core_ent:
                        continue
                    icon = "🌍" if re.match(r"^[A-Za-z0-9\s.,&-]+$", sub["name"]) else "🔗"
                    cnt_s = f"({sub['domain_count']}件)" if sub["domain_count"] is not None else (
                        f"(抽样{sub['sample_count']}件)" if sub["sample_count"] else ""
                    )
                    other_subs.append(f"{icon}`{sub['name']}`{cnt_s}")
                subs_col = " 、 ".join(other_subs) if other_subs else "单一核心主体直接申请"
                prim_cnt = grp.get("primary_domain_total", grp["max_domain_total"])
                print(f"| **#{idx}** | **{grp['group_label']}** (`{tot_num}件`) | `{core_ent}` (`{prim_cnt}件`) | {subs_col} |")
            print()

        if rank_values:
            print("### 2. 智慧芽全库主要申请人真实排名（Top 10 全量零抽样）")
            top_rank_str = " | ".join(f"**{item['name']}** ({item['num']}件)" for item in rank_values[:10])
            print(f"- {top_rank_str}\n")
        else:
            print(f"### 2. 具体申请人原始高频分布（Top {corp_analysis['sample_size']} 样本）")
            top_raw_str = " | ".join(
                f"**{name}** ({cnt}件)" for name, cnt in corp_analysis["raw_curr_counter"].most_common(10)
            )
            print(f"- {top_raw_str}\n")
    else:
        corp_analysis = {"grouped_corporations": [], "raw_curr_counter": Counter(), "sample_size": len(results)}

    if "E" in modules and tech_values:
        print("## [模块 E] 核心技术分类与布局构成（智慧芽官方全量 IPC 分析）")
        print("| IPC分类 | 全球专利量 | 技术领域说明 |")
        print("| :--- | :--- | :--- |")
        for t_item in tech_values[:6]:
            ipc_code = t_item.get("ipc", "")
            ipc_num = t_item.get("num", 0)
            ipc_desc = (t_item.get("content") or "").replace("\n", " ").strip()[:50]
            print(f"| **{ipc_code}** | `{ipc_num}件` | {ipc_desc} |")
        print()
    else:
        corp_analysis = {"grouped_corporations": [], "raw_curr_counter": Counter(), "sample_size": len(results)}

    if "C" in modules:
        print(f"## [模块 C] 核心发明人团队*（基于 Top {len(results)} 高相关专利样本抽样画像）")
        top_invs = [f"**{name}** ({cnt}件*)" for name, cnt in inventor_counter.most_common(10)]
        print("- " + ("、".join(top_invs) if top_invs else "暂无发明人数据"))
        print("- *注：智慧芽未开放全库发明人排行接口，该项基于当前高相关代表专利抽样提取，非全库全量枚举\n")

    if "F" in modules:
        print("## [模块 F] 受理局与区域分布（官方全量统计）")
        auth_str = " | ".join(f"{k}: {v}件" for k, v in auth_counter.most_common(8))
        print(f"- **受理局分布**：{auth_str}\n")

    # 3. 代表专利多样性与头部集团联动遴选：
    # - 优先确保前 4 大头部集团各有 1 篇代表作（优先选授权 B/U 专利）入选
    # - 限制单一申请人在 Top N 中最多入选 2 篇，同日连号/双申最多入选 1 篇，防止单一主体刷屏霸榜
    top_patents = []
    selected_pns = set()
    seen_assignee_date = set()
    assignee_quota = Counter()
    max_per_assignee = args.limit if args.company else 2

    if not args.company and corp_analysis.get("grouped_corporations"):
        for grp in corp_analysis["grouped_corporations"][:4]:
            grp_members = {s["name"] for s in grp.get("sub_entities", [])}
            grp_members.add(grp.get("primary_entity", ""))
            # 在 unique_results 中寻找属于该集团的专利（优先授权版 B/U）
            grp_candidates = []
            for item in unique_results:
                ass_all = f"{item.get('current_assignee', '')}|{item.get('original_assignee', '')}"
                if any(m and m in ass_all for m in grp_members):
                    grp_candidates.append(item)
            if grp_candidates:
                grp_candidates.sort(
                    key=lambda x: (
                        1 if str(x.get("apdt", "")) >= "20160101" else 0,
                        1 if str(x.get("pn", "")).endswith(("B", "B1", "B2", "U")) else 0,
                    ),
                    reverse=True,
                )
                best_item = grp_candidates[0]
                pn_k = best_item.get("pn") or best_item.get("patent_id")
                assignee = str(best_item.get("current_assignee") or best_item.get("original_assignee") or "未知").split("|")[0].strip()
                apdt = str(best_item.get("apdt") or "")
                selected_pns.add(pn_k)
                seen_assignee_date.add((assignee, apdt))
                assignee_quota[assignee] += 1
                top_patents.append(best_item)

    remainder_pool = []
    for item in unique_results:
        if len(top_patents) >= args.limit:
            break
        pn_k = item.get("pn") or item.get("patent_id")
        if pn_k in selected_pns:
            continue
        assignee = str(item.get("current_assignee") or item.get("original_assignee") or "未知").split("|")[0].strip()
        apdt = str(item.get("apdt") or "")
        ad_key = (assignee, apdt)
        # 优先遴选 2016 年及以后的近十年专利，避免 20 年前已过期的远古失效专利挤占 Top 8
        if apdt < "20160101" or ad_key in seen_assignee_date or assignee_quota[assignee] >= max_per_assignee:
            remainder_pool.append(item)
            continue
        selected_pns.add(pn_k)
        seen_assignee_date.add(ad_key)
        assignee_quota[assignee] += 1
        top_patents.append(item)

    if len(top_patents) < args.limit:
        for item in remainder_pool:
            if len(top_patents) >= args.limit:
                break
            pn_k = item.get("pn") or item.get("patent_id")
            if pn_k not in selected_pns:
                selected_pns.add(pn_k)
                top_patents.append(item)

    def enrich_patent(p_item: dict) -> dict:
        pid = p_item.get("patent_id")
        enriched = dict(p_item)
        status_res = call_mcp_tool("get_patent_legal_status", {"patent_id": pid})
        if status_res.get("success") and status_res.get("data"):
            statuses = status_res["data"][0].get("simple_legal_status", [])
            enriched["legal_status"] = "/".join(statuses) if statuses else "未知"
        else:
            enriched["legal_status"] = "未知"

        bib_res = call_mcp_tool("bibliography", {"patent_id": pid})
        if bib_res.get("success") and bib_res.get("data"):
            bib_data = bib_res["data"][0].get("bibliographic_data", {})
            abs_list = bib_data.get("abstracts", [])
            if isinstance(abs_list, dict):
                abs_list = [abs_list]
            if abs_list:
                enriched["abstract"] = clean_html_text(abs_list[0].get("text", ""))

        # 获取代表专利的摘要附图（若无独立摘要附图则自动回退取第1幅全文附图）
        abs_img_url = ""
        abs_img_res = call_mcp_tool("abstract_image", {"patent_id": pid})
        if abs_img_res.get("success") and abs_img_res.get("data"):
            drawing = abs_img_res["data"][0].get("abstract_drawing", {})
            if isinstance(drawing, dict):
                abs_img_url = drawing.get("path") or ""
        if not abs_img_url:
            ft_res = call_mcp_tool("fulltext_image", {"patent_id": pid, "limit": 1})
            if ft_res.get("success") and ft_res.get("data"):
                ft_d = ft_res["data"]
                ft_list = (
                    ft_d[0].get("fulltext_image", [])
                    if (isinstance(ft_d, list) and ft_d)
                    else (ft_d.get("fulltext_image", []) if isinstance(ft_d, dict) else [])
                )
                if ft_list:
                    abs_img_url = ft_list[0].get("path") or ""
        enriched["abs_img_url"] = abs_img_url

        # 获取代表专利的官方 PDF 全文下载链接（固化到概览 HTML 卡片中）
        pdf_url = ""
        pdf_res = call_mcp_tool("pdf", {"patent_id": pid})
        if pdf_res.get("success") and pdf_res.get("data"):
            pdf_obj = pdf_res["data"][0].get("pdf", {})
            if isinstance(pdf_obj, dict):
                pdf_url = pdf_obj.get("path") or ""
        enriched["pdf_url"] = pdf_url

        # 对于非中文代表专利，严禁调用智慧芽机翻；标题与摘要由当前大模型直接翻译
        is_bi = is_non_chinese_text(enriched.get("title", "")) or is_non_chinese_text(enriched.get("abstract", ""))
        enriched["is_bilingual"] = is_bi
        enriched["title_cn"] = ""
        enriched["abstract_cn"] = ""

        if "G" in modules:
            cit_res = call_mcp_tool("forward_citation", {"patent_id": pid})
            if cit_res.get("success") and cit_res.get("data"):
                cited_list = cit_res["data"][0].get("patent_cited", {}).get("cited_by_patents", [])
                enriched["forward_citations"] = len(cited_list)
            else:
                enriched["forward_citations"] = 0
        return enriched

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        enriched_top = list(executor.map(enrich_patent, top_patents))

    if "D" in modules:
        print(f"## [模块 D] 核心代表专利精选*（Top {len(enriched_top)}）")
        print(f"- *注：遴选自当前检索高相关代表专利池（Top {len(results)}），优先覆盖各集团核心授权件与高清附图\n")
        print("| 序号 | 公开(公告)号 | 专利标题（非中文含中外对照） | 当前权利人 | 申请日 | 法律状态 |" + (" 被引次数 |" if "G" in modules else ""))
        print("| :--- | :--- | :--- | :--- | :--- | :--- |" + (" :--- |" if "G" in modules else ""))
        for idx, p in enumerate(enriched_top, 1):
            t_orig = p.get("title") or ""
            t_cn = p.get("title_cn") or ""
            disp_t = f"🇨🇳 {t_cn} ({t_orig})" if (t_cn and t_cn != t_orig) else t_orig
            row = (
                f"| **#{idx}** | `{p.get('pn')}` | {disp_t} | "
                f"{p.get('current_assignee') or p.get('original_assignee')} | "
                f"{p.get('apdt')} | **{p.get('legal_status')}** |"
            )
            if "G" in modules:
                row += f" {p.get('forward_citations', 0)} 次 |"
            print(row)
        print()

    if "E" in modules:
        print("## [模块 E] 代表专利技术摘要与摘要附图汇总（供提炼核心技术方向与解决痛点）")
        for idx, p in enumerate(enriched_top, 1):
            abs_txt = p.get("abstract") or "（仅标题）"
            abs_cn = p.get("abstract_cn") or ""
            t_orig = p.get("title") or ""
            t_cn = p.get("title_cn") or ""
            disp_t = f"{t_cn} / {t_orig}" if (t_cn and t_cn != t_orig) else t_orig
            img_u = p.get("abs_img_url") or ""
            img_md = f"\n  - **摘要附图**：![{p.get('pn')}摘要附图]({img_u})" if img_u else ""
            if abs_cn and abs_cn != abs_txt:
                print(f"- **#{idx} `{p.get('pn')}` 《{disp_t}》 [🌐 中外文对照]**：\n  - **🇨🇳 中文译文**：{abs_cn}\n  - **🌐 外文原文**：{abs_txt}{img_md}")
            else:
                print(f"- **#{idx} `{p.get('pn')}` 《{disp_t}》**：{abs_txt}{img_md}")
        print()

    # 自动生成单文件交互式移动端 HTML 报告
    reports_dir = SKILL_DIR.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe_slug = re.sub(r'[^\w\u4e00-\u9fa5-]+', '_', (args.company + "_" + args.keyword).strip("_") or "overview")[:40]
    html_path = Path(args.html_out) if getattr(args, "html_out", "") else (reports_dir / f"patent_overview_{safe_slug}.html")
    title_label = f"{args.company} {args.keyword}".strip() or f"专利概览 ({query_text})"
    html_content = render_overview_html(
        query_text=query_text,
        total_count=total_count,
        sample_count=len(results),
        granted_count=granted_count,
        year_counter=display_year_counter,
        auth_counter=auth_counter,
        inventor_counter=inventor_counter,
        corp_analysis=corp_analysis,
        enriched_top=enriched_top,
        title_label=title_label,
        summary_text=args.extra_prompt or tpl.get("custom_prompt", ""),
        tech_list=tech_values,
        grant_rate_str=grant_rate_str,
        raw_rank_list=rank_values,
    )
    html_path.write_text(html_content, encoding="utf-8")
    print(f"## [交互式 HTML 报告已生成]")
    print(f"- **HTML 报告本地路径**：`{html_path.as_posix()}`\n")
    print("=================================================================")
    print("⚠️ 【模型回复格式强约束（WorkBuddy 聊天框防冗余指令 — 必须严格遵守）】")
    print("全量明细（完整公司树、年度图表、8篇代表专利摘要与高清附图）已 100% 写入上方 HTML 报告！")
    print("你在聊天框输出的文字【总行数严禁超过 22 行】，严禁画字符条形图、严禁罗列原始申请人长名单、严禁在表格外单独写技术焦点列表！必须严格按以下极简模板填空输出：")
    print("""
📊 **交互式全量看板已生成（含完整公司树、趋势图表与代表专利高清附图）**：
👉 `{html_file}`

**⚡ 3句话核心结论**
- **规模与趋势**：全球命中 **{total}** 件，近年峰值在 XXXX-XXXX 年（抽样含授权 B 约 {granted} 件）。
- **头部竞争格局**：**[集团1]**（XX件）、**[集团2]**（XX件）、**[集团3]**（XX件）领跑。
- **核心技术焦点**：集中在 **[焦点1]**、**[焦点2]**、**[焦点3]** 等方向。

**🏢 Top 5 主要申请主体（智慧芽公司树控股归并，完整榜单见 HTML）**
| 排名 | 集团系 (领域全口径) | 🏢 核心母公司 | 🔗 主要控股子公司 / 🌍 海外主体 (最多列2个) |
| :--- | :--- | :--- | :--- |
| #1 | ... | ... | ... |
*(仅列 Top 5 集团，每个集团右侧最多写 2 个代表性子主体)*

**🏆 核心代表专利精选（点击 HTML 可查看每篇专利的高清摘要附图）**
| # | 公开号 | 【核心看点】专利原名称 | 权利人 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| #1 | `...` | **【4~6字看点】** 《专利原始名称》 | ... | 🟢有效/🟡审中/⚪失效 |

💡 **快捷操作**：直接回复 **`#序号`**（如 `#1`）精读单篇专利；回复 **`0`** 定制/保存模板。
""".strip().format(html_file=html_path.name, total=f"{total_count:,}", granted=granted_count))
    print("=================================================================")


def cmd_detail(args: argparse.Namespace) -> None:
    """执行单篇专利深度精读聚合查询（关键段落、简述、权利要求、配对附图）"""
    tpl = get_template_by_id("detail", args.template)
    modules = set(tpl.get("modules", ["A", "B", "C", "E", "F", "I"]))
    if args.modules:
        modules = set(m.strip().upper() for m in args.modules.split(",") if m.strip())

    target = args.patent.strip()
    is_uuid = bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-", target))
    query_arg = {"patent_id": target} if is_uuid else {"patent_number": target.upper()}

    # 译文来源策略：
    # - 摘要 + 权利要求：不使用 MCP 机翻，改为导出翻译任务由大模型翻译（质量更高、术语更准）
    # - 说明书：直接采用智慧芽官方机翻（description_translated），保证长文本覆盖与速度
    tasks_to_run = [
        "bibliography",
        "get_patent_legal_status",
        "claims",
        "description",
        "fulltext_image",
        "abstract_image",
        "pdf",
        "description_translated",
    ]
    if "I" in modules:
        tasks_to_run.extend(["reexamination_invalidation", "transfer_data", "pledge_data", "license_data"])
    if "J" in modules:
        tasks_to_run.extend(["family", "forward_citation"])

    results_map = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_name = {}
        for t_name in set(tasks_to_run):
            t_args = dict(query_arg)
            if t_name in ("abstract_translated", "claim_translated", "description_translated"):
                t_args["lang"] = "CN"
            elif t_name == "fulltext_image":
                t_args["limit"] = max(args.max_images * 2, 20)
            future_to_name[executor.submit(call_mcp_tool, t_name, t_args)] = t_name

        for future in concurrent.futures.as_completed(future_to_name):
            t_name = future_to_name[future]
            try:
                results_map[t_name] = future.result()
            except Exception as e:
                results_map[t_name] = {"success": False, "error_msg": str(e)}

    bib_res = results_map.get("bibliography", {})
    if not bib_res.get("success") or not bib_res.get("data"):
        print(f"❌ 未能查到专利 `{target}` 的著录项信息，请确认公开号（如 `CN110806829B`）或专利 ID 是否正确。")
        sys.exit(1)

    bib_root = bib_res["data"][0]
    pn = bib_root.get("pn", target)
    pid = bib_root.get("patent_id", "")
    bib = bib_root.get("bibliographic_data", {})

    titles = bib.get("invention_title", [])
    if isinstance(titles, dict):
        titles = [titles]
    title_str = titles[0].get("text", "") if titles else "未知标题"

    abstracts = bib.get("abstracts", [])
    if isinstance(abstracts, dict):
        abstracts = [abstracts]
    abstract_str = clean_html_text(abstracts[0].get("text", "")) if abstracts else "暂无摘要"

    # 严格执行翻译规则：
    # - 标题 / 摘要 / 权利要求：严禁使用智慧芽机翻，必须由大模型翻译（质量更高、术语更统一）
    # - 说明书：只拉取智慧芽官方机翻（description_translated），注明「智慧芽官方机器翻译」
    title_cn = ""
    abstract_cn = ""

    # 可选直接加载 --translations 传入的模型译文
    model_translations = {}
    trans_arg = getattr(args, "translations", "")
    if trans_arg and Path(trans_arg).exists():
        try:
            model_translations = json.loads(Path(trans_arg).read_text(encoding="utf-8"))
            if isinstance(model_translations, dict):
                title_cn = model_translations.get("title", "")
                abstract_cn = model_translations.get("abstract", "")
        except Exception:
            pass

    clm_res = results_map.get("claims", {})
    clm_total = 0
    indep_cnt = 0
    parsed_clms = {"independent": [], "dependent": []}
    if clm_res.get("success") and clm_res.get("data"):
        clm_root = clm_res["data"][0]
        clm_total = clm_root.get("claim_count", 0)
        clm_items = clm_root.get("claims", [])
        raw_clm_html = clm_items[0].get("claim_text", "") if clm_items else ""
        indep_cnt = clm_items[0].get("claim_independent_count", 0) if clm_items else 0
        parsed_clms = parse_claims_structured(raw_clm_html)

    parsed_clms_cn = {"independent": [], "dependent": []}
    if model_translations:
        mt_indep = [model_translations.get(f"indep{i}", "") for i in range(1, len(parsed_clms["independent"]) + 1)]
        mt_dep = [model_translations.get(f"dep{i}", "") for i in range(1, len(parsed_clms["dependent"]) + 1)]
        if any(mt_indep) or any(mt_dep):
            parsed_clms_cn = {"independent": mt_indep, "dependent": mt_dep}

    desc_res = results_map.get("description", {})
    ft_img_res = results_map.get("fulltext_image", {})
    raw_desc_html = ""
    if desc_res.get("success") and desc_res.get("data"):
        desc_list = desc_res["data"][0].get("description", [])
        if desc_list:
            raw_desc_html = desc_list[0].get("text", "")

    ft_images = []
    if ft_img_res.get("success") and ft_img_res.get("data"):
        ft_data = ft_img_res["data"]
        if isinstance(ft_data, list) and ft_data:
            ft_images = ft_data[0].get("fulltext_image", [])
        elif isinstance(ft_data, dict):
            ft_images = ft_data.get("fulltext_image", [])

    parsed_desc = parse_description_and_figures(raw_desc_html, ft_images)

    parsed_desc_cn = {}
    desc_tr = results_map.get("description_translated", {})
    if desc_tr.get("success") and desc_tr.get("data"):
        raw_desc_cn = desc_tr["data"][0].get("description", "")
        if raw_desc_cn:
            parsed_desc_cn = parse_description_and_figures(raw_desc_cn, [])

    # 判断是否为非中文专利（标题、摘要、权利要求或说明书任一核心部分为外文）
    is_bilingual = (
        is_non_chinese_text(title_str)
        or is_non_chinese_text(abstract_str)
        or (parsed_clms["independent"] and is_non_chinese_text(parsed_clms["independent"][0]))
        or (parsed_desc.get("summary") and is_non_chinese_text(parsed_desc.get("summary", "")))
    )

    # 若为非中文专利且有附图说明中文翻译，将中文图注按序配对到 paired_figures
    if is_bilingual and parsed_desc.get("paired_figures") and parsed_desc_cn.get("drawing_desc"):
        cn_fig_caps = extract_fig_captions_from_text(parsed_desc_cn["drawing_desc"])
        for idx_f, fig_obj in enumerate(parsed_desc["paired_figures"]):
            if idx_f < len(cn_fig_caps):
                fig_obj["caption_cn"] = cn_fig_caps[idx_f]

    app_ref = bib.get("application_reference", {})
    pub_ref = bib.get("publication_reference", {})
    apno = f"{app_ref.get('country', '')}{app_ref.get('doc_number', '')}"
    apdt = app_ref.get("date", "")
    pbdt = pub_ref.get("date", "")
    exdt = bib.get("exdt", "未知")
    parties = bib.get("parties", {})
    assignees = [a.get("name", "") for a in parties.get("assignees", []) if a.get("name")]
    applicants = [a.get("name", "") for a in parties.get("applicants", []) if a.get("name")]
    inventors = [i.get("name", "") for i in parties.get("inventors", []) if i.get("name")]

    legal_res = results_map.get("get_patent_legal_status", {})
    simple_status = "未知"
    if legal_res.get("success") and legal_res.get("data"):
        simple_status = "/".join(legal_res["data"][0].get("simple_legal_status", ["未知"]))

    header_title_disp = f"《{title_cn}》（{title_str}） [🌐 非中文专利·中外文双语对照]" if (is_bilingual and title_cn and title_cn != title_str) else f"《{title_str}》"
    print(f"# 📄 单篇专利深度精读数据包：{header_title_disp}")
    print(f"- **选用模板**：`[{tpl.get('id')}] {tpl.get('name')}` (激活模块: `{','.join(sorted(modules))}`)")
    if is_bilingual:
        print("- **语言检测**：🌐 **检测到非中文专利，已自动启用【中外文双语对照模式】**")
    if args.extra_prompt or tpl.get("custom_prompt"):
        print(f"- **模板分析要求**：{tpl.get('custom_prompt', '')} {args.extra_prompt or ''}\n")

    if "A" in modules:
        print("## [模块 A] 基础著录项信息")
        print(f"- **公开(公告)号**：`{pn}` | **申请号**：`{apno}` | **专利ID**：`{pid}`")
        if is_bilingual and title_cn and title_cn != title_str:
            print(f"- **专利名称（中外文对照）**：🇨🇳 **{title_cn}** ｜ 🌐 `{title_str}`")
        else:
            print(f"- **专利名称**：{title_str}")
        print(f"- **当前法律状态**：**{simple_status}** | **预计到期日**：{exdt}")
        print(f"- **当前权利人**：{'、'.join(assignees or applicants) or '未知'}")
        print(f"- **原始申请人**：{'、'.join(applicants) or '未知'}")
        print(f"- **发明人**：{'、'.join(inventors) or '未知'}")
        print(f"- **申请日**：{apdt} | **公开(公告)日**：{pbdt}\n")

    if "B" in modules:
        print("## [模块 B] 摘要内容与摘要附图" + ("（中外文对照）" if is_bilingual else ""))
        if is_bilingual and abstract_cn and abstract_cn != abstract_str:
            print(f"**【🇨🇳 摘要中文译文】**：\n{abstract_cn}\n")
            print(f"**【🌐 摘要外文原文】**：\n{abstract_str}\n")
        else:
            print(f"**摘要内容**：\n{abstract_str}\n")
        abs_img_res = results_map.get("abstract_image", {})
        if abs_img_res.get("success") and abs_img_res.get("data"):
            drawing = abs_img_res["data"][0].get("abstract_drawing", {})
            img_path = drawing.get("path") if isinstance(drawing, dict) else None
            if img_path:
                print(f"**摘要附图（请在回复中保留以下 Markdown 图片语法以在手机端直接显示）**：\n![{pn}摘要附图]({img_path})\n")
            else:
                print("- *该专利暂无摘要附图*\n")

    if "C" in modules or "D" in modules:
        if "C" in modules and (parsed_clms["independent"] or parsed_clms_cn["independent"]):
            print(f"## [模块 C] 独立权利要求（共 {indep_cnt} 项独立权利要求 / 总计 {clm_total} 项）" + (" [中外文对照]" if is_bilingual else ""))
            max_i = max(len(parsed_clms["independent"]), len(parsed_clms_cn["independent"])) if is_bilingual else len(parsed_clms["independent"])
            for idx in range(1, max_i + 1):
                ic_orig = parsed_clms["independent"][idx - 1] if idx - 1 < len(parsed_clms["independent"]) else ""
                ic_cn = parsed_clms_cn["independent"][idx - 1] if idx - 1 < len(parsed_clms_cn["independent"]) else ""
                print(f"### 独立权利要求 #{idx}")
                if is_bilingual and ic_cn and ic_cn != ic_orig:
                    print(f"- **🇨🇳 中文译文**：\n{ic_cn}\n")
                    print(f"- **🌐 外文原文**：\n{ic_orig}\n")
                else:
                    print(f"{ic_orig or ic_cn}\n")
        if "D" in modules and (parsed_clms["dependent"] or parsed_clms_cn["dependent"]):
            print(f"## [模块 D] 从属权利要求（前 10 项关键附加特征）" + (" [中外文对照]" if is_bilingual else ""))
            max_d = min(10, max(len(parsed_clms["dependent"]), len(parsed_clms_cn["dependent"])) if is_bilingual else len(parsed_clms["dependent"]))
            for idx in range(max_d):
                dc_orig = parsed_clms["dependent"][idx] if idx < len(parsed_clms["dependent"]) else ""
                dc_cn = parsed_clms_cn["dependent"][idx] if idx < len(parsed_clms_cn["dependent"]) else ""
                if is_bilingual and dc_cn and dc_cn != dc_orig:
                    print(f"- **🇨🇳 译**：{dc_cn}\n  **🌐 原**：{dc_orig}\n")
                else:
                    print(f"- {dc_orig or dc_cn}\n")

    if any(m in modules for m in ["E", "F", "G", "H"]):
        if "E" in modules:
            print("## [模块 E] 说明书关键段落：技术领域与背景技术（痛点）" + (" [中外文对照]" if is_bilingual else ""))
            if is_bilingual and (parsed_desc_cn.get("technical_field") or parsed_desc_cn.get("background")):
                if parsed_desc_cn.get("technical_field") or parsed_desc.get("technical_field"):
                    print(f"**【技术领域 · 🇨🇳 中文译文】**\n{parsed_desc_cn.get('technical_field', '')}\n")
                    print(f"**【技术领域 · 🌐 外文原文】**\n{parsed_desc.get('technical_field', '')}\n")
                print(f"**【背景技术 · 🇨🇳 中文译文】**\n{(parsed_desc_cn.get('background') or '')[:1800]}\n")
                print(f"**【背景技术 · 🌐 外文原文】**\n{(parsed_desc.get('background') or '')[:1800]}\n")
            else:
                if parsed_desc["technical_field"]:
                    print(f"**【技术领域】**\n{parsed_desc['technical_field']}\n")
                print(f"**【背景技术】**\n{parsed_desc['background'][:2000] or '暂无背景技术段落'}\n")

        if "F" in modules:
            print("## [模块 F] 说明书关键段落：发明内容与有益效果" + (" [中外文对照]" if is_bilingual else ""))
            if is_bilingual and parsed_desc_cn.get("summary"):
                print(f"**【发明内容 · 🇨🇳 中文译文】**\n{parsed_desc_cn['summary'][:2500]}\n")
                print(f"**【发明内容 · 🌐 外文原文】**\n{parsed_desc['summary'][:2500]}\n")
            else:
                print(f"{parsed_desc['summary'][:3000] or '暂无发明内容段落'}\n")

        if "G" in modules:
            print("## [模块 G] 说明书关键段落：具体实施方式摘录" + (" [中外文对照]" if is_bilingual else ""))
            if is_bilingual and parsed_desc_cn.get("embodiments"):
                print(f"**【具体实施方式 · 🇨🇳 中文译文】**\n{parsed_desc_cn['embodiments'][:2800]}\n")
                print(f"**【具体实施方式 · 🌐 外文原文】**\n{parsed_desc['embodiments'][:2800]}\n")
            else:
                print(f"{parsed_desc['embodiments'][:3500] or '暂无具体实施方式段落'}\n")

        if "H" in modules:
            print("## [模块 H] 附图说明与全文高清附图配对直出" + (" [中外文对照]" if is_bilingual else ""))
            if is_bilingual and parsed_desc_cn.get("drawing_desc"):
                print(f"**【附图说明 · 🇨🇳 中文译文】**\n{parsed_desc_cn['drawing_desc'][:1200]}\n")
            if parsed_desc["drawing_desc"]:
                print(f"**【附图说明 · 原文】**\n{parsed_desc['drawing_desc'][:1200]}\n")
            figs = parsed_desc["paired_figures"][: args.max_images]
            if figs:
                print(f"**【配对高清附图（前 {len(figs)} 幅，请在回复中保留以下 Markdown 图片以在手机端展示）】**：")
                for fig in figs:
                    cap_c = fig.get("caption_cn")
                    cap_str = f"🇨🇳 {cap_c} ｜ 🌐 {fig['caption']}" if (is_bilingual and cap_c) else fig["caption"]
                    print(f"- **{cap_str}**\n  ![{fig['title']}]({fig['url']})")
                print()
            else:
                print("- *该专利暂无全文附图数据*\n")

    if "I" in modules:
        print("## [模块 I] 法律状态与风险排查（无效/转移/许可/质押）")
        print(f"- **当前简单法律状态**：**{simple_status}**")
        for r_key, r_label in [
            ("reexamination_invalidation", "复审与无效记录"),
            ("transfer_data", "权利转移记录"),
            ("license_data", "专利许可备案"),
            ("pledge_data", "专利质押记录"),
        ]:
            r_obj = results_map.get(r_key, {})
            r_list = r_obj.get("data", []) if r_obj.get("success") else []
            if r_list:
                print(f"- **{r_label}**：存在记录 -> `{json.dumps(r_list, ensure_ascii=False)[:600]}`")
            else:
                print(f"- **{r_label}**：无记录（未发现相关风险/变更）")
        print()

    if "J" in modules:
        print("## [模块 J] 同族布局与被引情况")
        fam_res = results_map.get("family", {})
        if fam_res.get("success") and fam_res.get("data"):
            sf = fam_res["data"][0].get("patent_family", {}).get("simple_family", [])
            fam_pns = [f"{x.get('country')}{x.get('doc_number')}{x.get('kind')}" for x in sf[:15]]
            print(f"- **简单同族成员（共 {len(sf)} 件）**：{', '.join(fam_pns) or '无'}")
        cit_res = results_map.get("forward_citation", {})
        if cit_res.get("success") and cit_res.get("data"):
            c_list = cit_res["data"][0].get("patent_cited", {}).get("cited_by_patents", [])
            print(f"- **被后续专利引用次数**：共 **{len(c_list)}** 次")
            for c_item in c_list[:5]:
                print(f"  - `{c_item.get('pn')}` 《{c_item.get('title')}》 ({c_item.get('current_assignee')})")
        print()

    if "K" in modules:
        pdf_res = results_map.get("pdf", {})
        if pdf_res.get("success") and pdf_res.get("data"):
            pdf_url = pdf_res["data"][0].get("pdf", {}).get("path", "")
            if pdf_url:
                print(f"## [模块 K] 官方 PDF 全文下载")
                print(f"- 📄 **[点击查看/下载 {pn} 专利全文 PDF]({pdf_url})**\n")

    # 自动生成单篇专利深度精读交互式 HTML 报告
    reports_dir = SKILL_DIR.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe_pn = re.sub(r"[^\w-]+", "_", pn)
    html_path = Path(args.html_out) if getattr(args, "html_out", "") else (reports_dir / f"patent_detail_{safe_pn}.html")
    abs_img_url = ""
    abs_img_res = results_map.get("abstract_image", {})
    if abs_img_res.get("success") and abs_img_res.get("data"):
        drawing = abs_img_res["data"][0].get("abstract_drawing", {})
        if isinstance(drawing, dict):
            abs_img_url = drawing.get("path") or ""
    pdf_url = ""
    pdf_res = results_map.get("pdf", {})
    if pdf_res.get("success") and pdf_res.get("data"):
        pdf_url = pdf_res["data"][0].get("pdf", {}).get("path", "")

    translator_label = getattr(args, "translator_label", "") or "AI 模型"

    # 非中文专利：导出「摘要 + 权利要求」模型翻译任务（说明书已由智慧芽机翻覆盖）
    if is_bilingual:
        segments = build_translation_segments(pn, title_str, abstract_str, parsed_clms)
        job_path = Path(args.translate_job) if getattr(args, "translate_job", "") else (
            reports_dir / f"patent_detail_{safe_pn}_translation_job.json"
        )
        trans_hint = reports_dir / f"patent_detail_{safe_pn}_translations.json"
        job = {
            "pn": pn,
            "html_path": html_path.as_posix(),
            "translations_path_hint": trans_hint.as_posix(),
            "translator_label": translator_label,
            "strategy": {"abstract": "model", "claims": "model", "description": "patsnap_mt"},
            "segments": segments,
            "snapshot": {
                "pn": pn, "apno": apno, "pid": pid, "title_str": title_str,
                "simple_status": simple_status, "exdt": str(exdt),
                "assignees": assignees, "applicants": applicants, "inventors": inventors,
                "apdt": str(apdt), "pbdt": str(pbdt),
                "abstract_str": abstract_str, "abs_img_url": abs_img_url,
                "parsed_clms": parsed_clms, "parsed_desc": parsed_desc,
                "pdf_url": pdf_url, "is_bilingual": is_bilingual,
                "title_cn": title_cn, "abstract_cn": abstract_cn,
                "parsed_clms_cn": parsed_clms_cn, "parsed_desc_cn": parsed_desc_cn,
            },
        }
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
        print("## [🌐 非中文专利 · 摘要/权利要求模型翻译任务已生成]")
        print(f"- **译文策略**：摘要与权利要求 = {translator_label} 模型翻译；说明书 = 智慧芽机翻（已拉取）")
        print(f"- **任务文件**：`{job_path.as_posix()}`（共 {len(segments)} 段待译：title/abstract/indep*/dep*）")
        print("- **来源标注**：由重建脚本在三个 Tab 顶部各写入一次，正文无需逐段标注；`--translator-label` 仅作署名，不调用该模型 API")
        print(f"- **下一步（必须执行）**：将每个 `id` 的 `text` 翻译为简体中文（权利用专利语境、术语统一），")
        print(f"  写成 JSON（键=段落 id，值=中文译文，**必须包含 `title`**），保存至：`{trans_hint.as_posix()}`")
        print("- 然后执行重建命令（离线回注，不重复请求 MCP）：")
        print("  ```bash")
        print(f'  python "{(SKILL_DIR / "scripts" / "zhihuiya_helper.py").as_posix()}" translate-apply \\')
        print(f'    --job "{job_path.as_posix()}" --translations "{trans_hint.as_posix()}"')
        print("  ```")
        print()

    html_content = render_detail_html(
        pn=pn,
        apno=apno,
        pid=pid,
        title_str=title_str,
        simple_status=simple_status,
        exdt=str(exdt),
        assignees=assignees,
        applicants=applicants,
        inventors=inventors,
        apdt=str(apdt),
        pbdt=str(pbdt),
        abstract_str=abstract_str,
        abs_img_url=abs_img_url,
        parsed_clms=parsed_clms,
        parsed_desc=parsed_desc,
        pdf_url=pdf_url,
        is_bilingual=is_bilingual,
        title_cn=title_cn,
        abstract_cn=abstract_cn,
        parsed_clms_cn=parsed_clms_cn,
        parsed_desc_cn=parsed_desc_cn,
        model_translations=model_translations,
        translator_label=translator_label,
    )
    html_path.write_text(html_content, encoding="utf-8")
    print(f"## [交互式 HTML 报告已生成]")
    print(f"- **HTML 报告本地路径**：`{html_path.as_posix()}`\n")
    print("=================================================================")
    print("⚠️ 【模型回复格式强约束（WorkBuddy 聊天框防冗余指令 — 必须严格遵守）】")
    print("全部配对高清附图画廊（Lightbox）、独立/从属权利要求全文、说明书完整章节（含中外文逐段双语对照）已 100% 写入上方 HTML 报告！")
    if is_bilingual:
        print("当前专利为【非中文专利】，你在聊天框输出的文字【总行数 ≤ 20 行】，必须提供精炼的【中外文双语对照】，核心部件/特征必须采用「中文术语 (外文原词)」格式标注，严禁抄写长篇原文刷屏！请严格按以下双语模板填空输出：")
        print("""
📄 **单篇精读双语看板已生成（支持 [🔀中外对照 / 🇨🇳仅看中文 / 🌐仅看原文] 一键切换）**：
👉 `{html_file}` ｜ 📥 [下载官方 PDF 全文]({pdf_link})
- 📌 **译文来源**：摘要/权利要求 = {translator_label} 模型翻译 ｜ 说明书 = 智慧芽机翻

**💡 一句话看懂 `{pn}` [🌐 中外文对照]**
- **专利名称**：🇨🇳 **{title_cn}** ｜ 🌐 *{title}*
- **基础信息**：🏢 {assignee} ｜ 📅 申请日 {apdt} ｜ 状态：**{status}**
- **核心方案（中外术语对照）**：<用1~2句话（≤90字）讲清核心结构与效果，关键部件必须带外文原词，如：通过滚轮收纳盒 (roller repository) 与可调式过滤组件 (adjustable filter assembly) 配合...>

**⚖️ 核心要点与独权中外文对照（完整逐条双语权利要求与说明书见 HTML）**
- **解决痛点**：<1句话提炼，关键概念带外文原词>
- **独权1核心特征（中外对照）**：
  - ① **<中文特征1> (`<对应外文短语>`)**：<简述连接或配合关系>
  - ② **<中文特征2> (`<对应外文短语>`)**：<简述连接或配合关系>
  - ③ **<中文特征3> (`<对应外文短语>`)**：<简述连接或配合关系>
- **关键实施亮点**：<1~2句话提炼核心实施例动作逻辑，标注段落号如 [0045]及部件标号>

**🖼️ 代表性附图预览**（其余 {fig_cnt} 幅中外文配对高清附图请点击上方 HTML 画廊全屏放大查看）：
{img_block}
""".strip().format(
            html_file=html_path.name,
            pdf_link=pdf_url or "#",
            pn=pn,
            title_cn=title_cn or title_str,
            title=title_str,
            assignee="、".join(assignees or applicants) or "未知",
            apdt=apdt,
            status=simple_status,
            fig_cnt=len(parsed_desc["paired_figures"]),
            img_link=abs_img_url or (parsed_desc["paired_figures"][0]["url"] if parsed_desc["paired_figures"] else ""),
            img_block=("![{}摘要附图]({})".format(pn, abs_img_url or (parsed_desc["paired_figures"][0]["url"] if parsed_desc["paired_figures"] else ""))) if (abs_img_url or parsed_desc["paired_figures"]) else "（本专利无可用附图）",
            translator_label=translator_label,
        ))
    else:
        print("你在聊天框输出的文字【总字数严禁超过 300 字（总行数 ≤ 18 行）】，严禁抄写权利要求或说明书长段落、严禁连续贴多张附图刷屏（聊天框仅允许放 1 张代表附图）！必须严格按以下极简模板填空输出：")
        print("""
📄 **单篇精读交互看板已生成（含高清附图放大画廊、完整权利要求与说明书原文）**：
👉 `{html_file}` ｜ 📥 [下载官方 PDF 全文]({pdf_link})

**💡 一句话看懂 `{pn}` 《{title}》**
- **基础信息**：🏢 {assignee} ｜ 📅 申请日 {apdt} ｜ 状态：**{status}**
- **核心方案**：<用1~2句话（≤80字）通俗讲清：通过什么核心结构/步骤，解决了什么痛点，实现什么效果>

**⚖️ 核心要点速览（完整权利要求与说明书原文见 HTML）**
- **解决痛点**：<1句话，≤35字>
- **独权核心特征**：① <特征1>；② <特征2>；③ <特征3>（每点≤25字）
- **关键实施亮点**：<1~2句话提炼最核心的结构配合或控制逻辑，标注段落号如 [0080]>

**🖼️ 代表性附图预览**（其余配对高清附图请点击上方 HTML 画廊全屏放大查看）：
{img_block}
""".strip().format(
            html_file=html_path.name,
            pdf_link=pdf_url or "#",
            pn=pn,
            title=title_str,
            assignee="、".join(assignees or applicants) or "未知",
            apdt=apdt,
            status=simple_status,
            img_link=abs_img_url or (parsed_desc["paired_figures"][0]["url"] if parsed_desc["paired_figures"] else ""),
            img_block=("![{}摘要附图]({})".format(pn, abs_img_url or (parsed_desc["paired_figures"][0]["url"] if parsed_desc["paired_figures"] else ""))) if (abs_img_url or parsed_desc["paired_figures"]) else "（本专利无可用附图）",
        ))
    print("=================================================================")


def cmd_translate_apply(args: argparse.Namespace) -> None:
    """回注模型译文（摘要 + 权利要求）并重建双语 HTML；说明书沿用智慧芽机翻（来自任务快照，离线重建）"""
    job_path = Path(args.job)
    trans_path = Path(args.translations)
    if not job_path.exists():
        print(f"❌ 找不到翻译任务文件：`{job_path.as_posix()}`")
        sys.exit(1)
    if not trans_path.exists():
        print(f"❌ 找不到译文文件：`{trans_path.as_posix()}`（请先按任务文件逐项翻译后保存为 JSON）")
        sys.exit(1)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    translations = json.loads(trans_path.read_text(encoding="utf-8"))
    if not isinstance(translations, dict) or not translations:
        print("❌ 译文文件必须是非空 JSON 对象（键=片段 id，值=中文译文）。")
        sys.exit(1)

    snap = job.get("snapshot") or {}
    if not snap:
        print("❌ 任务文件缺少 snapshot 快照，请重新运行 detail 生成任务。")
        sys.exit(1)
    label = getattr(args, "translator_label", "") or job.get("translator_label") or "AI 模型"

    html_out = Path(args.html_out) if getattr(args, "html_out", "") else Path(job["html_path"])
    html_content = render_detail_html(
        pn=snap["pn"],
        apno=snap["apno"],
        pid=snap["pid"],
        title_str=snap["title_str"],
        simple_status=snap["simple_status"],
        exdt=snap["exdt"],
        assignees=snap["assignees"],
        applicants=snap["applicants"],
        inventors=snap["inventors"],
        apdt=snap["apdt"],
        pbdt=snap["pbdt"],
        abstract_str=snap["abstract_str"],
        abs_img_url=snap["abs_img_url"],
        parsed_clms=snap["parsed_clms"],
        parsed_desc=snap["parsed_desc"],
        pdf_url=snap.get("pdf_url", ""),
        is_bilingual=snap.get("is_bilingual", True),
        title_cn=snap.get("title_cn", ""),
        abstract_cn=snap.get("abstract_cn", ""),
        parsed_clms_cn=snap.get("parsed_clms_cn") or {},
        parsed_desc_cn=snap.get("parsed_desc_cn") or {},
        model_translations=translations,
        translator_label=label,
    )
    html_out.write_text(html_content, encoding="utf-8")

    seg_ids = [seg["id"] for seg in job.get("segments", [])]
    missing = [sid for sid in seg_ids if sid not in translations]
    print("# 🌐 双语对照 HTML 报告已重建（摘要/权利要求=模型译文，说明书=智慧芽机翻）")
    print(f"- **HTML 报告本地路径**：`{html_out.as_posix()}`")
    print(f"- **模型翻译覆盖率**：{len(seg_ids) - len(missing)}/{len(seg_ids)} 段 ｜ 翻译模型：{label}")
    if missing:
        print(f"- ⚠️ 以下片段暂无模型译文（该处将回退显示原文）：`{missing[:12]}`")
    print()

    pdf_url = snap.get("pdf_url", "")
    figs = (snap.get("parsed_desc") or {}).get("paired_figures") or []
    img_link = snap.get("abs_img_url") or (figs[0]["url"] if figs else "")
    img_block = f'![{snap["pn"]}摘要附图]({img_link})' if img_link else "（本专利无可用附图）"
    print("=================================================================")
    print("⚠️ 【模型回复格式强约束（WorkBuddy 聊天框防冗余指令 — 必须严格遵守）】")
    print("双语对照（摘要/权利要求=模型译文，说明书=智慧芽机翻）、权利要求全文、说明书完整章节与附图画廊均已写入 HTML。")
    print("聊天框输出【总行数 ≤ 20 行】，必须提供精炼的中外文对照，关键部件用「中文术语 (外文原词)」格式，严禁抄写长段原文！按以下模板输出：")
    print(f"""
📄 **单篇精读双语看板已生成（支持 [🔀中外对照 / 🇨🇳仅看中文 / 🌐仅看原文] 一键切换）**：
👉 `{html_out.name}` ｜ 📥 [下载官方 PDF 全文]({pdf_url or "#"})
- 📌 **译文来源**：摘要/权利要求 = {label} 模型翻译 ｜ 说明书 = 智慧芽机翻

**💡 一句话看懂 `{snap["pn"]}` [🌐 中外文对照]**
- **专利名称**：🇨🇳 **{translations.get("title") or snap["title_str"]}** ｜ 🌐 *{snap["title_str"]}*
- **基础信息**：🏢 {"、".join(snap["assignees"] or snap["applicants"]) or "未知"} ｜ 📅 申请日 {snap["apdt"]} ｜ 状态：**{snap["simple_status"]}**
- **核心方案（中外术语对照）**：<用1~2句话（≤90字）讲清核心结构与效果，关键部件带外文原词>

**⚖️ 独权中外对照（完整逐条双语权利要求与说明书见 HTML）**
- **解决痛点**：<1句话，关键概念带外文原词>
- **独权核心特征**：① **<中文特征1> (`<外文短语>`)**；② **<中文特征2> (`<外文短语>`)**；③ **<中文特征3> (`<外文短语>`)**
- **关键实施亮点**：<1~2句话，标注段落号如 [0045]>

**🖼️ 代表性附图预览**（其余 {len(figs)} 幅中外文配对附图请点击 HTML 画廊查看）：
{img_block}
""".strip())
    print("=================================================================")



def main() -> None:
    parser = argparse.ArgumentParser(description="智慧芽 MCP 移动端专利助手聚合脚本")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_menu = subparsers.add_parser("menu", help="显示预设模板与自定义模板选择菜单")
    p_menu.add_argument("--mode", choices=["overview", "detail"], required=True, help="查询模式")
    p_menu.add_argument("--builder", action="store_true", help="显示新建自定义模板的模块选择表")

    p_tpl = subparsers.add_parser("template", help="管理自定义模板")
    p_tpl.add_argument("--action", choices=["list", "add", "delete"], required=True)
    p_tpl.add_argument("--mode", choices=["overview", "detail"], default="overview")
    p_tpl.add_argument("--name", default="", help="新模板名称")
    p_tpl.add_argument("--modules", default="", help="模块代码列表，逗号分隔，如 A,B,D,E")
    p_tpl.add_argument("--prompt", default="", help="自然语言描述的自定义关注重点")
    p_tpl.add_argument("--id", default="", help="要删除的模板ID或名称")

    p_ov = subparsers.add_parser("overview", help="查询公司/产品/领域的整体专利情况")
    p_ov.add_argument("--company", default="", help="公司/申请人名称")
    p_ov.add_argument("--keyword", default="", help="产品名或技术领域关键词")
    p_ov.add_argument("--raw-query", default="", help="自定义高级 PatSnap 检索式")
    p_ov.add_argument("--template", default="1", help="使用的模板编号或名称（默认 1）")
    p_ov.add_argument("--modules", default="", help="临时覆盖的模块列表，如 A,B,D")
    p_ov.add_argument("--extra-prompt", default="", help="临时附加的自然语言关注要求")
    p_ov.add_argument("--limit", type=int, default=8, help="展示的核心代表专利数量（默认 8）")
    p_ov.add_argument("--sort", default="SCORE", choices=["SCORE"], help="排序方式")
    p_ov.add_argument("--html-out", default="", help="自定义生成的 HTML 报告文件路径")

    p_dt = subparsers.add_parser("detail", help="查询单篇专利的关键段落、简述及附图")
    p_dt.add_argument("--patent", required=True, help="专利公开号（如 CN110806829B）或专利唯一 ID")
    p_dt.add_argument("--template", default="1", help="使用的模板编号或名称（默认 1）")
    p_dt.add_argument("--modules", default="", help="临时覆盖的模块列表，如 A,B,C,H")
    p_dt.add_argument("--extra-prompt", default="", help="临时附加的自然语言关注要求")
    p_dt.add_argument("--max-images", type=int, default=6, help="最多配对展示的全文附图数量（默认 6）")
    p_dt.add_argument("--html-out", default="", help="自定义生成的 HTML 报告文件路径")
    p_dt.add_argument("--translate-job", default="", help="非中文专利的模型翻译任务 JSON 输出路径（默认自动命名）")
    p_dt.add_argument("--translations", default="", help="可选直接传入模型译文 JSON 路径，一步完成双语 HTML 渲染")
    p_dt.add_argument("--translator-label", default="", help="翻译所用模型名称，用于在报告中标注译文来源（建议填当前对话实际使用的模型名，如 Claude / GPT-5 / DeepSeek）")

    p_ta = subparsers.add_parser("translate-apply", help="回注模型译文（摘要+权利要求）并重建双语 HTML（说明书用智慧芽机翻）")
    p_ta.add_argument("--job", required=True, help="detail 命令生成的翻译任务 JSON 路径")
    p_ta.add_argument("--translations", required=True, help="模型产出的译文 JSON 路径（键=片段 id，值=中文译文）")
    p_ta.add_argument("--translator-label", default="", help="翻译所用模型名称（默认取任务文件中记录的值）")
    p_ta.add_argument("--html-out", default="", help="自定义输出路径（默认覆盖原 HTML 报告）")

    args = parser.parse_args()
    if args.command == "menu":
        cmd_menu(args)
    elif args.command == "template":
        cmd_template(args)
    elif args.command == "overview":
        cmd_overview(args)
    elif args.command == "detail":
        cmd_detail(args)
    elif args.command == "translate-apply":
        cmd_translate_apply(args)


if __name__ == "__main__":
    main()
