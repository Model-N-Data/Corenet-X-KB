"""
CORENET X Knowledge Base — RAG-enabled Streamlit App v2
Documents uploaded by officer → text extracted → stored in GitHub repo.
Answers drawn from ACTUAL document text, not hardcoded summaries.
Secrets are configured in Streamlit Cloud settings, NOT in this file.
"""

import streamlit as st
import anthropic
import json, os, re, base64, io
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CORENET X Knowledge Base",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Config ───────────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"
DATA_PATH = "data"  # folder in GitHub repo

def cfg(key, default=""):
    try: return st.secrets[key]
    except: return os.environ.get(key, default)

def get_api_key():      return cfg("ANTHROPIC_API_KEY")
def get_github_token(): return cfg("GITHUB_TOKEN")
def get_github_repo():  return cfg("GITHUB_REPO", "")
def get_officer_pw():   return cfg("OFFICER_PASSWORD", "cx-officer-2025")
def github_enabled():   return bool(get_github_token() and get_github_repo())

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.tier-A{background:#e8f5ec;color:#1b6b3a;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;display:inline-block}
.tier-B{background:#e8f0f8;color:#1a3c5e;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;display:inline-block}
.tier-C{background:#fff3e0;color:#7a4500;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;display:inline-block}
.tier-D{background:#fdeaea;color:#8b1a1a;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;display:inline-block}
.kp-box{background:#fffde7;border-left:3px solid #f6c000;padding:9px 13px;border-radius:3px;font-size:13px;margin:8px 0}
.src-box{background:#f8f9fa;border:1px solid #dde3ec;padding:7px 12px;border-radius:5px;font-size:11.5px;color:#6b7280}
.user-bubble{background:#1a3c5e;color:#fff;padding:10px 14px;border-radius:16px 4px 16px 16px;display:inline-block;max-width:580px;font-size:14px;line-height:1.6}
.doc-active{background:#e8f5ec;border:1px solid #a8d5b5;border-radius:6px;padding:8px 12px;margin:4px 0}
.doc-superseded{background:#fdeaea;border:1px solid #f5b8b8;border-radius:6px;padding:8px 12px;margin:4px 0;opacity:.7}
.doc-pending{background:#fff3e0;border:1px solid #ffd580;border-radius:6px;padding:8px 12px;margin:4px 0}
</style>
""", unsafe_allow_html=True)

# ─── DEFAULT DOCUMENT REGISTRY ────────────────────────────────────────────────
# Pre-populated with the 12 official sources. "processed" = text chunks extracted.
DEFAULT_REGISTRY = {"documents": [
    {"id":"cop_v31",    "name":"COP v3.1 Edition (Dec 2025)",      "version":"3.1",      "pages":442, "status":"active","processed":False,"uploaded":None,"notes":"Primary regulatory standard"},
    {"id":"rabw_2026",  "name":"RABW Mar 2026",                     "version":"Mar 2026", "pages":181, "status":"active","processed":False,"uploaded":None,"notes":"Regulatory Advisory for Built Works"},
    {"id":"ifc_sg",     "name":"IFC-SG Revit SP Guide (Sep 2025)", "version":"Sep 2025", "pages":176, "status":"active","processed":False,"uploaded":None,"notes":"IFC+SG implementation guide"},
    {"id":"dg_pdf",     "name":"Design Gateway Guidelines",         "version":"2025",     "pages":0,   "status":"active","processed":False,"uploaded":None,"notes":"Image-based — OCR may be needed"},
    {"id":"cg_pdf",     "name":"Construction Gateway Guidelines",   "version":"2025",     "pages":0,   "status":"active","processed":False,"uploaded":None,"notes":"Image-based — OCR may be needed"},
    {"id":"hdb_fb",     "name":"HDB Feedback Document",            "version":"2025",     "pages":0,   "status":"active","processed":False,"uploaded":None,"notes":"HDB-specific requirements"},
    {"id":"consultant", "name":"Consultant Briefing Notes",        "version":"2025",     "pages":0,   "status":"active","processed":False,"uploaded":None,"notes":"Agency briefing materials"},
]}

# ─── GITHUB STORAGE ──────────────────────────────────────────────────────────
def gh_headers():
    return {"Authorization": f"Bearer {get_github_token()}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"}

def gh_read(path):
    """Read a JSON file from GitHub. Returns (data, sha) or (None, None)."""
    if not github_enabled() or not requests: return None, None
    url = f"https://api.github.com/repos/{get_github_repo()}/contents/{path}"
    try:
        r = requests.get(url, headers=gh_headers(), timeout=10)
        if r.status_code == 200:
            d = r.json()
            content = base64.b64decode(d["content"]).decode("utf-8")
            return json.loads(content), d["sha"]
    except Exception: pass
    return None, None

def gh_write(path, data, message, sha=None):
    """Write a JSON file to GitHub. Returns True on success."""
    if not github_enabled() or not requests: return False
    url = f"https://api.github.com/repos/{get_github_repo()}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(json.dumps(data, indent=2, ensure_ascii=False).encode()).decode()
    }
    if sha: body["sha"] = sha
    try:
        r = requests.put(url, headers=gh_headers(), json=body, timeout=15)
        return r.status_code in (200, 201)
    except Exception: return False

# ─── REGISTRY HELPERS ─────────────────────────────────────────────────────────
def load_registry():
    if github_enabled():
        data, _ = gh_read(f"{DATA_PATH}/registry.json")
        if data: return data
    reg = st.session_state.get("registry")
    return reg if reg is not None else DEFAULT_REGISTRY.copy()

def save_registry(registry):
    st.session_state["registry"] = registry
    if github_enabled():
        _, sha = gh_read(f"{DATA_PATH}/registry.json")
        gh_write(f"{DATA_PATH}/registry.json", registry,
                 f"Update document registry — {datetime.now().strftime('%Y-%m-%d %H:%M')}", sha)

def load_chunks(doc_id):
    """Load extracted text chunks for a document."""
    key = f"chunks_{doc_id}"
    if key in st.session_state: return st.session_state[key]
    if github_enabled():
        data, _ = gh_read(f"{DATA_PATH}/chunks/{doc_id}.json")
        if data:
            st.session_state[key] = data
            return data
    return []

def save_chunks(doc_id, chunks):
    """Save text chunks for a document."""
    st.session_state[f"chunks_{doc_id}"] = chunks
    if github_enabled():
        _, sha = gh_read(f"{DATA_PATH}/chunks/{doc_id}.json")
        gh_write(f"{DATA_PATH}/chunks/{doc_id}.json", chunks,
                 f"Add chunks for {doc_id} — {datetime.now().strftime('%Y-%m-%d')}", sha)

def load_custom_kb():
    """Load officer-added KB entries."""
    if github_enabled():
        data, _ = gh_read(f"{DATA_PATH}/custom_kb.json")
        if data: return data
    kb = st.session_state.get("custom_kb")
    return kb if kb is not None else []

def save_custom_kb(entries):
    st.session_state["custom_kb"] = entries
    if github_enabled():
        _, sha = gh_read(f"{DATA_PATH}/custom_kb.json")
        gh_write(f"{DATA_PATH}/custom_kb.json", entries,
                 f"Update custom KB — {datetime.now().strftime('%Y-%m-%d %H:%M')}", sha)

# ─── PDF PROCESSING ───────────────────────────────────────────────────────────
def extract_chunks_from_pdf(uploaded_file, chunk_size=800):
    """Extract text chunks from a PDF file. Returns list of chunk dicts."""
    if not pdfplumber:
        return [{"page": 0, "text": "pdfplumber not installed.", "chunk_id": "err"}]
    chunks = []
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if not text or not text.strip():
                    continue  # skip image-only pages
                text = re.sub(r'\s+', ' ', text).strip()
                # Split long pages into ~chunk_size char windows
                for i in range(0, len(text), chunk_size - 100):
                    chunk_text = text[i:i + chunk_size]
                    if len(chunk_text) > 50:
                        chunks.append({
                            "page": page_num,
                            "text": chunk_text,
                            "chunk_id": f"p{page_num}_c{i // chunk_size}"
                        })
    except Exception as e:
        chunks.append({"page": 0, "text": f"Extraction error: {e}", "chunk_id": "err"})
    return chunks

# ─── RETRIEVAL ────────────────────────────────────────────────────────────────
def get_relevant_chunks(query, max_chunks=6):
    """Find the most relevant text chunks across all active documents."""
    registry = load_registry()
    active_docs = [d for d in registry.get("documents", []) if d["status"] == "active" and d.get("processed")]

    query_tokens = set(re.findall(r'\b\w{3,}\b', query.lower()))
    if not query_tokens:
        return []

    all_scored = []
    for doc in active_docs:
        chunks = load_chunks(doc["id"])
        for chunk in chunks:
            chunk_tokens = set(re.findall(r'\b\w{3,}\b', chunk["text"].lower()))
            score = len(query_tokens & chunk_tokens)
            if score > 0:
                all_scored.append((score, doc["name"], chunk))

    all_scored.sort(key=lambda x: x[0], reverse=True)
    return [(name, chunk) for _, name, chunk in all_scored[:max_chunks]]

# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────
BASE_SYSTEM = """You are the CORENET X Knowledge Base AI — an authoritative assistant for Singapore's CORENET X regulatory submission platform.

IMPORTANT:
- Answer ONLY from the official document excerpts provided below.
- Do not invent requirements, numbers, or rules not present in the provided text.
- Always cite which document and page your answer comes from.
- Note if something is a Design Gateway (G1) vs Construction Gateway (G2) requirement — they differ significantly.
- SCDF fire suppression is ONLY a CG requirement, NOT a DG requirement.

RESPONSE FORMAT: Always respond in valid JSON:
{
  "answer": "<HTML using <p>, <ul>, <li>, <strong>, <h4> tags>",
  "confidence": <0-99>,
  "tier": "<A|B|C|D>",
  "tier_reason": "<one sentence>",
  "sources": ["<doc name p.XX>"],
  "key_point": "<most important sentence or null>",
  "follow_ups": ["<q1>", "<q2>", "<q3>"]
}

TIER RULES:
- A (≥85%): Directly answered by the provided excerpts. Cite exact page.
- B (70-84%): Partially answered; officer should verify.
- C (40-69%): Inferred from related content; officer should check.
- D (<40%): Not found in provided documents. Direct user to a CORENET X officer.

Respond ONLY with JSON. No preamble, no markdown outside the JSON.
"""

# Fallback KB context if no documents have been processed yet
FALLBACK_KB = """
FALLBACK KNOWLEDGE (use only if no document excerpts are provided):
- CORENET X: Singapore's multi-agency BIM regulatory platform. Mandatory 1 Oct 2025.
- 3 Gateways: G1 Design, G1.5 Piling (optional), G2 Construction, G3 Completion/TOP.
- 10 agencies: BCA, URA, GovTech, HDB, JTC, LTA, NEA, NParks, SCDF, SLA.
- BIM (IFC+SG) mandatory for GFA ≥ 5,000 m². Max file size: 800 MB per IFC file.
- Geo-reference: SVY21 (EPSG: 3414) + Singapore Height Datum. Orientation: True North.
- SCDF at DG: fire engine accessway ONLY. Fire suppression systems = CG requirement.
- NParks planting areas: min soil depth 2.0 m. IfcGeographicElement PLANTINGAREAS.
- Trees: IfcGeographicElement LANDSCAPE_TREE/PALM/HEDGE.
- Fire tanks: IfcTank (FIREFIGHTERSTORAGE). Sprinklers: IfcFireSuppressionTerminal.
- Validity: DG = 12 months, PG/CG = 24 months.
- Common myth: 2D drawings NOT required for BIM submissions.
"""

def build_system_prompt(retrieved_chunks):
    if retrieved_chunks:
        excerpts = "\n\n".join([
            f"[SOURCE: {doc_name}, Page {chunk['page']}]\n{chunk['text']}"
            for doc_name, chunk in retrieved_chunks
        ])
        return BASE_SYSTEM + f"\n\nOFFICIAL DOCUMENT EXCERPTS (answer from these):\n{excerpts}"
    else:
        return BASE_SYSTEM + "\n\n" + FALLBACK_KB + "\n\nNOTE: No documents have been processed yet. Answers are from the fallback summary only — upload and process PDFs in the Officer Dashboard for full accuracy."

# ─── CLAUDE API ───────────────────────────────────────────────────────────────
def ask_claude(question, history, retrieved_chunks):
    api_key = get_api_key()
    if not api_key:
        return {"answer": "<p>API key not configured.</p>", "confidence": 0, "tier": "D",
                "tier_reason": "No API key.", "sources": [], "key_point": None, "follow_ups": []}
    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": m["role"], "content": m.get("content", "")}
                for m in history[-6:] if m["role"] in ("user", "assistant")]
    messages.append({"role": "user", "content": question})
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1200,
            system=build_system_prompt(retrieved_chunks),
            messages=messages
        )
        raw = re.sub(r'^```(?:json)?\s*', '', resp.content[0].text.strip())
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        return {"answer": f"<p>Error: {e}</p>", "confidence": 0, "tier": "D",
                "tier_reason": "Error.", "sources": [], "key_point": None, "follow_ups": []}

# ─── KB UPDATE ANALYSIS ───────────────────────────────────────────────────────
def analyse_doc_for_kb_updates(doc_name, sample_chunks):
    """Ask Claude to review new doc chunks and identify what KB topics are affected."""
    api_key = get_api_key()
    if not api_key or not sample_chunks: return []
    client = anthropic.Anthropic(api_key=api_key)
    sample_text = "\n\n".join([c["text"] for c in sample_chunks[:15]])
    prompt = f"""You are reviewing a new/updated CORENET X document: "{doc_name}".

Document excerpts (first 15 chunks):
{sample_text}

Identify the key topics this document covers and any regulatory requirements it contains.
For each topic, indicate: topic name, brief description, what KB category it falls under, and urgency for update (High/Medium/Low).

Respond as JSON array:
[{{"topic": "...", "description": "...", "category": "...", "urgency": "High|Medium|Low", "sample_quote": "..."}}]

Respond ONLY with the JSON array."""

    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = re.sub(r'^```(?:json)?\s*', '', resp.content[0].text.strip())
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception:
        return []

# ─── AGENCY CONFIG ────────────────────────────────────────────────────────────
AGENCIES = ["BCA","URA","SCDF","HDB","JTC","LTA","NEA","NParks","SLA","GovTech","Other"]
AGENCY_COLORS = {
    "BCA":"#1a3c5e","URA":"#6b21a8","SCDF":"#dc2626","HDB":"#d97706",
    "JTC":"#0891b2","LTA":"#065f46","NEA":"#166534","NParks":"#15803d",
    "SLA":"#9a3412","GovTech":"#1d4ed8","Other":"#6b7280"
}
AGENCY_DOMAINS = {
    "BCA":  ["building control","structural","accessibility","GFA","floor area","height","storey","construction"],
    "URA":  ["planning","development","land use","zoning","plot ratio","setback","conservation","planning permission"],
    "SCDF": ["fire","sprinkler","suppression","emergency","evacuation","hose reel","detector","fire engine","SCDF"],
    "HDB":  ["public housing","HDB","residential flat","estate","HDB project"],
    "JTC":  ["industrial","warehouse","factory","JTC","logistics"],
    "LTA":  ["transport","traffic","road","parking","vehicle","LTA"],
    "NEA":  ["environment","waste","noise","pollution","NEA"],
    "NParks":["greenery","tree","plant","landscape","planting","soil depth","NParks"],
    "SLA":  ["land","survey","cadastral","boundary","SLA","lot number"],
    "GovTech":["digital","IFC","BIM","submission","portal","corenet","ifc-sg","model"],
}

def suggest_agency(question):
    """Auto-tag a query to the most likely reviewing agency."""
    q = question.lower()
    scores = {agency: sum(1 for kw in kws if kw in q) for agency, kws in AGENCY_DOMAINS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "GovTech"

def agency_badge(agency):
    color = AGENCY_COLORS.get(agency, "#6b7280")
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700">{agency}</span>'

# ─── HELPERS ──────────────────────────────────────────────────────────────────
TIER_LABELS = {"A": "✅ Verified (Tier A)", "B": "📋 Officer Reviewing (Tier B)",
               "C": "🤖 AI Draft (Tier C)", "D": "📞 Needs Officer (Tier D)"}

def conf_bar(conf, tier):
    c = {"A":"#1b6b3a","B":"#1a3c5e","C":"#d97706","D":"#dc2626"}.get(tier,"#6b7280")
    return f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0"><span style="font-size:13px;font-weight:700;color:{c}">{conf}%</span><div style="flex:1;height:6px;background:#e5e7eb;border-radius:3px"><div style="width:{conf}%;height:6px;background:{c};border-radius:3px"></div></div></div>'

# ─── SESSION STATE ────────────────────────────────────────────────────────────
for k, v in {"messages":[], "review_queue":[], "stats":{"asked":0,"resolved":0,"pending":0},
              "role":"user", "officer_authenticated":False, "pending_q":None, "custom_kb":[],
              "officer_name":"", "officer_agency":"GovTech",
              "private_mode":False, "private_messages":[]}.items():
    if k not in st.session_state: st.session_state[k] = v
if "registry" not in st.session_state or st.session_state["registry"] is None:
    st.session_state["registry"] = {"documents": [d.copy() for d in DEFAULT_REGISTRY["documents"]]}

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏗️ CORENET X KB")
    st.caption("Official Singapore government sources")
    if github_enabled():
        st.caption("🟢 GitHub sync active")
    else:
        st.caption("🟡 Session-only mode")

    st.divider()
    col1, col2 = st.columns(2)
    if col1.button("👤 User", use_container_width=True,
                   type="primary" if st.session_state.role=="user" else "secondary"):
        st.session_state.role = "user"; st.rerun()
    if col2.button("🔐 Officer", use_container_width=True,
                   type="primary" if st.session_state.role in ("officer","officer_login") else "secondary"):
        if st.session_state.officer_authenticated:
            st.session_state.role = "officer"
        else:
            st.session_state.role = "officer_login"
        st.rerun()

    if st.session_state.role == "officer_login":
        pw = st.text_input("Officer password", type="password", key="pw_input")
        off_name = st.text_input("Your name", key="off_name_input", placeholder="e.g. Ahmad Razali")
        off_agency = st.selectbox("Your agency", AGENCIES, key="off_agency_input")
        if st.button("Login", type="primary", use_container_width=True):
            if pw == get_officer_pw():
                st.session_state.officer_authenticated = True
                st.session_state.officer_name = off_name or "Officer"
                st.session_state.officer_agency = off_agency
                st.session_state.role = "officer"; st.rerun()
            else: st.error("Incorrect password")

    # Show officer identity if logged in
    if st.session_state.role == "officer" and st.session_state.officer_authenticated:
        ag = st.session_state.officer_agency
        color = AGENCY_COLORS.get(ag, "#6b7280")
        st.markdown(f'<div style="background:{color}22;border:1px solid {color};padding:8px 10px;border-radius:8px;margin:4px 0"><strong style="color:{color}">{ag}</strong><br><span style="font-size:12px">{st.session_state.officer_name}</span></div>', unsafe_allow_html=True)
        if st.button("🚪 Sign out", use_container_width=True):
            st.session_state.officer_authenticated = False
            st.session_state.officer_name = ""
            st.session_state.role = "user"; st.rerun()

    st.divider()

    # Private mode toggle (user side)
    if st.session_state.role == "user":
        private = st.toggle("🔒 Private / Confidential mode", value=st.session_state.private_mode,
                            help="Your questions and answers are NOT stored or shared. Use for project-specific or confidential queries.")
        if private != st.session_state.private_mode:
            st.session_state.private_mode = private
            if private:
                st.session_state.private_messages = []
            st.rerun()
        if st.session_state.private_mode:
            st.markdown('<div style="background:#fdeaea;border:1px solid #f5b8b8;padding:8px;border-radius:6px;font-size:12px">🔒 <strong>Private mode ON</strong><br>Nothing stored. Session only.</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("**📊 Session stats**")
    c1,c2,c3 = st.columns(3)
    c1.metric("Asked", st.session_state.stats["asked"])
    c2.metric("✅", st.session_state.stats["resolved"])
    c3.metric("⏳", st.session_state.stats["pending"])

    registry = load_registry()
    docs = registry.get("documents", [])
    processed = sum(1 for d in docs if d.get("processed") and d["status"]=="active")
    total_active = sum(1 for d in docs if d["status"]=="active")
    st.divider()
    st.markdown("**📚 Document coverage**")
    st.progress(processed / max(total_active, 1), text=f"{processed}/{total_active} docs processed")
    if processed == 0:
        st.caption("⚠️ No documents processed yet — using fallback KB.")
    else:
        st.caption(f"✅ {processed} document(s) indexed for live retrieval")

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.private_messages = []
        st.session_state.stats = {"asked":0,"resolved":0,"pending":0}
        st.rerun()

# ─── OFFICER DASHBOARD ────────────────────────────────────────────────────────
if st.session_state.role == "officer" and st.session_state.officer_authenticated:
    # ── Header with live stats ─────────────────────────────────────────────────
    st.markdown("## 🔐 Officer Dashboard")
    st.caption(f"Logged in · {datetime.now().strftime('%d %b %Y %H:%M')}")

    _reg = load_registry()
    _docs = _reg.get("documents", [])
    _total = len(_docs)
    _indexed = sum(1 for d in _docs if d.get("processed") and d["status"]=="active")
    _superseded = sum(1 for d in _docs if d["status"]=="superseded")
    _total_chunks = sum(d.get("chunk_count", 0) for d in _docs if d.get("processed"))
    _pending_q = sum(1 for q in st.session_state.review_queue if not q.get("reviewed"))
    _total_asked = st.session_state.stats.get("asked", 0)

    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("📚 Docs Indexed", f"{_indexed}/{_total}")
    m2.metric("🔍 Chunks in KB", f"{_total_chunks:,}")
    m3.metric("📋 Pending Review", _pending_q)
    m4.metric("💬 Total Queries", _total_asked)
    m5.metric("⛔ Superseded", _superseded)
    st.divider()

    _my_agency = st.session_state.officer_agency
    _my_name   = st.session_state.officer_name

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Review Queue", "🔍 Search KB", "📚 Documents", "✏️ KB Editor", "📧 Notifications"])

    # ── TAB 1: REVIEW QUEUE ───────────────────────────────────────────────────
    with tab1:
        rq = st.session_state.review_queue
        pending   = [q for q in rq if not q.get("reviewed") and not q.get("disputed")]
        disputed  = [q for q in rq if q.get("disputed") and not q.get("resolved")]
        reviewed  = [q for q in rq if q.get("reviewed") and not q.get("disputed")]

        # Summary metrics
        tier_counts = {}
        for q in rq:
            t = q.get("tier","?"); tier_counts[t] = tier_counts.get(t,0)+1
        tc1,tc2,tc3,tc4,tc5,tc6 = st.columns(6)
        tc1.metric("Total", len(rq))
        tc2.metric("🔵 Tier B", tier_counts.get("B",0))
        tc3.metric("🟡 Tier C", tier_counts.get("C",0))
        tc4.metric("🔴 Tier D", tier_counts.get("D",0))
        tc5.metric("✅ Tier A", tier_counts.get("A",0))
        tc6.metric("⚠️ Disputed", len(disputed))

        if not rq:
            st.info("No queries yet. Tier B/C/D questions from users appear here automatically.")
        else:
            # Filters
            f1, f2 = st.columns([2,2])
            show_filter = f1.radio("Show:", ["My agency first","Pending only","Disputed","All"], horizontal=True, key="rq_filter")
            agency_filter = f2.selectbox("Agency filter:", ["All agencies"] + AGENCIES, key="rq_agency")

            def _filter_queue(items):
                result = [(i,q) for i,q in enumerate(rq)]
                if show_filter == "Pending only":   result = [(i,q) for i,q in result if not q.get("reviewed") and not q.get("disputed")]
                elif show_filter == "Disputed":     result = [(i,q) for i,q in result if q.get("disputed")]
                elif show_filter == "My agency first":
                    result = sorted(result, key=lambda x: (x[1].get("suggested_agency","") != _my_agency, x[1].get("reviewed",False)))
                if agency_filter != "All agencies":
                    result = [(i,q) for i,q in result if q.get("suggested_agency","") == agency_filter]
                return result

            display_queue = _filter_queue(rq)
            st.caption(f"**{len(pending)} pending** · {len(disputed)} disputed · {len(reviewed)} reviewed · Showing {len(display_queue)} items")

            if pending and f1.button("🗑️ Dismiss all reviewed", key="dismiss_all"):
                for qi in rq: qi["reviewed"] = True
                st.rerun()

        for i, item in (display_queue if rq else []):
            icon = {"B":"🔵","C":"🟡","D":"🔴","A":"✅"}.get(item["tier"],"⚪")
            disp_icon = " ⚠️ DISPUTED" if item.get("disputed") else (" ✅" if item.get("reviewed") else " 🔴")
            sug_ag = item.get("suggested_agency","?")
            ag_color = AGENCY_COLORS.get(sug_ag,"#6b7280")
            is_my_domain = (sug_ag == _my_agency)
            border_style = f"border-left:4px solid {ag_color}"

            with st.expander(f"{icon} [{item['tier']}] {item['question'][:70]}…{disp_icon}"):
                # Agency tag + metadata row
                st.markdown(
                    f"{agency_badge(sug_ag)} &nbsp; Asked: {item.get('timestamp','')} · "
                    f"Conf: {item.get('conf',0)}% · "
                    f"{'👍' if item.get('feedback')=='up' else '👎' if item.get('feedback')=='down' else '—'} feedback · "
                    f"Email: {item.get('email','None')}",
                    unsafe_allow_html=True
                )
                if item.get("approved_by"):
                    st.caption(f"✅ Approved by: {item['approved_by']}")
                if item.get("disputed"):
                    st.error(f"⚠️ Disputed by **{item.get('disputed_by','unknown')}** ({item.get('dispute_agency','?')}): {item.get('dispute_reason','')}")

                st.markdown("**AI Answer:**")
                st.markdown(item.get("answer",""), unsafe_allow_html=True)
                if item.get("sources"): st.caption("📄 " + " · ".join(item["sources"]))
                if item.get("chunks_used"): st.caption(f"🔍 {item['chunks_used']}")
                st.markdown("---")

                ans = st.text_area("✏️ Official answer:", value=item.get("officer_answer",""), key=f"oa_{i}", height=90)
                c1,c2,c3,c4,c5 = st.columns(5)

                if c1.button("✅ Approve", key=f"app_{i}", type="primary"):
                    st.session_state.review_queue[i].update({
                        "officer_answer":ans,"reviewed":True,"tier":"A",
                        "approved_by":f"{_my_name} ({_my_agency})",
                        "approved_at":datetime.now().strftime("%d %b %Y %H:%M"),
                        "disputed":False
                    })
                    st.success(f"Approved by {_my_name}."); st.rerun()

                if c2.button("💾 Save Draft", key=f"sv_{i}"):
                    st.session_state.review_queue[i]["officer_answer"] = ans
                    st.session_state.review_queue[i]["draft_by"] = f"{_my_name} ({_my_agency})"
                    st.success("Draft saved.")

                if c3.button("➕ Add to KB", key=f"addkb_{i}"):
                    if ans:
                        ckb = load_custom_kb()
                        ckb.append({"q":item["question"],"a":ans,
                                    "src":" · ".join(item.get("sources",[])),
                                    "cat":sug_ag,"conf":90,
                                    "agency":_my_agency,"officer":_my_name,
                                    "added":datetime.now().strftime("%d %b %Y %H:%M")})
                        save_custom_kb(ckb); st.success("Added to KB!"); st.rerun()

                # Dispute button — only show on already-approved items
                if item.get("reviewed") and item.get("tier")=="A" and not item.get("disputed"):
                    if c4.button("⚠️ Dispute", key=f"disp_{i}"):
                        st.session_state[f"show_dispute_{i}"] = True
                    if st.session_state.get(f"show_dispute_{i}"):
                        dr = st.text_input("Reason for dispute:", key=f"dr_{i}", placeholder="e.g. Incorrect for HDB projects — refer to HDB circular 2024")
                        if st.button("Submit dispute", key=f"subdisp_{i}", type="primary"):
                            if dr:
                                st.session_state.review_queue[i].update({
                                    "disputed":True,"reviewed":False,
                                    "disputed_by":_my_name,"dispute_agency":_my_agency,
                                    "dispute_reason":dr,
                                    "disputed_at":datetime.now().strftime("%d %b %Y %H:%M")
                                })
                                del st.session_state[f"show_dispute_{i}"]
                                st.warning("Dispute raised. Item sent back for re-review."); st.rerun()
                else:
                    if c5.button("🗑️ Dismiss", key=f"dis_{i}"):
                        st.session_state.review_queue[i]["reviewed"] = True; st.rerun()

    # ── TAB 2: KB SEARCH (officer can test any query) ─────────────────────────
    with tab2:
        st.markdown("### 🔍 Search & Test the Knowledge Base")
        st.caption("Test any query as if you were a user. See exactly which document chunks were retrieved and why.")

        with st.form("officer_search_form"):
            osq = st.text_input("Enter any CORENET X question:", placeholder="e.g. What are the IFC requirements for fire tanks?")
            os_submitted = st.form_submit_button("🔍 Search KB", type="primary")

        if os_submitted and osq:
            with st.spinner("Retrieving chunks and generating answer…"):
                os_chunks = get_relevant_chunks(osq, max_chunks=8)
                os_result = ask_claude(osq, [], os_chunks)

            t = os_result.get("tier","D"); conf = os_result.get("confidence",0)
            tier_color = {"A":"#1b6b3a","B":"#1a3c5e","C":"#d97706","D":"#dc2626"}.get(t,"#6b7280")

            st.markdown(f'<span class="tier-{t}">{TIER_LABELS[t]}</span> &nbsp; <span style="color:{tier_color};font-weight:700">{conf}% confidence</span>', unsafe_allow_html=True)
            st.markdown(os_result.get("answer",""), unsafe_allow_html=True)

            if os_result.get("sources"):
                st.markdown(f'<div class="src-box">📄 <strong>Sources:</strong> {" · ".join(os_result["sources"])}</div>', unsafe_allow_html=True)

            if os_chunks:
                st.markdown(f"**📦 {len(os_chunks)} chunks retrieved:**")
                for doc_name, chunk in os_chunks:
                    with st.expander(f"📄 {doc_name} — Page {chunk['page']}"):
                        st.text(chunk["text"][:600] + ("…" if len(chunk["text"])>600 else ""))
            else:
                st.warning("No matching chunks found — answer came from fallback KB.")

            st.divider()
            st.caption(f"Tier reason: {os_result.get('tier_reason','')}")
            c1, c2 = st.columns(2)
            if c1.button("➕ Add this answer to KB", key="os_addkb"):
                custom_kb = load_custom_kb()
                custom_kb.append({"q":osq,"a":os_result.get("answer",""),"src":" · ".join(os_result.get("sources",[])),"cat":"Other","conf":conf,"added":datetime.now().strftime("%d %b %Y %H:%M")})
                save_custom_kb(custom_kb)
                st.success("Added to KB!")

        # Document coverage overview
        st.divider()
        st.markdown("**📊 Indexed document coverage:**")
        _r = load_registry()
        for d in _r.get("documents",[]):
            if d.get("processed") and d["status"]=="active":
                chunks = load_chunks(d["id"])
                pages_covered = len(set(c["page"] for c in chunks))
                st.markdown(f"🟢 **{d['name']}** — {d.get('chunk_count', len(chunks)):,} chunks · {pages_covered} pages covered · v{d['version']}")
            elif d["status"]=="superseded":
                st.markdown(f"⛔ ~~{d['name']}~~ — superseded")
            else:
                st.markdown(f"🔴 **{d['name']}** — not yet uploaded")

    # ── TAB 3: DOCUMENT REGISTRY ──────────────────────────────────────────────
    with tab3:
        st.markdown("### 📚 Document Registry")
        st.caption("Upload PDFs to enable live document-based answers. Mark old versions as superseded when updating.")

        registry = load_registry()
        docs = registry.get("documents", [])

        for i, doc in enumerate(docs):
            status = doc["status"]
            css = {"active":"doc-active","superseded":"doc-superseded"}.get(status,"doc-pending")
            processed_icon = "🟢" if doc.get("processed") else "🔴"
            st.markdown(f'<div class="{css}">', unsafe_allow_html=True)

            col_info, col_actions = st.columns([3,2])
            with col_info:
                st.markdown(f"**{doc['name']}** `v{doc['version']}`")
                st.caption(f"{processed_icon} {'Indexed' if doc.get('processed') else 'Not yet uploaded'} · {doc.get('pages',0) or '?'} pages · {doc.get('notes','')}")
                if doc.get("uploaded"): st.caption(f"Last uploaded: {doc['uploaded']}")

            with col_actions:
                # Upload new PDF
                uploaded_file = st.file_uploader(
                    f"Upload PDF", type=["pdf"], key=f"upload_{i}_{doc['id']}",
                    label_visibility="collapsed"
                )
                if uploaded_file and not doc.get("processed"):
                    with st.spinner(f"Extracting text from {doc['name']}…"):
                        if pdfplumber:
                            chunks = extract_chunks_from_pdf(uploaded_file)
                            if chunks:
                                save_chunks(doc["id"], chunks)
                                docs[i]["processed"] = True
                                docs[i]["pages"] = max((c["page"] for c in chunks), default=0)
                                docs[i]["uploaded"] = datetime.now().strftime("%d %b %Y %H:%M")
                                docs[i]["chunk_count"] = len(chunks)
                                registry["documents"] = docs
                                save_registry(registry)
                                st.success(f"✅ Extracted {len(chunks)} chunks from {doc['name']}")

                                # Run KB update analysis
                                with st.spinner("Analysing document for KB update prompts…"):
                                    updates = analyse_doc_for_kb_updates(doc["name"], chunks)
                                if updates:
                                    st.session_state[f"updates_{doc['id']}"] = updates
                                st.rerun()
                        else:
                            st.error("pdfplumber not installed. Add it to requirements.txt.")

                c1, c2 = st.columns(2)
                if status == "active" and c1.button("⚠️ Supersede", key=f"sup_{i}"):
                    docs[i]["status"] = "superseded"
                    registry["documents"] = docs
                    save_registry(registry); st.rerun()
                if status == "superseded" and c1.button("↩️ Restore", key=f"res_{i}"):
                    docs[i]["status"] = "active"
                    registry["documents"] = docs
                    save_registry(registry); st.rerun()
                if doc.get("processed") and c2.button("🔄 Re-process", key=f"rep_{i}"):
                    docs[i]["processed"] = False
                    registry["documents"] = docs
                    save_registry(registry); st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

            # Show KB update prompts if available
            updates = st.session_state.get(f"updates_{doc['id']}")
            if updates:
                st.info(f"📣 KB Update Prompts for **{doc['name']}** — {len(updates)} topics identified:")
                for u in updates:
                    urgency_color = {"High":"🔴","Medium":"🟡","Low":"🟢"}.get(u.get("urgency",""), "⚪")
                    with st.expander(f"{urgency_color} [{u.get('urgency','')}] {u.get('topic','')}"):
                        st.markdown(f"**Category:** {u.get('category','')} · **Description:** {u.get('description','')}")
                        if u.get("sample_quote"): st.caption(f'Quote: "{u["sample_quote"][:200]}…"')
                        st.markdown("Go to **KB Editor** tab to add or update the relevant KB entry.")
                if st.button(f"✅ Dismiss prompts for {doc['name']}", key=f"dismiss_upd_{doc['id']}"):
                    del st.session_state[f"updates_{doc['id']}"]
                    st.rerun()

        st.divider()
        st.markdown("**Add a new document to the registry:**")
        with st.form("add_doc_form"):
            nd_name = st.text_input("Document name")
            nd_ver = st.text_input("Version / date")
            nd_notes = st.text_input("Notes (e.g. which agency, topic)")
            nd_id = st.text_input("Short ID (no spaces, e.g. bca_circular_2026)")
            if st.form_submit_button("➕ Add document", type="primary"):
                if nd_name and nd_id:
                    clean_id = nd_id.replace(" ","_").lower()
                    existing_ids = [d["id"] for d in registry.get("documents", [])]
                    if clean_id in existing_ids:
                        st.error(f"ID '{clean_id}' already exists. Choose a different Short ID.")
                    else:
                        new_doc = {"id": clean_id, "name": nd_name,
                                   "version": nd_ver, "pages": 0, "status": "active",
                                   "processed": False, "uploaded": None, "notes": nd_notes}
                        registry["documents"].append(new_doc)
                        save_registry(registry)
                        st.success(f"Added '{nd_name}' — now upload the PDF above."); st.rerun()

    # ── TAB 4: KB EDITOR ──────────────────────────────────────────────────────
    with tab4:
        st.markdown("### ✏️ Knowledge Base Editor")
        st.caption("All officers see the full KB. Each entry is owned by the agency that created it — only that agency (or admin) should edit it.")

        custom_kb = load_custom_kb()

        # Agency filter
        kb_view = st.radio("View:", [f"My agency ({_my_agency})", "All agencies"], horizontal=True, key="kb_view")
        if kb_view.startswith("My"):
            visible_kb = [(j,e) for j,e in enumerate(custom_kb) if e.get("agency","")==_my_agency or not e.get("agency")]
        else:
            visible_kb = list(enumerate(custom_kb))

        # Group by agency
        if kb_view == "All agencies" and custom_kb:
            by_agency = {}
            for j, e in visible_kb:
                ag = e.get("agency","Other")
                by_agency.setdefault(ag,[]).append((j,e))
            for ag, entries in sorted(by_agency.items()):
                color = AGENCY_COLORS.get(ag,"#6b7280")
                st.markdown(f'<div style="border-left:4px solid {color};padding:4px 12px;margin:12px 0 4px"><strong style="color:{color}">{ag}</strong> — {len(entries)} entries</div>', unsafe_allow_html=True)
                for j, e in entries:
                    can_edit = (e.get("agency","") == _my_agency or not e.get("agency"))
                    lock = "" if can_edit else " 🔒"
                    with st.expander(f"[{e.get('cat','')}] {e['q'][:60]}…{lock}"):
                        st.markdown(e["a"])
                        st.caption(f"Source: {e.get('src','')} · Added by: {e.get('officer','unknown')} · {e.get('added','')} · Conf: {e.get('conf','')}%")
                        if can_edit:
                            if st.button("🗑️ Remove", key=f"rmkb_{j}"):
                                custom_kb.pop(j); save_custom_kb(custom_kb); st.rerun()
                        else:
                            st.caption(f"🔒 Owned by {ag}. Raise a dispute if you disagree.")
        else:
            if visible_kb:
                st.markdown(f"**{len(visible_kb)} entries for {_my_agency}:**")
                for j, e in visible_kb:
                    with st.expander(f"[{e.get('cat','')}] {e['q'][:60]}…"):
                        st.markdown(e["a"])
                        st.caption(f"Source: {e.get('src','')} · {e.get('added','')} · Conf: {e.get('conf','')}%")
                        if st.button("🗑️ Remove", key=f"rmkb_{j}"):
                            custom_kb.pop(j); save_custom_kb(custom_kb); st.rerun()
            else:
                st.info(f"No KB entries owned by {_my_agency} yet. Add one below.")

        st.divider()
        st.markdown("**➕ Add new entry** (will be owned by your agency)")
        with st.form("kb_form"):
            kq = st.text_input("Question")
            ka = st.text_area("Answer", height=100)
            ks = st.text_input("Source reference (document + page)")
            kc = st.selectbox("Category", ["Overview","Design Gateway","Construction Gateway",
                                            "BIM & IFC+SG","External Works","Greenery & Trees","Process","Other"])
            kconf = st.slider("Confidence %", 50, 99, 90)
            if st.form_submit_button("➕ Add to KB", type="primary"):
                if kq and ka:
                    custom_kb.append({"q":kq,"a":ka,"src":ks,"cat":kc,"conf":kconf,
                                      "agency":_my_agency,"officer":_my_name,
                                      "added":datetime.now().strftime("%d %b %Y %H:%M")})
                    save_custom_kb(custom_kb); st.success("Entry added."); st.rerun()

    # ── TAB 5: EMAIL NOTIFICATIONS ────────────────────────────────────────────
    with tab5:
        with_email = [q for q in st.session_state.review_queue if q.get("email")]
        st.markdown(f"**{len(with_email)} queries with user email**")
        if not with_email:
            st.info("No user emails yet. They appear when users submit their email on Tier B/C/D answers.")
        for item in with_email:
            with st.expander(f"📧 {item['email']} — {item['question'][:55]}…"):
                ans_text = item.get("officer_answer","")
                if not ans_text:
                    st.warning("Write official answer in Review Queue tab first.")
                else:
                    body = f"""Dear User,\n\nThank you for your query via the CORENET X Knowledge Base.\n\nYour question: {item['question']}\n\nOfficial Response:\n{ans_text}\n\nSources: {', '.join(item.get('sources',[]))}\n\nIf you have further questions, please visit the CORENET X portal.\n\nRegards,\nCORENET X Knowledge Base Team"""
                    st.code(body, language=None)
                    st.markdown(f"[📨 Open in email client](mailto:{item['email']}?subject=CORENET%20X%20Query%20Response&body={body[:800].replace(chr(10),'%0A').replace(' ','%20')})")

# ─── USER CHAT INTERFACE ──────────────────────────────────────────────────────
else:
    if st.session_state.role not in ("officer_login",):
        # Header
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a3c5e 0%,#0f2540 100%);padding:24px 28px;border-radius:12px;margin-bottom:20px">
          <h2 style="color:#fff;margin:0;font-size:26px">🏗️ CORENET X Knowledge Base</h2>
          <p style="color:#a8c4e0;margin:6px 0 0;font-size:14px">Official Singapore government sources · Powered by Claude AI</p>
        </div>
        """, unsafe_allow_html=True)

        registry = load_registry()
        docs = registry.get("documents", [])
        processed_count = sum(1 for d in docs if d.get("processed") and d["status"]=="active")
        total_chunks = sum(d.get("chunk_count",0) for d in docs if d.get("processed"))

        # Live status bar
        if processed_count > 0:
            st.markdown(f'<div style="background:#e8f5ec;border:1px solid #a8d5b5;padding:8px 14px;border-radius:8px;font-size:13px;margin-bottom:16px">✅ <strong>Live mode</strong> — answering from {processed_count} indexed document(s) · {total_chunks:,} searchable chunks</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="background:#fff3e0;border:1px solid #ffd580;padding:8px 14px;border-radius:8px;font-size:13px;margin-bottom:16px">⚠️ <strong>Fallback mode</strong> — using built-in summaries. Upload PDFs in Officer Dashboard for full accuracy.</div>', unsafe_allow_html=True)

        # Starter questions with category tabs
        if not st.session_state.messages:
            st.markdown("### 💡 Browse by topic or just start typing below")
            STARTER_CATEGORIES = {
                "🏛️ Overview": [
                    "What is CORENET X?",
                    "What are the 3 key gateways?",
                    "Which agencies are involved?",
                    "What are the validity periods?",
                ],
                "📐 Design Gateway": [
                    "What does SCDF require at Design Gateway?",
                    "Do I need to model soil depth at DG?",
                    "External works at Design Gateway?",
                    "What is the minimum planting area soil depth?",
                ],
                "🏗️ Construction Gateway": [
                    "What are fire suppression requirements at CG?",
                    "What changes between DG and CG submissions?",
                    "Construction Gateway IFC requirements?",
                ],
                "📦 BIM & IFC+SG": [
                    "Do I need 2D drawings for BIM?",
                    "How do I model trees in IFC+SG?",
                    "What do I need for a fire tank?",
                    "What is the max IFC file size?",
                ],
            }
            cat_tabs = st.tabs(list(STARTER_CATEGORIES.keys()))
            for cat_tab, (cat_name, questions) in zip(cat_tabs, STARTER_CATEGORIES.items()):
                with cat_tab:
                    cols = st.columns(2)
                    for qi, q in enumerate(questions):
                        if cols[qi%2].button(q, key=f"s_{cat_name}_{qi}", use_container_width=True):
                            st.session_state.pending_q = q; st.rerun()

        # Render messages
        for msg_idx, msg in enumerate(st.session_state.messages):
            if msg["role"] == "user":
                st.markdown(f'<div style="text-align:right;margin:12px 0"><div class="user-bubble">{msg["content"]}</div></div>', unsafe_allow_html=True)
            else:
                r = msg["data"]; t = r.get("tier","D"); conf = r.get("confidence",0)
                with st.container(border=True):
                    hc1, hc2 = st.columns([3,1])
                    with hc1:
                        st.markdown(f'<span class="tier-{t}">{TIER_LABELS[t]}</span> <span style="font-size:11px;color:#6b7280">{r.get("tier_reason","")}</span>', unsafe_allow_html=True)
                        st.markdown(conf_bar(conf, t), unsafe_allow_html=True)
                    with hc2:
                        # Feedback buttons
                        if not msg.get("feedback"):
                            fb1, fb2 = st.columns(2)
                            if fb1.button("👍", key=f"fb_up_{msg_idx}", help="Helpful"):
                                msg["feedback"] = "up"
                                for qi in st.session_state.review_queue:
                                    if qi.get("question") == msg.get("question"): qi["feedback"] = "up"
                                st.rerun()
                            if fb2.button("👎", key=f"fb_dn_{msg_idx}", help="Not helpful"):
                                msg["feedback"] = "down"
                                for qi in st.session_state.review_queue:
                                    if qi.get("question") == msg.get("question"): qi["feedback"] = "down"
                                st.rerun()
                        else:
                            st.caption("👍 Thanks!" if msg["feedback"]=="up" else "👎 Noted")

                    if msg.get("chunks_used"):
                        st.caption(f"🔍 Retrieved from: {msg['chunks_used']}")
                    if r.get("key_point"):
                        st.markdown(f'<div class="kp-box">📌 <strong>Key point:</strong> {r["key_point"]}</div>', unsafe_allow_html=True)
                    st.markdown(r.get("answer",""), unsafe_allow_html=True)
                    if r.get("sources"):
                        st.markdown(f'<div class="src-box">📄 <strong>Sources:</strong> {" · ".join(r["sources"])}</div>', unsafe_allow_html=True)
                    if t == "A":
                        st.success("✅ Verified from official documents")
                    else:
                        notices = {
                            "B":"📬 **Officer reviewing** — this answer is partially verified. An officer will review shortly.",
                            "C":"🤖 **AI-drafted** — based on related content. Officer verification recommended before acting on this.",
                            "D":"📞 **Needs officer guidance** — this topic wasn't found in the indexed documents."
                        }
                        st.warning(notices.get(t,""))
                        if not msg.get("email_submitted"):
                            st.markdown("**Get notified when an officer responds:**")
                            ec, bc = st.columns([3,1])
                            em = ec.text_input("Your email:", key=f"em_{msg_idx}", label_visibility="collapsed", placeholder="your@email.com")
                            if bc.button("Notify me →", key=f"nb_{msg_idx}", type="primary"):
                                if em:
                                    msg["email_submitted"] = True; msg["user_email"] = em
                                    for qi in st.session_state.review_queue:
                                        if qi.get("question") == msg.get("question"): qi["email"] = em
                                    st.success(f"✅ We'll notify {em} when an officer responds."); st.rerun()
                        else:
                            st.caption(f"✅ Officer response will be sent to {msg.get('user_email','')}")
                    if r.get("follow_ups"):
                        st.markdown("**You might also want to ask:**")
                        fc = st.columns(len(r["follow_ups"]))
                        for i, fq in enumerate(r["follow_ups"]):
                            if fc[i].button(f"💬 {fq}", key=f"fu_{msg_idx}_{i}", use_container_width=True):
                                st.session_state.pending_q = fq; st.rerun()

        # Input
        st.markdown("---")
        is_private = st.session_state.get("private_mode", False)
        if is_private:
            st.markdown('<div style="background:#fdeaea;border:1px solid #f5b8b8;padding:6px 12px;border-radius:6px;font-size:12px;margin-bottom:8px">🔒 <strong>Private mode</strong> — your question will be answered from the KB but nothing will be stored or shared with officers.</div>', unsafe_allow_html=True)

        with st.form("chat_form", clear_on_submit=True):
            ic, bc = st.columns([5,1])
            placeholder = "Ask a confidential project question…" if is_private else "Ask anything about CORENET X…"
            user_input = ic.text_input(placeholder, label_visibility="collapsed", placeholder="e.g. What does SCDF require at Design Gateway?")
            submitted = bc.form_submit_button("Send ➤", use_container_width=True, type="primary")

        pending = st.session_state.pending_q
        if pending: user_input = pending; submitted = True; st.session_state.pending_q = None

        if submitted and user_input and user_input.strip():
            q = user_input.strip()
            suggested_ag = suggest_agency(q)

            if is_private:
                # ── PRIVATE MODE: answer only, nothing stored ──────────────────
                st.session_state.private_messages.append({"role":"user","content":q})
                with st.spinner("Searching KB (private)…"):
                    chunks = get_relevant_chunks(q)
                    result = ask_claude(q, [], chunks)
                chunks_label = ", ".join(set(f"{name} p.{c['page']}" for name, c in chunks)) if chunks else None
                st.session_state.private_messages.append({
                    "role":"assistant","content":result.get("answer",""),
                    "data":result,"chunks_used":chunks_label
                })
                # Render private conversation inline
                st.rerun()
            else:
                # ── NORMAL MODE ────────────────────────────────────────────────
                st.session_state.messages.append({"role":"user","content":q,"question":q})
                history = [{"role":m["role"],"content":m.get("content","")} for m in st.session_state.messages[:-1]]
                with st.spinner("Searching documents…"):
                    chunks = get_relevant_chunks(q)
                    result = ask_claude(q, history, chunks)
                chunks_label = ", ".join(set(f"{name} p.{c['page']}" for name, c in chunks)) if chunks else None
                st.session_state.messages.append({
                    "role":"assistant","content":result.get("answer",""),
                    "data":result,"question":q,"chunks_used":chunks_label
                })
                t = result.get("tier","D")
                st.session_state.stats["asked"] += 1
                if t == "A": st.session_state.stats["resolved"] += 1
                else:
                    st.session_state.stats["pending"] += 1
                    st.session_state.review_queue.append({
                        "question":q,"tier":t,"conf":result.get("confidence",0),
                        "answer":result.get("answer",""),"sources":result.get("sources",[]),
                        "chunks_used":chunks_label,"email":None,
                        "suggested_agency":suggested_ag,
                        "timestamp":datetime.now().strftime("%d %b %Y %H:%M"),
                        "reviewed":False,"officer_answer":"","disputed":False
                    })
                st.rerun()

        # Render private messages (shown above input when in private mode)
        if is_private and st.session_state.private_messages:
            st.markdown("---")
            st.markdown('<div style="background:#fdeaea;border:1px solid #f5b8b8;padding:6px 12px;border-radius:6px;font-size:12px;margin:8px 0">🔒 Private session — visible only to you, cleared when you leave this page or turn off private mode.</div>', unsafe_allow_html=True)
            for pm in st.session_state.private_messages:
                if pm["role"] == "user":
                    st.markdown(f'<div style="text-align:right;margin:8px 0"><div class="user-bubble">{pm["content"]}</div></div>', unsafe_allow_html=True)
                else:
                    r = pm.get("data",{}); t = r.get("tier","D")
                    with st.container(border=True):
                        st.markdown(f'<span class="tier-{t}">{TIER_LABELS[t]}</span>', unsafe_allow_html=True)
                        if pm.get("chunks_used"): st.caption(f"🔍 {pm['chunks_used']}")
                        if r.get("key_point"): st.markdown(f'<div class="kp-box">📌 {r["key_point"]}</div>', unsafe_allow_html=True)
                        st.markdown(r.get("answer",""), unsafe_allow_html=True)
                        if r.get("sources"): st.markdown(f'<div class="src-box">📄 {" · ".join(r["sources"])}</div>', unsafe_allow_html=True)
            if st.button("🗑️ Clear private session", key="clear_private"):
                st.session_state.private_messages = []; st.rerun()
