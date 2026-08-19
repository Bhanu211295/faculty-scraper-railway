"""
streamlit_app_advanced.py
-----------------------
Advanced Streamlit app with:
  - Scrolling for dynamic content
  - Pagination detection
  - Profile clicking
  - Complete data extraction

Deploy to Railway.app (not Streamlit Cloud) for Playwright support.
"""

import streamlit as st
from io import StringIO
import csv
from datetime import datetime

from fetcher_advanced import AdvancedFetcher
from extractor import get_extractor, FacultyRecord

st.set_page_config(
    page_title="Faculty Data Scraper (Advanced)",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .main {
        max-width: 800px;
        margin: auto;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Faculty Data Scraper (Advanced)")
st.markdown("Extract ALL faculty information — with scrolling, pagination, and profile clicking")

# Initialize session state
if "job_running" not in st.session_state:
    st.session_state.job_running = False
if "records" not in st.session_state:
    st.session_state.records = []
if "error_msg" not in st.session_state:
    st.session_state.error_msg = None
if "success" not in st.session_state:
    st.session_state.success = False

# Sidebar info
with st.sidebar:
    st.markdown("### ℹ️ Advanced Features")
    st.markdown("""
    This version handles:
    - **Scrolling**: Dynamic content loaded on scroll
    - **Pagination**: Multiple pages auto-detected
    - **Profiles**: Click individual profiles for details
    - **Complete Data**: All fields including numerical/multi-line
    
    **Deploy on:** Railway.app (Streamlit Cloud has Playwright limits)
    
    **Free API Keys:**
    - [Gemini](https://aistudio.google.com/apikey)
    - [Groq](https://console.groq.com)
    """)

# Main form
if not st.session_state.job_running:
    st.markdown("---")
    
    with st.form("scrape_form"):
        university = st.text_input(
            "University Name *",
            placeholder="e.g., SASTRA, DTU, IIT Delhi",
            help="Label for this university"
        )
        
        url = st.text_input(
            "Faculty Listing URL *",
            placeholder="https://www.sastra.edu/staffprofiles/schools/mech.php",
            help="Main faculty/staff page URL"
        )
        
        provider = st.selectbox(
            "AI Provider",
            ["gemini", "groq", "anthropic"],
            help="Which AI service to use"
        )
        
        col1, col2, col3 = st.columns(3)
        with col1:
            with_scrolling = st.checkbox("📜 Scrolling", value=True, help="Load dynamic content")
        with col2:
            with_pagination = st.checkbox("📖 Pagination", value=True, help="Auto-scrape all pages")
        with col3:
            with_profiles = st.checkbox("👤 Profiles", value=False, help="Click individual profiles")
        
        submitted = st.form_submit_button("🚀 Start Scraping", type="primary", use_container_width=True)
        
        if submitted:
            if not university or not url:
                st.error("❌ Please enter both university name and URL")
            else:
                st.session_state.job_running = True
                st.session_state.university = university
                st.session_state.url = url
                st.session_state.provider = provider
                st.session_state.with_scrolling = with_scrolling
                st.session_state.with_pagination = with_pagination
                st.session_state.with_profiles = with_profiles
                st.session_state.records = []
                st.session_state.error_msg = None
                st.session_state.success = False
                st.rerun()

else:
    # Job running - show progress
    st.markdown("---")
    st.markdown("### 🔄 Scraping in Progress...")
    
    progress_container = st.empty()
    status_container = st.empty()
    record_count_container = st.empty()
    error_container = st.empty()
    
    try:
        progress_container.progress(10)
        status_container.info("🔍 Initializing scraper...")
        
        fetcher = AdvancedFetcher(headless=True, delay_seconds=0.8)
        extractor = get_extractor(st.session_state.provider)
        
        try:
            # Discover pagination
            if st.session_state.with_pagination:
                progress_container.progress(15)
                status_container.info("📖 Detecting pagination...")
                urls_to_process = fetcher.discover_pagination(st.session_state.url)
                if len(urls_to_process) > 1:
                    status_container.info(f"📖 Found {len(urls_to_process)} page(s)")
            else:
                urls_to_process = [st.session_state.url]
            
            all_records = []
            
            # Process each page
            for page_num, page_url in enumerate(urls_to_process, 1):
                progress = 20 + (page_num / len(urls_to_process)) * 30
                progress_container.progress(int(progress))
                status_container.info(f"📥 Page {page_num}/{len(urls_to_process)}: Fetching...")
                
                # Fetch with scrolling
                if st.session_state.with_scrolling:
                    page = fetcher.fetch_with_scrolling(page_url, scroll_pause_time=1.2, max_scrolls=12)
                else:
                    page = fetcher.fetch(page_url)
                
                # Analyze page
                progress_container.progress(int(progress + 10))
                status_container.info(f"🤖 Page {page_num}: Analyzing structure...")
                analysis = extractor.analyze_listing_page(page["url"], page["text"], page["links"])
                page_type = analysis.get("page_type")
                
                # Try profile clicking if classification is ambiguous
                if st.session_state.with_profiles and page_type == "unknown":
                    progress_container.progress(int(progress + 15))
                    status_container.info(f"Page {page_num}: Discovering profiles via clicking...")
                    profiles = fetcher.discover_and_click_profiles(page_url, max_profiles=100)
                    if profiles:
                        page_type = "detail_links"
                        analysis = {"page_type": "detail_links", "profiles": profiles}
                
                # Extract records
                if page_type == "full_records":
                    progress_container.progress(int(progress + 20))
                    status_container.info(f"Page {page_num}: Extracting records...")
                    for r in analysis.get("records", []):
                        rec = FacultyRecord(
                            source_university=st.session_state.university,
                            source_url=st.session_state.url
                        )
                        for k in ["name", "designation", "department", "qualification", "specialization", "email", "phone", "photo_url", "bio"]:
                            setattr(rec, k, r.get(k))
                        all_records.append(rec)
                
                elif page_type == "detail_links":
                    profiles = analysis.get("profiles", [])
                    progress_container.progress(int(progress + 20))
                    status_container.info(f"Page {page_num}: Visiting {len(profiles)} profiles...")
                    
                    for i, p in enumerate(profiles, 1):
                        purl = p.get("url")
                        if not purl:
                            continue
                        
                        try:
                            progress = 50 + (i / len(profiles)) * 40
                            progress_container.progress(int(progress))
                            record_count_container.metric("Extracted Records", len(all_records))
                            
                            detail_page = fetcher.fetch(purl)
                            data = extractor.extract_detail_page(purl, detail_page["text"])
                            data["profile_url"] = purl
                            
                            rec = FacultyRecord(
                                source_university=st.session_state.university,
                                source_url=st.session_state.url
                            )
                            for k in ["name", "designation", "department", "qualification", "specialization", "email", "phone", "photo_url", "bio", "profile_url"]:
                                setattr(rec, k, data.get(k))
                            rec.extraction_confidence = data.get("extraction_confidence")
                            all_records.append(rec)
                        except Exception as e:
                            pass
            
            fetcher.close()
            
            if not all_records:
                raise Exception("No records extracted from the page.")
            
            # Deduplicate
            seen = {}
            deduped = []
            for r in all_records:
                key = (r.name, r.email)
                if key not in seen:
                    seen[key] = True
                    deduped.append(r)
            
            st.session_state.records = deduped
            st.session_state.success = True
            progress_container.progress(100)
            status_container.success(f"✅ Success! Extracted {len(deduped)} records.")
        
        except Exception as e:
            st.session_state.error_msg = str(e)
            error_container.error(f"❌ Error: {str(e)}")
            status_container.empty()
            progress_container.empty()
    
    st.markdown("---")
    
    # Show results
    if st.session_state.success and st.session_state.records:
        st.success(f"✅ Extracted {len(st.session_state.records)} faculty records!")
        
        st.markdown("### 📥 Download Your Data")
        
        # Convert to CSV
        output = StringIO()
        fieldnames = [
            "source_university",
            "source_url",
            "name",
            "designation",
            "department",
            "qualification",
            "specialization",
            "email",
            "phone",
            "photo_url",
            "bio",
            "profile_url",
            "extraction_confidence",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([r.to_dict() for r in st.session_state.records])
        
        csv_data = output.getvalue()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"faculty_data_{timestamp}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True
        )
        
        st.markdown("---")
        
        # Preview
        with st.expander("👀 Preview Data"):
            st.dataframe(
                [r.to_dict() for r in st.session_state.records[:10]],
                use_container_width=True,
                height=400
            )
    
    if st.button("🔄 Start Over", use_container_width=True):
        st.session_state.job_running = False
        st.session_state.records = []
        st.session_state.error_msg = None
        st.session_state.success = False
        st.rerun()
