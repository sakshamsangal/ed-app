import streamlit as st
import requests
import time
import os
import uuid

# --- CONFIGURATION ---
API_GATEWAY_BASE_URL = "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev" # Your API Gateway Invoke URL


# --- UI LAYOUT & STATE MANAGEMENT ---
st.set_page_config(layout="wide", page_title="Wire Vision AI")
st.title("💡 Wire Vision AI")

# Initialize session state variables to hold data across reruns
if 'jobs' not in st.session_state:
    st.session_state.jobs = []
if 'selected_job_details' not in st.session_state:
    st.session_state.selected_job_details = None


# --- API HELPER FUNCTIONS ---

def create_job_in_backend(filename, content_type, language):
    """Calls the POST /jobs endpoint to start the upload process."""
    try:
        url = f"{API_GATEWAY_BASE_URL}/jobs"
        payload = {"filename": filename, "contentType": content_type, "targetLanguage": language}
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error creating job: {e}")
        return None


def upload_file_to_s3(upload_url, file_object, content_type):
    """Uploads a file directly to S3 using a presigned URL."""
    try:
        headers = {'Content-Type': content_type}
        response = requests.put(upload_url, data=file_object, headers=headers)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"Error uploading file to S3: {e}")
        return False


def get_jobs_from_backend():
    """Calls the GET /jobs endpoint to refresh the job list."""
    try:
        url = f"{API_GATEWAY_BASE_URL}/jobs"
        response = requests.get(url)
        response.raise_for_status()
        # Sort jobs by timestamp, newest first, for a better UX
        sorted_jobs = sorted(response.json().get('jobs', []), key=lambda x: x.get('uploadTimestamp', ''), reverse=True)
        st.session_state.jobs = sorted_jobs
        st.toast("Job status refreshed!")
    except requests.exceptions.RequestException as e:
        st.error(f"Error refreshing job list: {e}")


def get_job_details(job_id):
    """Calls the GET /jobs/{jobId}/instructions endpoint to view details."""
    with st.spinner("Fetching instruction details..."):
        try:
            url = f"{API_GATEWAY_BASE_URL}/jobs/{job_id}/instructions"
            response = requests.get(url)
            response.raise_for_status()
            st.session_state.selected_job_details = response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching job details: {e}")
            st.session_state.selected_job_details = None


def get_pdf_download_url(job_id):
    """Calls the GET /jobs/{jobId}/download endpoint to get a PDF link."""
    try:
        url = f"{API_GATEWAY_BASE_URL}/jobs/{job_id}/download"
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('downloadUrl')
    except requests.exceptions.RequestException as e:
        st.error(f"Error generating PDF link: {e.response.text if e.response else e}")
        return None


# --- UI SECTIONS ---

# Section 1: Start a New Job
with st.container(border=True):
    st.subheader("1. Start a New Job")

    # Language dropdown with flags for better UX
    language_options = {
        "en": "🇬🇧 English",
        "es": "🇪🇸 Spanish",
        "fr": "🇫🇷 French"
    }
    target_language = st.selectbox(
        "Select Target Language for Instructions",
        options=language_options.keys(),
        format_func=lambda lang_code: language_options[lang_code]
    )

    uploaded_file = st.file_uploader("Upload Electrical Drawing", type=["png", "jpg", "jpeg"])

    if st.button("Start Processing", type="primary"):
        if uploaded_file is not None:
            # Step 1: Tell backend we want to upload and get a presigned URL
            job_info = create_job_in_backend(uploaded_file.name, uploaded_file.type, target_language)

            if job_info and "uploadUrl" in job_info:
                # Step 2: Upload the file directly to S3
                with st.spinner(f"Uploading {uploaded_file.name}..."):
                    upload_success = upload_file_to_s3(job_info["uploadUrl"], uploaded_file, uploaded_file.type)

                if upload_success:
                    st.success(f"Job '{job_info['jobId']}' created. Refreshing status...")
                    time.sleep(2)  # Give a moment for the backend to update DynamoDB
                    get_jobs_from_backend()
        else:
            st.warning("Please select a file to upload.")

# Section 2: Job Status Dashboard
with st.container(border=True):
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader("2. Job Status Dashboard")
    with col2:
        if st.button("Refresh ↻"):
            get_jobs_from_backend()

    # Automatically refresh the job list on the first load of the page
    if not st.session_state.jobs:
        get_jobs_from_backend()

    if st.session_state.jobs:
        # Table Header
        c1, c2, c3, c4, c5 = st.columns([3, 3, 1, 2, 3])
        c1.markdown("**Job ID**")
        c2.markdown("**Filename**")
        c3.markdown("**Lang**")
        c4.markdown("**Status**")
        c5.markdown("**Actions**")
        st.divider()

        # Table Rows
        for job in st.session_state.jobs:
            c1, c2, c3, c4, c5 = st.columns([3, 3, 1, 2, 3])

            # Use 'id' from the job object, as this is the primary key from DynamoDB
            job_id_from_db = job.get('id')
            c1.code(job_id_from_db)
            c2.write(job.get('originalFilename'))
            c3.write(job.get('targetLanguage', 'N/A').upper())

            status = job.get('status', 'UNKNOWN')
            if status == "DONE":
                c4.success("✅ DONE")
                action_cols = c5.columns(2)
                # Pass the correct 'id' to the functions
                if action_cols[0].button("View", key=f"view_{job_id_from_db}"):
                    get_job_details(job_id_from_db)
                if action_cols[1].button("PDF", key=f"pdf_{job_id_from_db}"):
                    with st.spinner("Generating PDF link..."):
                        download_url = get_pdf_download_url(job_id_from_db)
                        if download_url:
                            # Store the link in session state to persist it
                            st.session_state[f"dl_{job_id_from_db}"] = download_url
            elif status == "PENDING_PDF":
                c4.info("📄 Generating PDF...")
            elif status == "PROCESSING":
                c4.warning("⏳ PROCESSING")
            else:
                c4.write(status)  # Handles PENDING_UPLOAD or FAILED states

            # Display the download link if it has been generated for this specific job
            if f"dl_{job_id_from_db}" in st.session_state:
                c5.link_button("Download PDF", st.session_state[f"dl_{job_id_from_db}"])

            st.divider()

# Section 3: Instruction Viewer
if st.session_state.selected_job_details:
    with st.container(border=True):
        job_details = st.session_state.selected_job_details
        st.subheader(f"3. Instruction Viewer for Job ID: `{job_details.get('jobId')}`")

        col_img, col_inst = st.columns(2)

        with col_img:
            st.markdown("#### Original Drawing")
            if job_details.get('originalDrawingUrl'):
                st.image(job_details.get('originalDrawingUrl'), use_container_width=True)
            else:
                st.warning("Original drawing URL not available.")

        with col_inst:
            instructions_obj = job_details.get('instructions', {})
            lang = job_details.get('targetLanguage', 'en')
            lang_name = {"en": "English", "es": "Spanish", "fr": "French"}.get(lang, lang.upper())
            st.markdown(f"#### Generated Instructions ({lang_name})")

            if lang == 'en':
                instruction_text = instructions_obj.get('englishInstructions')
            else:
                instruction_key = f"translatedInstructions_{lang}"
                instruction_text = instructions_obj.get(instruction_key)

            if not instruction_text:
                instruction_text = instructions_obj.get('englishInstructions', "Instructions not available.")

            # Use st.markdown to render the formatted text generated by the AI
            st.markdown(instruction_text)