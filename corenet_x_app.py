"""
CORENET X Knowledge Base — Interactive Streamlit App
Answers from 12 official Singapore government documents via Claude AI.

SETUP:
  pip install streamlit anthropic
  export ANTHROPIC_API_KEY="sk-ant-..."
  export OFFICER_PASSWORD="your-officer-password"   (optional, default: cx-officer-2025)
  streamlit run corenet_x_app.py
"""

import streamlit as st
import anthropic
import json, os, re
from datetime import datetime

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CORENET X Knowledge Base",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Config ───────────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"   # Fixed — do not expose model switcher

def get_api_key():
    try: return st.secrets["ANTHROPIC_API_KEY"]
    except: return os.environ.get("ANTHROPIC_API_KEY", "")

def get_officer_password():
    try: return st.secrets["OFFICER_PASSWORD"]
    except: return os.environ.get("OFFICER_PASSWORD", "cx-officer-2025")

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
.officer-badge{background:#7c3aed;color:#fff;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700}
</style>
""", unsafe_allow_html=True)

# ─── Knowledge Base context ────────────────────────────────────────────────────
KB_CONTEXT = """
OFFICIAL CORENET X KNOWLEDGE BASE
Sources: COP v3.1 (Dec 2025, 442 pp), RABW Mar 2026 (181 pp), IFC-SG Revit SP Guide Sep 2025 (176 pp).
ALL Singapore government official documents only. No private firm content.

== OVERVIEW ==
Q: What is CORENET X?
A: CORENET X is Singapore's multi-agency One-Stop Integrated Digital Shopfront for regulatory processes in the built environment — one 3D BIM model reviewed simultaneously by up to 10 agencies.
- Led by BCA and URA; agencies: HDB, JTC, LTA, NEA, NParks, SCDF, SLA, GovTech
- Soft-launched 18 December 2023; MANDATORY from 1 October 2025
- Replaces 20+ separate approval stages with 3 Key Gateways
- Industry submits once; agencies respond collectively
Source: COP v3.1 §1 pp.8–10

Q: What are the 3 key gateways?
A: G1 Design Gateway — critical design parameters (showstoppers). URA Planning Permission, LTA/NEA/PUB/NParks DC Clearances.
G1.5 Piling Gateway (optional) — structural design for piling/foundations before ground-breaking.
G2 Construction Gateway — detailed design before piling or sales launch. All agency detailed approvals.
G3 Completion / TOP — compliance to approved design. Agency clearances trigger overall TOP/CSC.
Source: COP v3.1 §3 Overview p.95

Q: When is CORENET X mandatory?
A: 1 Oct 2025: mandatory for all new projects regardless of GFA.
1 Oct 2026: mandatory for GFA ≥ 30,000 m².
1 Oct 2027: onboard ongoing projects.
BIM (IFC+SG) format mandatory only for GFA ≥ 5,000 m².
Source: RABW Mar 2026 p.21

Q: Which agencies are involved?
A: 10 agencies: BCA (co-lead), URA (co-lead), GovTech (platform), HDB, JTC, LTA, NEA, NParks, SCDF, SLA. Agencies review submissions collectively and issue a consolidated Written Direction.
Source: COP v3.1 §1 p.8

== DESIGN GATEWAY (G1) ==
Q: What does each agency require at Design Gateway?
A: BCA: NIL at DG. Complex buildings require pre-consultation before Piling Gateway.
LTA: Access points, parking provision, frontage improvement, commuter facilities.
NEA: Refuse location/size, cooling tower setback (5 m), pollution control buffers.
NParks: Planting areas (3 m/5 m green buffers), tree conservation, Arborist report.
PUB: Minimum Platform Level, peak run-off C ≤ 0.55, drainage concept, sewer connection.
SCDF: Fire engine accessway location and width ONLY (fire suppression is a CG requirement, NOT DG).
URA: Building massing, site layout, land use/GFA/GPR, connectivity, greenery.
Source: COP v3.1 §3 DG Summary pp.108–126

Q: What are planting area / soil depth requirements at Design Gateway?
A: NParks requires planting areas modelled at DG. Key rules:
- Minimum soil depth: 2.0 m (underground structures must be recessed ≥ 2.0 m below planting areas)
- Green Buffers: 3.0 m setback (along boundaries) or 5.0 m (along roads)
- Peripheral Planting Verges: 2.0 m
- Model using IfcGeographicElement SubType PLANTINGAREAS
- Properties: Area (m²), Status, Turf (Boolean), TurfSpecies, ApprovedSoilMixture, Compensated
- Compensated and encroached areas modelled as separate elements
Source: COP v3.1 §4 Planting Areas p.324

== EXTERNAL WORKS ==
Q: What is required for external works at Design Gateway?
A: External Works = proposed works OUTSIDE the development boundary. Submissions may be in 2D CAD.
LTA (pp.183–186): Horizontal alignment and junction layout of new/modified roads; road vertical profile; development access levels; tree affected plan; layout of drains/sumps/box culverts; commuter facilities (covered linkways, bus stops, POBs); cycling paths.
NParks (pp.190–191): Conservation of trees (TCOT, Heritage, EIA/EMMP) — Arborist report required; green verges.
PUB (pp.193–195): Peak run-off C value ≤ 0.55; roadside drain capacity; sewer connection point; Drainage Reserve location and width.
Source: COP v3.1 §3 External Works pp.178–196

Q: Can external works be delinked?
A: Yes — conditional delinking at Construction Gateway if internal works are in order but external works still under review.
Cannot be delinked: LTA/NParks access points, covered linkways, POB connections, bus stops; PUB drain connections, MPL/outlet levels, sewer connection point.
Source: COP v3.1 §3 External Works pp.178–179

== CONSTRUCTION GATEWAY (G2) ==
Q: What does SCDF require at Construction Gateway for fire suppression?
A: Full fire safety design at CG (NOT Design Gateway):
- Fire cisterns/firefighting water storage tanks — capacity, location, fire engine access
- Wet/dry pipe sprinkler systems — coverage, zoning, flow calculations
- Hose reels, fire hydrants — location, spacing
- Rising mains (wet and dry risers) — location, sizing
- Means of escape: travel distances, staircase widths, pressurisation
- Fire compartmentation: fire-rated walls/floors, compartment sizes
- Smoke control: mechanical ventilation/extraction
- Emergency Voice Communication (EVC) and Automatic Fire Alarm (AFA)
NOTE: SCDF at Design Gateway = fire engine accessway ONLY.
Source: COP v3.1 §3 CG SCDF pp.130–135

== BIM & IFC+SG ==
Q: What is IFC+SG?
A: Singapore's customised openBIM standard extending IFC4 with SGPsets (Singapore-localised property sets). Mandatory for GFA ≥ 5,000 m². Resource Kit: go.gov.sg/ifcsg. Supported: Autodesk Revit, Graphisoft ArchiCAD, Bentley OpenBuildings Designer.
Source: COP v3.1 Preamble p.4

Q: How do I model trees in IFC+SG?
A: IfcGeographicElement subtypes: LANDSCAPE_TREE, LANDSCAPE_PALM, LANDSCAPE_HEDGE.
Required: Girth (mm), Height (mm), Species, Status (Proposed/Existing/To be removed/To be transplanted), TreeNumber (T001...), Roadside (Boolean).
Simplified lollipop components allowed if IFC+SG properties embedded. Base point at base of tree.
Source: COP v3.1 §4 Landscape Plants pp.308–309

Q: How do I model fire tanks / fire suppression in IFC+SG?
A: Fire tank/cistern: IfcTank with IfcObjectType FIREFIGHTERSTORAGE. Properties: Capacity (m³), Location, Status.
Sprinklers/hose reels/hydrants: IfcFireSuppressionTerminal — subtypes SPRINKLERHEAD, HOSEREEL, FIREHYDRANT.
Rising mains: IfcPipeSegment for pipe runs; IfcPipeTerminal for outlets.
Source: COP v3.1 §4 Identified Components pp.247–260

Q: What is the maximum BIM file size?
A: 800 MB per IFC file. Recommended: 1 block per IFC file. Split by zones/levels if a block exceeds 800 MB. All disciplines (Arch, C&S, MEP) must be coordinated before submission.
Source: IFC-SG SP Guide Sep 2025 p.9

Q: How do I geo-reference my BIM model?
A: Easting/Northing: SVY21 (EPSG: 3414). Height: Singapore Height Datum (SHD). Orientation: True North.
In Revit: Manage > Coordinates > Specify Coordinates at a Point.
Source: IFC-SG SP Guide Sep 2025 pp.126–136

== PROCESS ==
Q: Do I need 2D drawings for BIM submissions?
A: No — 2D drawings NOT required for BIM submissions. Exception: complex details impractical to model in 3D. External Works may be submitted in 2D CAD.
Source: RABW Mar 2026 p.134 (Misconception #3)

Q: Common misconceptions about CORENET X?
A: Myth 1: Only QPs involved — False. Developers, Builders, RE/RTO, Accredited Checkers also interact.
Myth 2: All projects must submit in BIM — False. BIM mandatory only for GFA ≥ 5,000 m².
Myth 3: 3D BIM still requires 2D drawings — False. 2D generally NOT required.
Myth 4: All requirements must be cleared at gateways — False. Certain requirements can be submitted separately.
Myth 5: Demolition waits for main building works — False. Demolition can proceed independently.
Myth 6: Must restart if clearance not in 2 iterations — False. Submissions can go beyond 2 iterations.
Source: RABW Mar 2026 pp.134–135

Q: What are the validity periods for gateway clearances?
A: Design Gateway: 12 months. Piling Gateway: 24 months. Construction Gateway: 24 months. CSC: within 2 years of TOP.
Source: RABW Mar 2026 p.105

Q: How does the joint submission process work?
A: 1. Project Coordinator creates project on CORENET X Submission Portal.
2. Developer/Owner logs in via Singpass to appoint QPs.
3. QPs input data, upload model and documents, declare accuracy.
4. Team pays fees via CORENET Pay.
5. Agencies collaborate and process plans in 20 working days.
6. Agencies issue clearance or consolidated Written Direction.
Source: RABW Mar 2026 pp.101–103
"""

SYSTEM_PROMPT = f"""You are the CORENET X Knowledge Base AI — an authoritative, helpful assistant for Singapore's CORENET X regulatory submission platform.

Answer ONLY from the official sources below. Do not invent requirements, numbers, or rules not present in the knowledge base.

{KB_CONTEXT}

RESPONSE FORMAT: Always respond in valid JSON with this exact structure:
{{
  "answer": "<HTML-formatted answer using <p>, <ul>, <li>, <strong>, <h4> tags. Be specific and cite sections.>",
  "confidence": <integer 0-99>,
  "tier": "<A|B|C|D>",
  "tier_reason": "<one sentence>",
  "sources": ["<source 1>", "<source 2>"],
  "key_point": "<most important single sentence, or null>",
  "follow_ups": ["<follow-up 1>", "<follow-up 2>", "<follow-up 3>"]
}}

TIER RULES:
- Tier A (≥85%): Directly answered by the KB. Cite exact section/page.
- Tier B (70–84%): Partially answered; officer should review.
- Tier C (40–69%): AI inference from related content; officer should verify.
- Tier D (<40%): Not in KB. Direct user to contact a CORENET X officer.

CRITICAL: Never invent specific numbers. Note if something is DG vs CG (they differ significantly). Respond ONLY with JSON.
"""

# ─── Session state init ────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "messages": [],
        "review_queue": [],
        "kb_additions": [],
        "stats": {"asked": 0, "resolved": 0, "pending": 0},
        "role": "user",
        "officer_authenticated": False,
        "officer_pw_input": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ─── API call ──────────────────────────────────────────────────────────────────
def ask_claude(question: str, history: list) -> dict:
    api_key = get_api_key()
    if not api_key:
        return {"answer": "<p>API key not configured.</p>", "confidence": 0,
                "tier": "D", "tier_reason": "No API key.", "sources": [],
                "key_point": None, "follow_ups": []}
    client = anthropic.Anthropic(api_key=api_key)
    messages = []
    for m in history[-6:]:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m.get("content", "")})
    messages.append({"role": "user", "content": question})
    try:
        resp = client.messages.create(model=MODEL, max_tokens=1024,
                                      system=SYSTEM_PROMPT, messages=messages)
        raw = resp.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        return {"answer": f"<p>Error: {e}</p>", "confidence": 0, "tier": "D",
                "tier_reason": "Error.", "sources": [], "key_point": None, "follow_ups": []}

# ─── Helpers ───────────────────────────────────────────────────────────────────
TIER_LABELS = {"A": "✅ Verified (Tier A)", "B": "📋 Officer Reviewing (Tier B)",
               "C": "🤖 AI Draft (Tier C)", "D": "📞 Needs Officer (Tier D)"}

def conf_bar(conf, tier):
    colors = {"A": "#1b6b3a", "B": "#1a3c5e", "C": "#d97706", "D": "#dc2626"}
    c = colors.get(tier, "#6b7280")
    return f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0"><span style="font-size:13px;font-weight:700;color:{c}">{conf}%</span><div style="flex:1;height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden"><div style="width:{conf}%;height:6px;background:{c};border-radius:3px"></div></div></div>'

# ─── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏗️ CORENET X KB")
    st.caption("12 Official Sources · COP v3.1 Dec 2025")
    st.divider()

    # Role toggle
    col1, col2 = st.columns(2)
    if col1.button("👤 User", use_container_width=True,
                   type="primary" if st.session_state.role == "user" else "secondary"):
        st.session_state.role = "user"
        st.rerun()
    if col2.button("🔐 Officer", use_container_width=True,
                   type="primary" if st.session_state.role == "officer" else "secondary"):
        if not st.session_state.officer_authenticated:
            st.session_state.role = "officer_login"
        else:
            st.session_state.role = "officer"
        st.rerun()

    # Officer login gate
    if st.session_state.role == "officer_login":
        st.warning("Enter officer password")
        pw = st.text_input("Password", type="password", key="pw_field")
        if st.button("Login", type="primary"):
            if pw == get_officer_password():
                st.session_state.officer_authenticated = True
                st.session_state.role = "officer"
                st.rerun()
            else:
                st.error("Incorrect password")

    st.divider()

    # Stats
    st.markdown("**📊 Session stats**")
    c1, c2, c3 = st.columns(3)
    c1.metric("Asked", st.session_state.stats["asked"])
    c2.metric("✅", st.session_state.stats["resolved"])
    c3.metric("⏳", st.session_state.stats["pending"])

    st.divider()
    st.markdown("**📁 Sources**")
    st.caption("COP v3.1 (Dec 2025, 442 pp)")
    st.caption("RABW Mar 2026 (181 pp)")
    st.caption("IFC-SG SP Guide Sep 2025 (176 pp)")
    st.caption("+ 9 more official SG govt docs")

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.stats = {"asked": 0, "resolved": 0, "pending": 0}
        st.rerun()

# ─── OFFICER DASHBOARD ─────────────────────────────────────────────────────────
if st.session_state.role == "officer" and st.session_state.officer_authenticated:
    st.markdown("## 🔐 Officer Dashboard")
    st.markdown('<span class="officer-badge">OFFICER MODE</span>', unsafe_allow_html=True)
    st.caption(f"Logged in · {datetime.now().strftime('%d %b %Y %H:%M')}")

    tab1, tab2, tab3 = st.tabs(["📋 Review Queue", "📚 KB Editor", "📧 Email Notifications"])

    # ── TAB 1: REVIEW QUEUE ────────────────────────────────────────────────────
    with tab1:
        pending_items = [q for q in st.session_state.review_queue if not q.get("reviewed")]
        reviewed_items = [q for q in st.session_state.review_queue if q.get("reviewed")]

        st.markdown(f"**{len(pending_items)} pending** · {len(reviewed_items)} reviewed")

        if not st.session_state.review_queue:
            st.info("No queries yet. Questions from users appear here when confidence is below 85% (Tier B/C/D).")
        else:
            for i, item in enumerate(st.session_state.review_queue):
                tier_color = {"B": "🔵", "C": "🟡", "D": "🔴"}.get(item["tier"], "⚪")
                reviewed_label = " ✅ Reviewed" if item.get("reviewed") else ""
                with st.expander(f"{tier_color} [{item['tier']}] {item['question'][:80]}…{reviewed_label}"):
                    st.markdown(f"**Asked:** {item.get('timestamp', 'Unknown')}")
                    st.markdown(f"**Confidence:** {item.get('conf', 0)}% · **Tier:** {item['tier']}")
                    st.markdown(f"**User email:** {item.get('email', 'Not provided')}")
                    st.markdown("**AI Answer:**")
                    st.markdown(item.get("answer", ""), unsafe_allow_html=True)
                    if item.get("sources"):
                        st.caption("Sources: " + " · ".join(item["sources"]))

                    st.markdown("---")
                    st.markdown("**Officer Response:**")
                    officer_ans = st.text_area(
                        "Write official answer (will upgrade to Tier A):",
                        value=item.get("officer_answer", ""),
                        key=f"oa_{i}",
                        height=120
                    )
                    col_a, col_b, col_c = st.columns(3)
                    if col_a.button("✅ Approve & Upgrade to Tier A", key=f"approve_{i}"):
                        st.session_state.review_queue[i]["officer_answer"] = officer_ans
                        st.session_state.review_queue[i]["reviewed"] = True
                        st.session_state.review_queue[i]["tier"] = "A"
                        st.success("Marked as Tier A — verified answer recorded.")
                        st.rerun()
                    if col_b.button("💾 Save Draft", key=f"save_{i}"):
                        st.session_state.review_queue[i]["officer_answer"] = officer_ans
                        st.success("Draft saved.")
                        st.rerun()
                    if col_c.button("🗑️ Dismiss", key=f"dismiss_{i}"):
                        st.session_state.review_queue[i]["reviewed"] = True
                        st.rerun()

    # ── TAB 2: KB EDITOR ───────────────────────────────────────────────────────
    with tab2:
        st.markdown("**Add a new Knowledge Base entry**")
        st.caption("New entries are active for this session. To make them permanent, contact your admin to update the app code.")

        with st.form("kb_add_form"):
            new_q = st.text_input("Question")
            new_a = st.text_area("Answer (plain text or HTML)", height=150)
            new_src = st.text_input("Source (e.g. COP v3.1 §3 p.110)")
            new_cat = st.selectbox("Category", ["Overview", "Design Gateway", "External Works",
                                                  "Construction Gateway", "Completion Gateway",
                                                  "BIM & IFC+SG", "Greenery & Trees", "Process"])
            new_conf = st.slider("Confidence %", 40, 99, 85)
            submitted = st.form_submit_button("➕ Add to KB", type="primary")
            if submitted and new_q and new_a:
                entry = {"q": new_q, "a": new_a, "src": new_src,
                         "cat": new_cat, "conf": new_conf,
                         "added_by": "officer",
                         "timestamp": datetime.now().strftime("%d %b %Y %H:%M")}
                st.session_state.kb_additions.append(entry)
                st.success(f"✅ Entry added: '{new_q[:60]}…'")

        if st.session_state.kb_additions:
            st.markdown(f"**Session additions ({len(st.session_state.kb_additions)}):**")
            for e in st.session_state.kb_additions:
                with st.expander(f"[{e['cat']}] {e['q'][:70]}"):
                    st.markdown(e["a"])
                    st.caption(f"Source: {e['src']} · Added: {e['timestamp']}")

        st.divider()
        st.markdown("**Current KB coverage (official sources)**")
        topics = {
            "COP v3.1 §1": "Overview, agencies, mandatory dates",
            "COP v3.1 §3 DG": "Design Gateway — all 7 agencies",
            "COP v3.1 §3 CG": "Construction Gateway — SCDF fire safety",
            "COP v3.1 §3 EW": "External Works — LTA, NParks, PUB",
            "COP v3.1 §4": "IFC+SG: trees, planting, fire cisterns",
            "RABW Mar 2026": "Misconceptions, validity, process, Part-ST",
            "IFC-SG SP Sep 2025": "File size, geo-referencing, Revit export",
        }
        for src, desc in topics.items():
            st.markdown(f"✅ **{src}** — {desc}")
        st.caption("⚠️ Image-based PDFs (Design Gateway.pdf, Construction Gateway.pdf) have no extractable text — not yet indexed.")

    # ── TAB 3: EMAIL NOTIFICATIONS ─────────────────────────────────────────────
    with tab3:
        items_with_email = [q for q in st.session_state.review_queue if q.get("email")]
        st.markdown(f"**{len(items_with_email)} queries with user email provided**")

        if not items_with_email:
            st.info("No users have provided their email address yet. Email addresses appear here when users submit them on Tier B/C/D responses.")
        else:
            for i, item in enumerate(items_with_email):
                with st.expander(f"📧 {item['email']} — {item['question'][:60]}…"):
                    officer_ans_text = item.get("officer_answer", "")
                    if not officer_ans_text:
                        st.warning("No officer answer yet. Go to Review Queue tab to write one first.")
                    else:
                        email_body = f"""Dear User,

Thank you for your query via the CORENET X Knowledge Base.

Your question: {item['question']}

Official Response:
{officer_ans_text}

Sources: {', '.join(item.get('sources', []))}

If you have further questions, please contact us at the CORENET X portal.

Regards,
CORENET X Knowledge Base Team
"""
                        st.markdown("**Draft email — copy and send via your email client:**")
                        st.code(email_body, language=None)

                        mailto_link = f"mailto:{item['email']}?subject=CORENET%20X%20Query%20Response&body={email_body.replace(chr(10), '%0A').replace(' ', '%20')[:1000]}"
                        st.markdown(f"[📨 Open in email client]({mailto_link})")
                        st.caption("Or copy the text above and paste into your email.")

# ─── USER CHAT INTERFACE ───────────────────────────────────────────────────────
else:
    if st.session_state.role != "officer_login":
        st.markdown("## 🏗️ CORENET X Interactive Knowledge Base")
        st.caption("Answers drawn from 12 official Singapore government documents · Powered by Claude AI")

        # Starter questions
        if not st.session_state.messages:
            st.markdown("**Try a question:**")
            starters = [
                "What is CORENET X?",
                "What do I need for a fire tank?",
                "External works at Design Gateway?",
                "What are the 3 key gateways?",
                "Do I need to model soil depth at Design Gateway?",
                "What are the validity periods?",
                "Do I need 2D drawings for BIM?",
                "How do I model trees in IFC+SG?",
            ]
            cols = st.columns(4)
            for i, q in enumerate(starters):
                if cols[i % 4].button(q, key=f"s_{i}", use_container_width=True):
                    st.session_state["pending_q"] = q
                    st.rerun()

        # Render conversation history
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(f'<div style="text-align:right;margin:12px 0"><div class="user-bubble">{msg["content"]}</div></div>', unsafe_allow_html=True)
            else:
                r = msg["data"]
                t = r.get("tier", "D")
                conf = r.get("confidence", 0)

                with st.container(border=True):
                    tier_colors = {"A": "#1b6b3a", "B": "#1a3c5e", "C": "#d97706", "D": "#dc2626"}
                    c = tier_colors.get(t, "#6b7280")
                    st.markdown(f'<span class="tier-{t}">{TIER_LABELS[t]}</span> <span style="font-size:11px;color:#6b7280">{r.get("tier_reason","")}</span>', unsafe_allow_html=True)
                    st.markdown(conf_bar(conf, t), unsafe_allow_html=True)

                    if r.get("key_point"):
                        st.markdown(f'<div class="kp-box">📌 <strong>Key point:</strong> {r["key_point"]}</div>', unsafe_allow_html=True)

                    st.markdown(r.get("answer", ""), unsafe_allow_html=True)

                    if r.get("sources"):
                        st.markdown(f'<div class="src-box">📄 <strong>Sources:</strong> {" · ".join(r["sources"])}</div>', unsafe_allow_html=True)

                    # Resolved / officer notice + email capture
                    if t == "A":
                        st.success("✅ Query resolved — verified from official documents")
                    else:
                        notices = {
                            "B": "📬 Being reviewed by a CORENET X officer.",
                            "C": "🤖 AI-drafted from official documents. Officer verification recommended.",
                            "D": "📞 This topic needs direct officer guidance."
                        }
                        st.warning(notices.get(t, ""))
                        # Email capture
                        email_key = f"email_{id(msg)}"
                        if not msg.get("email_submitted"):
                            email_col, btn_col = st.columns([3, 1])
                            user_email = email_col.text_input("Leave your email to be notified when an officer responds:",
                                                               key=email_key, label_visibility="collapsed",
                                                               placeholder="your@email.com")
                            if btn_col.button("Notify me", key=f"nb_{id(msg)}"):
                                if user_email:
                                    msg["email_submitted"] = True
                                    msg["user_email"] = user_email
                                    # Update review queue entry
                                    for qitem in st.session_state.review_queue:
                                        if qitem.get("question") == msg.get("question"):
                                            qitem["email"] = user_email
                                    st.success(f"✅ Registered — officer will notify you at {user_email}")
                                    st.rerun()
                        else:
                            st.caption(f"✅ Notification registered for {msg.get('user_email','')}")

                    # Follow-up buttons
                    if r.get("follow_ups"):
                        st.markdown("**Suggested follow-ups:**")
                        fu_cols = st.columns(len(r["follow_ups"]))
                        for i, fq in enumerate(r["follow_ups"]):
                            if fu_cols[i].button(f"💬 {fq}", key=f"fu_{id(msg)}_{i}", use_container_width=True):
                                st.session_state["pending_q"] = fq
                                st.rerun()

        # Input area
        st.markdown("---")
        with st.form("chat_form", clear_on_submit=True):
            icol, bcol = st.columns([5, 1])
            user_input = icol.text_input("Ask anything about CORENET X…",
                                          label_visibility="collapsed",
                                          placeholder="e.g. What does SCDF require at Design Gateway?")
            submitted = bcol.form_submit_button("Send ➤", use_container_width=True, type="primary")

        # Handle pending question
        pending = st.session_state.pop("pending_q", None)
        if pending:
            user_input = pending
            submitted = True

        if submitted and user_input and user_input.strip():
            question = user_input.strip()
            st.session_state.messages.append({"role": "user", "content": question, "question": question})

            history = [{"role": m["role"], "content": m.get("content", "")}
                       for m in st.session_state.messages[:-1]]

            with st.spinner("Searching official documents…"):
                result = ask_claude(question, history)

            st.session_state.messages.append({
                "role": "assistant",
                "content": result.get("answer", ""),
                "data": result,
                "question": question,
            })

            # Update stats
            t = result.get("tier", "D")
            st.session_state.stats["asked"] += 1
            if t == "A":
                st.session_state.stats["resolved"] += 1
            else:
                st.session_state.stats["pending"] += 1
                # Add to review queue
                st.session_state.review_queue.append({
                    "question": question,
                    "tier": t,
                    "conf": result.get("confidence", 0),
                    "answer": result.get("answer", ""),
                    "sources": result.get("sources", []),
                    "email": None,
                    "timestamp": datetime.now().strftime("%d %b %Y %H:%M"),
                    "reviewed": False,
                    "officer_answer": "",
                })

            st.rerun()
