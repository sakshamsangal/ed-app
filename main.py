import streamlit as st
# import boto3  # Good to have for potential future local testing, though not strictly needed by the UI
import requests
import json
import time
import os
import uuid

# --- CONFIGURATION ---
# IMPORTANT: Replace this with your actual API Gateway Invoke URL from the AWS Console
API_GATEWAY_BASE_URL = "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev"  # e.g., https://a1b2c3d4e5.execute-api.us-east-1.amazonaws.com/dev

# --- UI Layout & State Management ---
st.set_page_config(layout="wide", page_title="Wirevision AI")
st.title("💡 Wirevision AI")

# Use session state to keep track of jobs and selected instruction
if 'jobs' not in st.session_state:
    st.session_state.jobs = []
if 'selected_job_details' not in st.session_state:
    st.session_state.selected_job_details = None


# --- API Helper Functions ---

def create_job_in_backend(filename, content_type, language):
    """Calls the POST /jobs endpoint to start the upload process."""
    try:
        url = f"{API_GATEWAY_BASE_URL}/jobs"
        payload = {
            "filename": filename,
            "contentType": content_type,
            "targetLanguage": language
        }
        st.info(f"Creating job for {filename}...")
        response = requests.post(url, json=payload)
        response.raise_for_status()
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
    """Calls the POST /jobs/{jobId}/download endpoint to get a PDF link."""
    try:
        url = f"{API_GATEWAY_BASE_URL}/jobs/{job_id}/download"
        response = requests.post(url)
        response.raise_for_status()
        return response.json().get('downloadUrl')
    except requests.exceptions.RequestException as e:
        st.error(f"Error generating PDF: {e}")
        return None


# --- UI SECTIONS ---

# Section 1: Start a New Job
with st.container(border=True):
    st.subheader("1. Start a New Job")

    target_language = st.selectbox(
        "Select Target Language for Instructions",
        ("es", "fr"),
        format_func=lambda x: {"es": "Spanish", "fr": "French"}.get(x, x.upper())
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
                    st.success(f"Job '{job_info['jobId']}' created and file uploaded. Refreshing status...")
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

    # Automatically refresh the job list on first load
    if not st.session_state.jobs:
        get_jobs_from_backend()

    if not st.session_state.jobs:
        st.info("No jobs found. Upload a drawing to get started.")
    else:
        # Table Header
        c1, c2, c3, c4, c5, c6 = st.columns([3, 3, 1, 2, 2, 2])
        c1.markdown("**Job ID**")
        c2.markdown("**Filename**")
        c3.markdown("**Lang**")
        c4.markdown("**Status**")
        c5.markdown("**View in App**")
        c6.markdown("**Download PDF**")
        st.divider()

        # Table Rows
        for job in st.session_state.jobs:
            c1, c2, c3, c4, c5, c6 = st.columns([3, 3, 1, 2, 2, 2])
            c1.code(job.get('jobId'))
            c2.write(job.get('originalFilename'))
            c3.write(job.get('targetLanguage', 'N/A').upper())

            status = job.get('status', 'UNKNOWN')
            if status == "DONE":
                c4.success("✅ DONE")
                if c5.button("View", key=f"view_{job.get('jobId')}"):
                    get_job_details(job.get('jobId'))
                if c6.button("Generate PDF", key=f"pdf_{job.get('jobId')}"):
                    with st.spinner("Generating PDF..."):
                        download_url = get_pdf_download_url(job.get('jobId'))
                        if download_url:
                            # Use st.link_button for a clean UI element
                            st.session_state[f"dl_{job.get('jobId')}"] = download_url
            else:
                c4.warning("⏳ PROCESSING")

            # Display the download link if it has been generated
            if f"dl_{job.get('jobId')}" in st.session_state:
                c6.link_button("Click to Download", st.session_state[f"dl_{job.get('jobId')}"])

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
                st.image(job_details.get('originalDrawingUrl'), use_column_width=True)
            else:
                st.warning("Original drawing URL not found.")

        with col_inst:
            lang = job_details.get('instructions', {}).get('targetLanguage', 'en')
            lang_name = {"es": "Spanish", "fr": "French", "en": "English"}.get(lang, "Translated")
            st.markdown(f"#### Generated Instructions ({lang_name})")

            instruction_key = f"translatedInstructions_{lang}"
            instruction_text = job_details.get('instructions', {}).get(instruction_key)

            if not instruction_text:
                instruction_text = job_details.get('instructions', {}).get('englishInstructions',
                                                                           "Instructions not available.")

            # Use st.markdown to render the formatted text from the AI
            st.markdown(instruction_text)