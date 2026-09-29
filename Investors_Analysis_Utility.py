import streamlit as st
import pandas as pd
import json
import os
import time
from google import genai
from datetime import datetime

# --- 1. CONFIGURATION & MODEL SETUP ---
st.set_page_config(
    page_title="AI Driven Self-serviced Analytics | BIU",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Securely retrieve the key from Streamlit Secrets or Environment Variable
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("⚠️ GEMINI_API_KEY not found. Please configure it in your Streamlit Secrets.")
    st.stop()

client = genai.Client(api_key=GEMINI_API_KEY)

PRIMARY_MODEL = "gemini-3.6-flash"
FALLBACK_MODEL = "gemini-3.6-pro"

def generate_content_with_retry(client_obj, prompt_text, max_retries=3):
    """Executes prompt with backoff retries and model failover against 503 capacity spikes."""
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
    
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                res = client_obj.models.generate_content(
                    model=model_name,
                    contents=prompt_text,
                    config={"response_mime_type": "application/json"}
                )
                return res
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                    wait_seconds = (attempt + 1) * 2
                    time.sleep(wait_seconds)
                    continue
                break
                
    raise Exception("Google AI servers are currently experiencing high demand. Please try again in a few seconds.")

# --- 2. THEME (HDFC-inspired: deep blue + red, on white) ---
HDFC_BLUE = "#004C8F"
HDFC_RED = "#ED232A"

st.markdown(f"""
<style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}

    .main {{ background-color: #f0f2f5; }}

    .block-container {{
        padding-top: 3rem;
        padding-bottom: 3rem;
        max-width: 950px;
        background-color: #ffffff;
        border: 1px solid {HDFC_BLUE};
        border-radius: 14px;
        margin-top: 2rem;
        margin-bottom: 2rem;
        box-shadow: 0 2px 14px rgba(0,76,143,0.08);
    }}

    .logo-wrap {{
        text-align: center;
        margin-top: 2vh;
        margin-bottom: 0.5rem;
    }}
    .logo-text {{
        font-size: 3rem;
        font-weight: 700;
        letter-spacing: -1px;
        font-family: 'Segoe UI', Arial, sans-serif;
    }}
    .logo-text .b {{ color: {HDFC_BLUE}; }}
    .logo-text .r {{ color: {HDFC_RED}; }}
    .tagline {{
        text-align: center;
        color: #5f6368;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }}

    div[data-testid="stFileUploaderDropzone"] {{
        border-radius: 24px !important;
        border: 1px solid #dfe1e5 !important;
        box-shadow: 0 1px 6px rgba(32,33,36,0.15);
        background-color: #fff !important;
        max-width: 650px;
        margin: 0 auto;
    }}

    div[data-testid="stFileUploader"] {{
        max-width: 650px;
        margin: 0 auto;
    }}

    .stButton>button {{
        background-color: {HDFC_RED};
        color: white;
        border-radius: 24px;
        border: none;
        padding: 0.45rem 1.6rem;
        font-weight: 500;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        box-shadow: 0 2px 6px rgba(237,35,42,0.25);
    }}
    .stButton>button:hover {{
        background-color: #c81e24;
        color: white;
        transform: translateY(-2px) scale(1.02);
    }}

    .writeup-box {{
        background-color: #f8fafd;
        border-left: 4px solid {HDFC_BLUE};
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin: 1rem 0;
        color: #1a1a1a;
        line-height: 1.6;
        font-size: 0.93rem;
    }}
    .writeup-box h4 {{
        margin: 0 0 0.5rem 0;
        color: {HDFC_BLUE};
        font-size: 1rem;
    }}

    .caveat-box {{
        background-color: #fff8f6;
        border-left: 4px solid {HDFC_RED};
        border-radius: 8px;
        padding: 0.8rem 1.2rem;
        margin-top: 0.8rem;
        color: #4a1517;
        font-size: 0.88rem;
    }}

    .footer-note {{
        text-align: center;
        color: #70757a;
        font-size: 0.8rem;
        margin-top: 2rem;
    }}
</style>
""", unsafe_allow_html=True)

# --- 3. SESSION STATE ---
if "history" not in st.session_state:
    st.session_state.history = []

# --- 4. HERO ---
st.markdown("""
<div class="logo-wrap">
    <span class="logo-text"><span class="b">Investor Analysis </span><span class="r">AI-Engine</span></span>
</div>
<div class="tagline">BIU Self-Service Analytics &nbsp;·&nbsp; Automated Cross-tabs, Visuals & Deep Insights</div>
""", unsafe_allow_html=True)

# --- 5. FILE UPLOAD ---
uploaded_file = st.file_uploader(" ", type=["csv", "xlsx", "xls"], label_visibility="collapsed")

if uploaded_file is None:
    st.markdown('<div class="footer-note">Upload an Excel or CSV file to start analysis</div>', unsafe_allow_html=True)

if uploaded_file is not None:
    try:
        file_ext = uploaded_file.name.split('.')[-1].lower()
        if file_ext == 'csv':
            df = pd.read_csv(uploaded_file)
        else:
            try:
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            except Exception:
                uploaded_file.seek(0)
                df = pd.read_excel(uploaded_file)

        st.success(f"✅ Data loaded: **{uploaded_file.name}** ({len(df):,} records, {len(df.columns)} columns)")

        tab_ask, tab_history = st.tabs(["Ask the Assistant", "Query History"])

        with tab_ask:
            st.caption("Try: *'Disbursement breakdown across zones'* or *'Delinquency rates across ticket sizes'*")
            query = st.text_input("Your question", label_visibility="collapsed", placeholder="Enter your business question...")
            
            run = False
            _, btn_col, _ = st.columns([2, 1, 2])
            with btn_col:
                run = st.button("Analyze", use_container_width=True)

            if run and query:
                with st.spinner("Crunching numbers, compiling cross-tabs, and rendering charts..."):
                    col_summary = "\n".join([f"- {col} ({dtype})" for col, dtype in zip(df.columns, df.dtypes)])
                    num_summary = df.describe().to_string()

                    prompt = f"""
                    You are a Lead BIU / MIS Banking Analyst.
                    A pandas DataFrame 'df' is loaded in memory with these columns and types:
                    {col_summary}

                    Summary statistics preview:
                    {num_summary}

                    BUSINESS QUESTION: "{query}"

                    CRITICAL REQUIREMENTS:
                    1. Cross-Tab & Visuals: The executable code MUST ALWAYS output BOTH:
                       - An aggregated cross-tab or pivot table using `st.dataframe(...)` or `st.table(...)`.
                       - A primary visual chart using `st.bar_chart(...)` or `st.line_chart(...)`.
                    2. Deep Analytical Writeup:
                       - Explicitly discuss concrete numerical points, baseline averages, and percentage variances.
                       - Highlight the core trends and drivers behind the numbers.
                    3. Caveats & Self-Analysis:
                       - Mention sample skews, outliers, zero-value concentrations, or missing slices that readers should consider before making credit/business decisions.

                    Respond ONLY with a valid JSON object (no markdown, no backticks) containing:
                    {{
                        "executive_summary": "Thorough 3-5 sentence breakdown referencing numbers, percentages, and direction of trends.",
                        "caveats_and_risks": "2-3 sentences covering data caveats, concentration risks, or statistical biases.",
                        "code": "Valid Python code using Streamlit to compute and display BOTH the cross-tab/pivot and chart."
                    }}
                    """

                    response = generate_content_with_retry(client, prompt)
                    
                    try:
                        clean_json = response.text.strip()
                        if clean_json.startswith("```"):
                            clean_json = clean_json.strip("`")
                            if clean_json.lower().startswith("json"):
                                clean_json = clean_json[4:]
                        parsed = json.loads(clean_json)
                        summary = parsed.get("executive_summary", "")
                        caveats = parsed.get("caveats_and_risks", "")
                        clean_code = parsed.get("code", "")
                    except Exception:
                        summary = "Analysis generated. See computations below."
                        caveats = ""
                        clean_code = response.text.strip().replace("```python", "").replace("```", "")

                    st.session_state.history.append({
                        "query": query,
                        "summary": summary,
                        "caveats": caveats,
                        "time": datetime.now().strftime("%H:%M:%S")
                    })

                    # Render Insights
                    if summary:
                        st.markdown(f"""
                        <div class="writeup-box">
                            <h4>📊 Business Insights & Trends</h4>
                            {summary}
                        </div>
                        """, unsafe_allow_html=True)

                    if caveats:
                        st.markdown(f"""
                        <div class="caveat-box">
                            <strong>⚠️ Analytical Caveats & Distribution Risks:</strong><br>
                            {caveats}
                        </div>
                        """, unsafe_allow_html=True)

                    # Execute and Render Results
                    result_container = st.container(border=True)
                    with result_container:
                        st.subheader("Data & Visual Output")
                        try:
                            exec(clean_code)
                        except Exception as err:
                            st.error(f"Execution Error: {err}")
                            with st.expander("View generated code"):
                                st.code(clean_code, language="python")

        with tab_history:
            if not st.session_state.history:
                st.info("No queries executed in this session.")
            else:
                for item in reversed(st.session_state.history):
                    st.markdown(f"""
                    <div style="background-color: #f8f9fa; border-left: 3px solid {HDFC_BLUE}; padding: 0.6rem 1rem; border-radius: 6px; margin-bottom: 0.8rem;">
                        <strong>🕒 {item['time']} — {item['query']}</strong>
                        <p style="margin: 0.4rem 0 0 0; font-size: 0.88rem; color: #3c4043;">{item['summary']}</p>
                    </div>
                    """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Error reading file: {e}")
