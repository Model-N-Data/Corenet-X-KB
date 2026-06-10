"""
CORENET X Knowledge Base — Interactive Streamlit App
Answers from 12 official Singapore government documents via Claude API.

SETUP:
  pip install streamlit anthropic
  export ANTHROPIC_API_KEY="sk-ant-..."   (Linux/Mac)
  set ANTHROPIC_API_KEY=sk-ant-...        (Windows CMD)

RUN:
  streamlit run corenet_x_app.py

DEPLOY (Streamlit Cloud):
  1. Push this file + requirements.txt to a public GitHub repo
  2. Go to https://share.streamlit.io → New app → select repo
  3. Add secret:  ANTHROPIC_API_KEY = "sk-ant-..."
"""

import streamlit as st
import anthropic
import json
import os
import re

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CORENET X Knowledge Base",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.tier-A  {background:#e8f5ec;color:#1b6b3a;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:700;display:inline-block}
.tier-B  {background:#e8f0f8;color:#1a3c5e;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:700;display:inline-block}
.tier-C  {background:#fff3e0;color:#7a4500;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:700;display:inline-block}
.tier-D  {background:#fdeaea;color:#8b1a1a;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:700;display:inline-block}
.kp-box  {background:#fffde7;border-left:3px solid #f6c000;padding:9px 13px;border-radius:3px;font-size:13px;margin:8px 0}
.src-box {background:#f8f9fa;border:1px solid #dde3ec;padding:7px 12px;border-radius:5px;font-size:11.5px;color:#6b7280}
.conf-bar-wrap {display:flex;align-items:center;gap:8px;margin:4px 0}
.conf-bar {height:6px;border-radius:3px;flex:1;background:#e5e7eb;overflow:hidden}
.user-bubble {background:#1a3c5e;color:#fff;padding:10px 14px;border-radius:16px 4px 16px 16px;display:inline-block;max-width:580px;font-size:14px;line-height:1.6}
.ai-card-head {display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
</style>
""", unsafe_allow_html=True)

# ─── KB Data (source of truth — same 25 entries as chat demo, extended context) ──────
KB_CONTEXT = """
OFFICIAL CORENET X KNOWLEDGE BASE
Sources: COP v3.1 (Dec 2025, 442 pp), RABW Mar 2026 (181 pp), IFC-SG Revit SP Guide Sep 2025 (176 pp).
ALL Singapore government official documents only.

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

== DESIGN GATEWAY (G1) ==
Q: What does each agency require at Design Gateway?
A: BCA: NIL at DG. Complex buildings require pre-consultation before Piling Gateway.
LTA: Access points, parking provision, frontage improvement, commuter facilities.
NEA: Refuse location/size, cooling tower setback (5 m), pollution control buffers.
NParks: Planting areas (3 m/5 m green buffers), tree conservation, Arborist report.
PUB: Minimum Platform Level, peak run-off C ≤ 0.55, drainage concept, sewer connection.
SCDF: Fire engine accessway location and width ONLY (fire suppression is a CG requirement).
URA: Building massing, site layout, land use/GFA/GPR, connectivity, greenery.
Source: COP v3.1 §3 DG Summary pp.108–126

Q: What are planting area requirements at Design Gateway?
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
LTA (COP pp.183–186): Horizontal alignment and junction layout of new/modified roads; road vertical profile; development access levels; tree affected plan; layout of drains/sumps/box culverts; commuter facilities (covered linkways, bus stops, POBs); cycling paths.
NParks (COP pp.190–191): Conservation of trees (TCOT, Heritage, EIA/EMMP) — Arborist report required; green verges: tree planting and service verges for street works.
PUB (COP pp.193–195): Peak run-off C value ≤ 0.55; roadside drain capacity; sewer connection point; Drainage Reserve location and width.
Source: COP v3.1 §3 External Works pp.178–196

Q: Can external works be delinked?
A: Yes — CORENET X supports conditional delinking at Construction Gateway if internal works are in order but external works are still being reviewed.
Cannot be delinked (interfacing aspects): LTA/NParks: vehicular/pedestrian/cyclist access points, covered linkways, POB connections, bus stops; PUB: connection of internal drain to road drain, MPL/outlet levels, sewer connection point.
Source: COP v3.1 §3 External Works pp.178–179

== CONSTRUCTION GATEWAY (G2) ==
Q: What does SCDF require at Construction Gateway for fire suppression?
A: SCDF requires the full fire safety design at CG:
- Firefighting water storage tanks (fire cisterns) — capacity, location, fire engine access
- Wet/dry pipe sprinkler systems — coverage, zoning, flow calculations
- Hose reels — location, coverage zones
- Fire hydrants — location, spacing
- Rising mains (wet and dry risers) — location in fire-fighting lobbies, sizing
- Means of escape: travel distances, staircase widths, pressurisation
- Fire compartmentation: fire-rated walls/floors, compartment sizes
- Smoke control systems: mechanical ventilation/extraction
- Emergency Voice Communication (EVC) and Automatic Fire Alarm (AFA)
NOTE: SCDF at Design Gateway requires ONLY fire engine accessway — NOT fire suppression systems.
Source: COP v3.1 §3 CG SCDF pp.130–135

== BIM & IFC+SG ==
Q: What is IFC+SG?
A: Singapore's customised openBIM standard extending IFC4 with SGPsets (Singapore-localised property sets). Mandatory for GFA ≥ 5,000 m². Resource Kit: go.gov.sg/ifcsg. Supported: Autodesk Revit, Graphisoft ArchiCAD, Bentley OpenBuildings Designer.
Source: COP v3.1 Preamble p.4

Q: How do I model trees in IFC+SG?
A: Use IfcGeographicElement with subtypes: LANDSCAPE_TREE, LANDSCAPE_PALM, LANDSCAPE_HEDGE.
Required properties: Girth (mm), Height (mm), Species (e.g. Samanea saman), Status (Proposed/Existing/To be removed/To be transplanted), TreeNumber (T001, T002...), Roadside (Boolean).
Simplified lollipop BIM components allowed if IFC+SG properties embedded. Base point at base of tree.
Source: COP v3.1 §4 Landscape Plants pp.308–309

Q: How do I model fire tanks in IFC+SG?
A: Fire tank/cistern: IfcTank with IfcObjectType: FIREFIGHTERSTORAGE. Properties: Capacity (m³), Location (basement/rooftop), Status.
Sprinklers/hose reels/hydrants: IfcFireSuppressionTerminal — subtypes: SPRINKLERHEAD, HOSEREEL, FIREHYDRANT. Properties: FlowRate, WorkingPressure, Status.
Rising mains: IfcPipeSegment for pipe runs; IfcPipeTerminal for outlets.
Source: COP v3.1 §4 Identified Components pp.247–260

Q: What is the maximum BIM file size?
A: 800 MB per IFC file. Recommended: 1 block per IFC file. If a single block exceeds 800 MB, split by zones and levels. All discipline models (Arch, C&S, MEP) must be coordinated before submission.
Source: IFC-SG SP Guide Sep 2025 p.9

Q: How do I geo-reference my BIM model?
A: Easting/Northing (x,y): Singapore SVY21 (EPSG: 3414). Height (z): Singapore Height Datum (SHD). Orientation: True North. In Revit: Manage > Coordinates > Specify Coordinates at a Point, or import geo-referenced CAD/DWG.
Source: IFC-SG SP Guide Sep 2025 pp.126–136

== PROCESS & MISCONCEPTIONS ==
Q: Do I need 2D drawings for BIM submissions?
A: No — 2D drawings NOT required for BIM submissions. Exception: complex details impractical to model in 3D may use supplementary 2D. External Works may be submitted in 2D CAD.
Source: RABW Mar 2026 p.134 (Misconception #3)

Q: Common misconceptions about CORENET X?
A: Myth 1: Only QPs are involved — False. Developers, Builders, RE/RTO, Accredited Checkers also interact.
Myth 2: All projects must submit in BIM — False. BIM mandatory only for GFA ≥ 5,000 m².
Myth 3: 3D BIM still requires 2D drawings — False. 2D generally NOT required.
Myth 4: All requirements must be cleared at gateways — False. Certain detailed requirements can be submitted separately.
Myth 5: Demolition waits for main building works approval — False. Demolition can proceed independently.
Myth 6: Project must restart if clearance not in 2 iterations — False. Submissions can go beyond 2 iterations.
Source: RABW Mar 2026 pp.134–135

Q: What are the validity periods?
A: Design Gateway: 12 months initial validity. Clearance must be valid when CG submitted.
Piling Gateway: 24 months. Lapses if building works not commenced.
Construction Gateway: 24 months. Must remain valid until completion.
CSC: Must be obtained within 2 years of TOP.
Source: RABW Mar 2026 p.105

Q: How does the joint submission process work?
A: 1. Project Coordinator (lead QP) creates project on CORENET X Submission Portal.
2. Developer/Owner logs in via Singpass to appoint QPs.
3. Appointed QPs input data, upload model and documents, declare accuracy.
4. Team pays fees via CORENET Pay (pay.corenet.gov.sg).
5. Agencies collaborate and process plans in 20 working days.
6. Agencies issue clearance or consolidated Written Direction.
Source: RABW Mar 2026 pp.101–103
"""

# ─── System prompt ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are the CORENET X Knowledge Base AI — an authoritative, helpful assistant for Singapore's CORENET X regulatory submission platform.

You answer questions ONLY from the official sources provided below. Do not invent requirements, percentages, or agency-specific rules not present in the knowledge base.

{KB_CONTEXT}

RESPONSE FORMAT: Always respond in valid JSON with this exact structure:
{{
  "answer": "<HTML-formatted answer. Use <p>, <ul>, <li>, <strong>, <h4> tags. Be specific and cite section numbers where available.>",
  "confidence": <integer 0-99>,
  "tier": "<A|B|C|D>",
  "tier_reason": "<one sentence explaining the confidence level>",
  "sources": ["<source 1>", "<source 2>"],
  "key_point": "<most important single sentence from your answer, or null>",
  "follow_ups": ["<follow-up question 1>", "<follow-up question 2>", "<follow-up question 3>"]
}}

TIER / CONFIDENCE RULES:
- Tier A (≥85%): Question directly answered by the KB above. Cite exact section/page.
- Tier B (70–84%): Partially answered; officer should review for completeness.
- Tier C (40–69%): AI inference from related content; officer should verify.
- Tier D (<40%): Not in the KB. Direct user to contact a CORENET X officer.

CRITICAL RULES:
- Never invent specific numbers (setbacks, areas, percentages) not in the KB.
- Always note if something is a Design Gateway vs Construction Gateway requirement (they differ significantly — e.g. SCDF fire suppression is ONLY a CG requirement, not DG).
- For topics completely outside the KB, respond with Tier D and confidence < 30.
- Keep answers concise but complete. Use HTML formatting for clarity.
- Respond ONLY with JSON. No markdown, no preamble, no explanation outside the JSON.
"""

# ─── API helper ──────────────────────────────────────────────────────────────
def get_api_key():
    # Try Streamlit secrets first (for cloud deployment), then env var
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY", "")

def ask_claude(question: str, history: list[dict]) -> dict:
    api_key = get_api_key()
    if not api_key:
        return {
            "answer": "<p><strong>API key not configured.</strong> Set your <code>ANTHROPIC_API_KEY</code> environment variable or Streamlit secret to enable real AI answers.</p>",
            "confidence": 0, "tier": "D",
            "tier_reason": "API key missing.",
            "sources": [], "key_point": None,
            "follow_ups": ["What is CORENET X?", "What are the 3 key gateways?", "When is CORENET X mandatory?"]
        }

    client = anthropic.Anthropic(api_key=api_key)

    # Build messages array from history
    messages = []
    for msg in history[-6:]:   # send last 3 Q/A pairs for context
        if msg["role"] in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",   # fast + cheap; swap to claude-sonnet-4-6 for best quality
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "answer": f"<p>Response parsing error. Raw text: <code>{raw[:400]}</code></p>",
            "confidence": 30, "tier": "C",
            "tier_reason": "Parse error.",
            "sources": [], "key_point": None,
            "follow_ups": []
        }
    except anthropic.APIError as e:
        return {
            "answer": f"<p>API error: {e}</p>",
            "confidence": 0, "tier": "D",
            "tier_reason": "API error.",
            "sources": [], "key_point": None,
            "follow_ups": []
        }

# ─── Confidence bar HTML ─────────────────────────────────────────────────────
def conf_bar(conf: int, tier: str) -> str:
    colors = {"A": "#1b6b3a", "B": "#1a3c5e", "C": "#d97706", "D": "#dc2626"}
    c = colors.get(tier, "#6b7280")
    return f"""
    <div class="conf-bar-wrap">
      <span style="font-size:13px;font-weight:700;color:{c}">{conf}%</span>
      <div class="conf-bar"><div style="width:{conf}%;height:6px;background:{c};border-radius:3px"></div></div>
    </div>
    """

TIER_LABELS = {"A": "✅ Verified (Tier A)", "B": "📋 Officer Reviewing (Tier B)",
               "C": "🤖 AI Draft (Tier C)", "D": "📞 Needs Officer (Tier D)"}

# ─── Session state ───────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "stats" not in st.session_state:
    st.session_state.stats = {"asked": 0, "resolved": 0, "pending": 0}

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏗️ CORENET X KB")
    st.caption("12 Official Sources · COP v3.1 Dec 2025")
    st.divider()

    # Model selector
    model_choice = st.selectbox(
        "Claude model",
        ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
        index=0,
        help="Haiku = fast & cheap. Sonnet = higher quality."
    )

    st.divider()
    st.markdown("**📊 Session stats**")
    col1, col2, col3 = st.columns(3)
    col1.metric("Asked", st.session_state.stats["asked"])
    col2.metric("✅ Resolved", st.session_state.stats["resolved"])
    col3.metric("⏳ Pending", st.session_state.stats["pending"])

    st.divider()
    st.markdown("**📁 Sources**")
    st.caption("COP v3.1 (Dec 2025, 442 pp)")
    st.caption("RABW Mar 2026 (181 pp)")
    st.caption("IFC-SG SP Guide Sep 2025 (176 pp)")
    st.caption("+ 9 more official SG govt docs")

    st.divider()
    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = []
        st.session_state.stats = {"asked": 0, "resolved": 0, "pending": 0}
        st.rerun()

    st.divider()
    st.markdown("**🔑 API Key**")
    api_key_input = st.text_input("ANTHROPIC_API_KEY", type="password",
                                   value=get_api_key(),
                                   placeholder="sk-ant-…")
    if api_key_input:
        os.environ["ANTHROPIC_API_KEY"] = api_key_input

# ─── Main area ───────────────────────────────────────────────────────────────
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
        if cols[i % 4].button(q, key=f"starter_{i}", use_container_width=True):
            st.session_state["pending_question"] = q
            st.rerun()

# Render conversation history
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div style="text-align:right;margin:12px 0"><div class="user-bubble">{msg["content"]}</div></div>', unsafe_allow_html=True)
    else:
        r = msg["data"]
        t = r.get("tier", "D")
        conf = r.get("confidence", 0)
        sources = r.get("sources", [])
        kp = r.get("key_point")
        tier_reason = r.get("tier_reason", "")
        follow_ups = r.get("follow_ups", [])

        with st.container(border=True):
            # Header row
            tier_color = {"A": "#1b6b3a", "B": "#1a3c5e", "C": "#d97706", "D": "#dc2626"}.get(t, "#6b7280")
            tier_bg = {"A": "#e8f5ec", "B": "#e8f0f8", "C": "#fff3e0", "D": "#fdeaea"}.get(t, "#f0f0f0")
            st.markdown(
                f'<div class="ai-card-head">'
                f'<span class="tier-{t}">{TIER_LABELS[t]}</span>'
                f'<span style="font-size:11px;color:#6b7280">{tier_reason}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.markdown(conf_bar(conf, t), unsafe_allow_html=True)

            # Key point
            if kp:
                st.markdown(f'<div class="kp-box">📌 <strong>Key point:</strong> {kp}</div>', unsafe_allow_html=True)

            # Answer
            st.markdown(r.get("answer", ""), unsafe_allow_html=True)

            # Sources
            if sources:
                src_str = " · ".join(sources)
                st.markdown(f'<div class="src-box">📄 <strong>Sources:</strong> {src_str}</div>', unsafe_allow_html=True)

            # Resolved / officer notice
            if t == "A":
                st.success("✅ Query resolved — verified from official documents")
            elif t in ("B", "C", "D"):
                notices = {
                    "B": "📬 Being reviewed by a CORENET X officer.",
                    "C": "🤖 AI-drafted. Officer verification recommended.",
                    "D": "📞 Outside the knowledge base. Contact a CORENET X officer directly."
                }
                st.warning(notices.get(t, ""))

            # Follow-up buttons
            if follow_ups:
                st.markdown("**Suggested follow-ups:**")
                fu_cols = st.columns(len(follow_ups))
                for i, fq in enumerate(follow_ups):
                    if fu_cols[i].button(f"💬 {fq}", key=f"fu_{id(msg)}_{i}", use_container_width=True):
                        st.session_state["pending_question"] = fq
                        st.rerun()

# Input area
st.markdown("---")
with st.form("chat_form", clear_on_submit=True):
    cols = st.columns([5, 1])
    user_input = cols[0].text_input(
        "Ask anything about CORENET X…",
        placeholder="e.g. What does SCDF require at Design Gateway?",
        label_visibility="collapsed"
    )
    submitted = cols[1].form_submit_button("Send ➤", use_container_width=True, type="primary")

# Handle pending question from starter buttons or follow-ups
pending = st.session_state.pop("pending_question", None)
if pending:
    user_input = pending
    submitted = True

if submitted and user_input and user_input.strip():
    question = user_input.strip()

    # Add user message
    st.session_state.messages.append({"role": "user", "content": question})

    # Build history for context
    history = [{"role": m["role"], "content": m.get("content") or ""} for m in st.session_state.messages[:-1]]

    with st.spinner("Searching official documents…"):
        # Pass model choice
        api_key = get_api_key()
        client = anthropic.Anthropic(api_key=api_key) if api_key else None

        if client:
            try:
                messages = []
                for m in history[-6:]:
                    if m["role"] in ("user", "assistant"):
                        messages.append({"role": m["role"], "content": m["content"]})
                messages.append({"role": "user", "content": question})

                resp = client.messages.create(
                    model=model_choice,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                )
                raw = resp.content[0].text.strip()
                raw = re.sub(r'^```(?:json)?\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw)
                result = json.loads(raw)
            except Exception as e:
                result = {
                    "answer": f"<p>Error: {e}</p>",
                    "confidence": 0, "tier": "D",
                    "tier_reason": "Error occurred.",
                    "sources": [], "key_point": None,
                    "follow_ups": []
                }
        else:
            result = {
                "answer": "<p><strong>Set your ANTHROPIC_API_KEY</strong> in the sidebar to enable AI answers.</p>",
                "confidence": 0, "tier": "D",
                "tier_reason": "No API key configured.",
                "sources": [], "key_point": None,
                "follow_ups": ["What is CORENET X?", "What are the 3 key gateways?"]
            }

    # Add AI message
    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("answer", ""),
        "data": result
    })

    # Update stats
    t = result.get("tier", "D")
    st.session_state.stats["asked"] += 1
    if t == "A":
        st.session_state.stats["resolved"] += 1
    else:
        st.session_state.stats["pending"] += 1

    st.rerun()
