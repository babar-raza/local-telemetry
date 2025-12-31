#!/usr/bin/env python3
"""Streamlit dashboard for viewing and editing agent telemetry data."""

import os
import streamlit as st
import pandas as pd
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

# Configuration
API_BASE_URL = os.environ.get("TELEMETRY_API_URL", "http://localhost:8765")

# ============================================================================
# API Client
# ============================================================================

class TelemetryAPIClient:
    """Client for interacting with the Telemetry FastAPI service."""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url

    def health_check(self) -> bool:
        """Check if API is reachable."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def get_runs(
        self,
        agent_name: Optional[str] = None,
        status: Optional[str] = None,
        created_before: Optional[str] = None,
        created_after: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Query runs with filters."""
        params = {
            "limit": limit,
            "offset": offset
        }
        if agent_name:
            params["agent_name"] = agent_name
        if status:
            params["status"] = status
        if created_before:
            params["created_before"] = created_before
        if created_after:
            params["created_after"] = created_after

        response = requests.get(f"{self.base_url}/api/v1/runs", params=params)
        response.raise_for_status()
        return response.json()

    def update_run(self, event_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update run via PATCH endpoint."""
        # Remove None values (don't update fields not changed)
        payload = {k: v for k, v in updates.items() if v is not None}

        response = requests.patch(
            f"{self.base_url}/api/v1/runs/{event_id}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

# ============================================================================
# Utility Functions
# ============================================================================

def format_duration(duration_ms: Optional[int]) -> str:
    """Format duration_ms as human-readable string."""
    if duration_ms is None:
        return "N/A"
    seconds = duration_ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

def truncate_text(text: Optional[str], max_length: int = 50) -> str:
    """Truncate text to max_length with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

def validate_status(status: str) -> bool:
    """Validate status enum."""
    return status in ["running", "success", "failed", "partial", "timeout", "cancelled"]

# ============================================================================
# Page Configuration
# ============================================================================

st.set_page_config(
    page_title="Telemetry Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize API client
client = TelemetryAPIClient()

# ============================================================================
# Sidebar - API Health Check and Filters
# ============================================================================

with st.sidebar:
    st.title("📊 Telemetry Dashboard")

    # Health check
    st.subheader("API Status")
    if client.health_check():
        st.success("✅ API Connected")
    else:
        st.error(f"❌ Cannot connect to API at {API_BASE_URL}")
        st.info("Start the service: `python telemetry_service.py`")

    st.divider()

    # Fetch metadata for filters (cached)
    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def get_filter_options():
        """Fetch distinct agent names and job types from API."""
        try:
            # Fetch a large sample to get all unique values
            sample_runs = client.get_runs(limit=1000)

            agent_names = sorted(list(set(r.get("agent_name") for r in sample_runs if r.get("agent_name"))))
            job_types = sorted(list(set(r.get("job_type") for r in sample_runs if r.get("job_type"))))

            return agent_names, job_types
        except Exception:
            return [], []

    available_agents, available_job_types = get_filter_options()

    # Filters
    st.subheader("Filters")

    # Show count of available options
    if available_agents:
        st.caption(f"📊 {len(available_agents)} agents, {len(available_job_types)} job types")

        # Refresh filter options button
        if st.button("🔄 Refresh Filter Options", help="Reload agent names and job types"):
            get_filter_options.clear()
            st.rerun()
    else:
        st.warning("⚠️ No data available. Load some runs first.")

    # Agent name filter (dropdown with auto-populated values)
    filter_agent = st.selectbox(
        "Agent Name",
        options=["All"] + available_agents,
        index=0,
        help="Select agent to filter"
    )

    # Convert "All" to None for API query
    if filter_agent == "All":
        filter_agent = None

    # Status filter
    filter_status = st.multiselect(
        "Status",
        options=["running", "success", "failed", "partial", "timeout", "cancelled"],
        help="Select one or more statuses"
    )

    # Date range filter
    st.write("Date Range")
    col1, col2 = st.columns(2)
    with col1:
        filter_date_from = st.date_input(
            "From",
            value=None,
            help="Start date (inclusive)"
        )
    with col2:
        filter_date_to = st.date_input(
            "To",
            value=None,
            help="End date (inclusive)"
        )

    # Job type filter (dropdown with auto-populated values)
    filter_job_type = st.selectbox(
        "Job Type",
        options=["All"] + available_job_types,
        index=0,
        help="Select job type to filter"
    )

    # Convert "All" to None for filtering
    if filter_job_type == "All":
        filter_job_type = None

    # Exclude test data
    exclude_test = st.checkbox(
        "Exclude test data (job_type='test')",
        value=True,
        help="Filter out test entries"
    )

    st.divider()

    # Pagination
    st.subheader("Pagination")
    limit = st.number_input("Rows per page", min_value=10, max_value=500, value=100, step=10)
    offset = st.number_input("Offset", min_value=0, value=0, step=100)

    st.divider()

    # Actions
    refresh_button = st.button("🔄 Refresh Data", width='stretch')
    clear_filters = st.button("🗑️ Clear Filters", width='stretch')

# ============================================================================
# Main Content - Tabs
# ============================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 Browse Runs",
    "✏️ Edit Single Run",
    "📝 Bulk Edit",
    "📈 Analytics",
    "💾 Export"
])

# ============================================================================
# Tab 1: Browse Runs
# ============================================================================

with tab1:
    st.header("Browse Agent Runs")

    if clear_filters:
        st.rerun()

    try:
        # Build query parameters
        query_params = {
            "limit": int(limit),
            "offset": int(offset)
        }

        if filter_agent:
            query_params["agent_name"] = filter_agent

        if filter_status:
            # API accepts single status, so we'll query multiple times
            # For simplicity, let's just use the first status for now
            query_params["status"] = filter_status[0] if filter_status else None

        if filter_date_from:
            query_params["created_after"] = filter_date_from.isoformat()

        if filter_date_to:
            # Add 1 day to include the entire end date
            end_date = filter_date_to + timedelta(days=1)
            query_params["created_before"] = end_date.isoformat()

        # Fetch data
        with st.spinner("Loading data..."):
            runs = client.get_runs(**query_params)

        if not runs:
            st.info("No runs found matching the filters.")
        else:
            # Filter out test data if requested
            if exclude_test:
                runs = [r for r in runs if r.get("job_type") != "test"]

            # Filter by job_type if specified (exact match)
            if filter_job_type:
                runs = [r for r in runs if r.get("job_type") == filter_job_type]

            # Display count
            st.success(f"Found {len(runs)} run(s)")

            # Convert to DataFrame for display
            df_data = []
            for run in runs:
                df_data.append({
                    "event_id": run.get("event_id"),
                    "run_id": run.get("run_id", "")[:8],  # Short format
                    "agent_name": run.get("agent_name"),
                    "job_type": run.get("job_type"),
                    "status": run.get("status"),
                    "start_time": run.get("start_time", "")[:19] if run.get("start_time") else "",
                    "duration": format_duration(run.get("duration_ms")),
                    "items_discovered": run.get("items_discovered"),
                    "items_succeeded": run.get("items_succeeded"),
                    "items_failed": run.get("items_failed"),
                    "error_summary": truncate_text(run.get("error_summary"), 50)
                })

            df = pd.DataFrame(df_data)

            # Store in session state for use in other tabs
            st.session_state.runs_data = runs
            st.session_state.runs_df = df

            # Display dataframe
            st.dataframe(
                df.drop(columns=["event_id"]),  # Hide event_id
                width='stretch',
                height=600
            )

            # Selection for editing
            st.subheader("Quick Actions")
            selected_run_id = st.selectbox(
                "Select run to edit",
                options=df["run_id"].tolist(),
                help="Select a run to edit in the 'Edit Single Run' tab"
            )

            if selected_run_id:
                # Find the event_id for the selected run_id
                selected_event_id = df[df["run_id"] == selected_run_id]["event_id"].iloc[0]
                st.session_state.selected_event_id = selected_event_id
                st.info(f"Selected event_id: {selected_event_id}")
                st.info("Switch to the 'Edit Single Run' tab to modify this record.")

    except requests.RequestException as e:
        st.error(f"❌ Failed to connect to API: {str(e)}")
        st.info(f"Please ensure the API service is running at {API_BASE_URL}")
        st.code(f"curl {API_BASE_URL}/health", language="bash")
    except Exception as e:
        st.error(f"❌ Error loading data: {str(e)}")
        st.exception(e)

# ============================================================================
# Tab 2: Edit Single Run
# ============================================================================

with tab2:
    st.header("Edit Single Run")

    # Event ID input
    col1, col2 = st.columns([3, 1])
    with col1:
        event_id_input = st.text_input(
            "Event ID",
            value=st.session_state.get("selected_event_id", ""),
            placeholder="Enter event_id or select from Browse tab",
            help="UUID of the run to edit"
        )
    with col2:
        fetch_button = st.button("🔍 Fetch Current Values", width='stretch')

    # Initialize session state for form data
    if "edit_form_data" not in st.session_state:
        st.session_state.edit_form_data = {}

    # Fetch current values
    if fetch_button and event_id_input:
        try:
            with st.spinner("Fetching run data..."):
                # Query by event_id - we need to get all runs and filter
                all_runs = client.get_runs(limit=1000)
                run_data = next((r for r in all_runs if r.get("event_id") == event_id_input), None)

                if run_data:
                    st.session_state.edit_form_data = run_data
                    st.success(f"✅ Loaded run: {run_data.get('agent_name')} - {run_data.get('job_type')}")
                else:
                    st.error(f"❌ No run found with event_id: {event_id_input}")
        except requests.RequestException as e:
            st.error(f"❌ Failed to fetch data from API: {str(e)}")
            st.info("Please ensure the API service is running and accessible at " + API_BASE_URL)
        except Exception as e:
            st.error(f"❌ Error fetching run: {str(e)}")

    # Display edit form if data is loaded
    if st.session_state.edit_form_data:
        run_data = st.session_state.edit_form_data

        st.divider()
        st.subheader("Current Run Information")

        # Display read-only fields
        col1, col2, col3 = st.columns(3)
        with col1:
            st.text_input("Agent Name", value=run_data.get("agent_name", ""), disabled=True)
        with col2:
            st.text_input("Job Type", value=run_data.get("job_type", ""), disabled=True)
        with col3:
            st.text_input("Start Time", value=run_data.get("start_time", "")[:19] if run_data.get("start_time") else "", disabled=True)

        st.divider()
        st.subheader("Editable Fields")

        with st.form("edit_run_form"):
            # Status (enum)
            status_value = st.selectbox(
                "Status *",
                options=["running", "success", "failed", "partial", "timeout", "cancelled"],
                index=["running", "success", "failed", "partial", "timeout", "cancelled"].index(run_data.get("status", "running")),
                help="Current status of the run"
            )

            # End time
            end_time_value = st.text_input(
                "End Time",
                value=run_data.get("end_time", "") or "",
                placeholder="2025-12-31T12:00:00Z",
                help="ISO 8601 format (optional)"
            )

            # Duration
            duration_ms_value = st.number_input(
                "Duration (ms)",
                value=run_data.get("duration_ms") or 0,
                min_value=0,
                step=1000,
                help="Duration in milliseconds (must be ≥ 0)"
            )

            # Item counts
            col1, col2, col3 = st.columns(3)
            with col1:
                items_succeeded_value = st.number_input(
                    "Items Succeeded",
                    value=run_data.get("items_succeeded") or 0,
                    min_value=0,
                    step=1,
                    help="Number of successfully processed items"
                )
            with col2:
                items_failed_value = st.number_input(
                    "Items Failed",
                    value=run_data.get("items_failed") or 0,
                    min_value=0,
                    step=1,
                    help="Number of failed items"
                )
            with col3:
                items_skipped_value = st.number_input(
                    "Items Skipped",
                    value=run_data.get("items_skipped") or 0,
                    min_value=0,
                    step=1,
                    help="Number of skipped items"
                )

            # Error fields
            error_summary_value = st.text_input(
                "Error Summary",
                value=run_data.get("error_summary", "") or "",
                max_chars=500,
                help="Brief error description (max 500 chars)"
            )

            error_details_value = st.text_area(
                "Error Details",
                value=run_data.get("error_details", "") or "",
                max_chars=5000,
                height=100,
                help="Detailed error information (max 5000 chars)"
            )

            # Output summary
            output_summary_value = st.text_area(
                "Output Summary",
                value=run_data.get("output_summary", "") or "",
                max_chars=1000,
                height=100,
                help="Summary of run output (max 1000 chars)"
            )

            # JSON fields
            st.subheader("JSON Fields")

            metrics_json_value = st.text_area(
                "Metrics JSON",
                value=str(run_data.get("metrics_json", "")) if run_data.get("metrics_json") else "",
                height=100,
                help="Custom metrics as JSON object"
            )

            context_json_value = st.text_area(
                "Context JSON",
                value=str(run_data.get("context_json", "")) if run_data.get("context_json") else "",
                height=100,
                help="Additional context as JSON object"
            )

            # Form buttons
            col1, col2 = st.columns(2)
            with col1:
                submit_button = st.form_submit_button("✅ Update Run", width='stretch')
            with col2:
                clear_button = st.form_submit_button("🗑️ Clear Form", width='stretch')

        # Handle form submission
        if submit_button:
            try:
                # Validate JSON fields
                import json
                validation_errors = []

                if metrics_json_value:
                    try:
                        metrics_json_parsed = json.loads(metrics_json_value)
                    except json.JSONDecodeError as e:
                        validation_errors.append(f"Invalid Metrics JSON: {str(e)}")
                        metrics_json_parsed = None
                else:
                    metrics_json_parsed = None

                if context_json_value:
                    try:
                        context_json_parsed = json.loads(context_json_value)
                    except json.JSONDecodeError as e:
                        validation_errors.append(f"Invalid Context JSON: {str(e)}")
                        context_json_parsed = None
                else:
                    context_json_parsed = None

                # Validate status
                if not validate_status(status_value):
                    validation_errors.append(f"Invalid status: {status_value}")

                # Display validation errors
                if validation_errors:
                    for error in validation_errors:
                        st.error(f"❌ {error}")
                else:
                    # Prepare update payload
                    updates = {
                        "status": status_value,
                        "end_time": end_time_value if end_time_value else None,
                        "duration_ms": int(duration_ms_value) if duration_ms_value else None,
                        "error_summary": error_summary_value if error_summary_value else None,
                        "error_details": error_details_value if error_details_value else None,
                        "output_summary": output_summary_value if output_summary_value else None,
                        "items_succeeded": int(items_succeeded_value) if items_succeeded_value is not None else None,
                        "items_failed": int(items_failed_value) if items_failed_value is not None else None,
                        "items_skipped": int(items_skipped_value) if items_skipped_value is not None else None,
                        "metrics_json": metrics_json_parsed,
                        "context_json": context_json_parsed
                    }

                    # Send PATCH request
                    with st.spinner("Updating run..."):
                        result = client.update_run(event_id_input, updates)
                        st.success(f"✅ Successfully updated run: {event_id_input}")
                        st.json(result)

                        # Clear session state to force re-fetch
                        if "runs_data" in st.session_state:
                            del st.session_state.runs_data
                        if "runs_df" in st.session_state:
                            del st.session_state.runs_df

            except requests.HTTPError as e:
                st.error(f"❌ API Error: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                st.error(f"❌ Error updating run: {str(e)}")
                st.exception(e)

        # Handle clear button
        if clear_button:
            st.session_state.edit_form_data = {}
            st.session_state.selected_event_id = ""
            st.rerun()

    else:
        st.info("👆 Enter an event_id and click 'Fetch Current Values' to start editing, or select a run from the Browse tab.")

# ============================================================================
# Tab 3: Bulk Edit
# ============================================================================

with tab3:
    st.header("Bulk Edit Operations")

    # Check if we have runs data from Browse tab
    if "runs_data" not in st.session_state or not st.session_state.runs_data:
        st.warning("⚠️ No runs data available. Please go to the 'Browse Runs' tab and load some data first.")
    else:
        runs_data = st.session_state.runs_data
        runs_df = st.session_state.runs_df

        st.info(f"📊 Loaded {len(runs_data)} runs from Browse tab")

        # Step 1: Select runs to bulk edit
        st.subheader("Step 1: Select Runs")

        # Multiselect by run_id
        selected_run_ids = st.multiselect(
            "Select runs to edit",
            options=runs_df["run_id"].tolist(),
            help="Select multiple runs to edit at once"
        )

        if selected_run_ids:
            # Get full event_ids for selected runs
            selected_event_ids = runs_df[runs_df["run_id"].isin(selected_run_ids)]["event_id"].tolist()

            st.success(f"✅ Selected {len(selected_run_ids)} run(s)")

            # Show selected runs summary
            with st.expander("📋 View Selected Runs"):
                selected_df = runs_df[runs_df["run_id"].isin(selected_run_ids)].drop(columns=["event_id"])
                st.dataframe(selected_df, width='stretch')

            st.divider()

            # Step 2: Choose field to edit
            st.subheader("Step 2: Choose Field to Edit")

            field_to_edit = st.selectbox(
                "Field to update",
                options=[
                    "status",
                    "end_time",
                    "duration_ms",
                    "error_summary",
                    "error_details",
                    "output_summary",
                    "items_succeeded",
                    "items_failed",
                    "items_skipped"
                ],
                help="Select which field to update for all selected runs"
            )

            st.divider()

            # Step 3: Enter new value
            st.subheader("Step 3: Enter New Value")

            # Dynamic input based on field type
            new_value = None

            if field_to_edit == "status":
                new_value = st.selectbox(
                    "New Status",
                    options=["running", "success", "failed", "partial", "timeout", "cancelled"]
                )
            elif field_to_edit == "end_time":
                new_value = st.text_input(
                    "New End Time",
                    placeholder="2025-12-31T12:00:00Z",
                    help="ISO 8601 format"
                )
            elif field_to_edit == "duration_ms":
                new_value = st.number_input(
                    "New Duration (ms)",
                    min_value=0,
                    step=1000,
                    help="Duration in milliseconds"
                )
            elif field_to_edit in ["error_summary", "output_summary"]:
                new_value = st.text_input(
                    f"New {field_to_edit.replace('_', ' ').title()}",
                    max_chars=500 if field_to_edit == "error_summary" else 1000
                )
            elif field_to_edit == "error_details":
                new_value = st.text_area(
                    "New Error Details",
                    max_chars=5000,
                    height=100
                )
            elif field_to_edit in ["items_succeeded", "items_failed", "items_skipped"]:
                new_value = st.number_input(
                    f"New {field_to_edit.replace('_', ' ').title()}",
                    min_value=0,
                    step=1
                )

            # Option to clear field (set to None)
            clear_field = st.checkbox(
                "Clear this field (set to null/empty)",
                help="Check this to set the field to null instead of a specific value"
            )

            if clear_field:
                new_value = None

            st.divider()

            # Step 4: Preview changes
            st.subheader("Step 4: Preview Changes")

            # Show preview table
            preview_data = []
            for run_id in selected_run_ids:
                run_idx = runs_df[runs_df["run_id"] == run_id].index[0]
                full_run = runs_data[run_idx]

                old_value = full_run.get(field_to_edit)
                preview_data.append({
                    "run_id": run_id,
                    "agent_name": full_run.get("agent_name"),
                    "old_value": str(old_value) if old_value is not None else "(empty)",
                    "new_value": str(new_value) if new_value is not None else "(empty)"
                })

            preview_df = pd.DataFrame(preview_data)
            st.dataframe(preview_df, width='stretch')

            st.divider()

            # Step 5: Confirm and execute
            st.subheader("Step 5: Execute Bulk Update")

            col1, col2 = st.columns([1, 3])
            with col1:
                execute_button = st.button(
                    f"🚀 Update {len(selected_run_ids)} Run(s)",
                    type="primary",
                    width='stretch'
                )

            if execute_button:
                # Execute bulk update
                success_count = 0
                failure_count = 0
                failed_event_ids = []

                # Progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()

                for idx, event_id in enumerate(selected_event_ids):
                    try:
                        # Prepare update payload
                        updates = {field_to_edit: new_value}

                        # Send PATCH request
                        client.update_run(event_id, updates)
                        success_count += 1

                    except Exception as e:
                        failure_count += 1
                        failed_event_ids.append(event_id)

                    # Update progress
                    progress = (idx + 1) / len(selected_event_ids)
                    progress_bar.progress(progress)
                    status_text.text(f"Processing {idx + 1}/{len(selected_event_ids)}...")

                # Clear progress indicators
                progress_bar.empty()
                status_text.empty()

                # Display results
                st.divider()
                st.subheader("📊 Bulk Update Results")

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("✅ Successful Updates", success_count)
                with col2:
                    st.metric("❌ Failed Updates", failure_count)

                if failure_count > 0:
                    st.error(f"❌ {failure_count} update(s) failed")
                    with st.expander("View Failed Event IDs"):
                        for event_id in failed_event_ids:
                            st.code(event_id)

                    # Retry button
                    if st.button("🔁 Retry Failed Updates"):
                        st.info("Retry functionality coming soon...")
                else:
                    st.success(f"✅ All {success_count} update(s) completed successfully!")

                # Clear session state to force re-fetch
                if "runs_data" in st.session_state:
                    del st.session_state.runs_data
                if "runs_df" in st.session_state:
                    del st.session_state.runs_df

                st.info("💡 Go back to the 'Browse Runs' tab and refresh to see the updated data.")

        else:
            st.info("👆 Select one or more runs from the dropdown above to begin bulk editing.")

# ============================================================================
# Tab 4: Analytics
# ============================================================================

with tab4:
    st.header("Analytics & Charts")

    # Check if we have runs data
    if "runs_data" not in st.session_state or not st.session_state.runs_data:
        st.warning("⚠️ No runs data available. Please go to the 'Browse Runs' tab and load some data first.")
    else:
        runs_data = st.session_state.runs_data

        # Convert to DataFrame for easier analysis
        df_analytics = pd.DataFrame(runs_data)

        # Filters
        st.subheader("Filters")
        col1, col2, col3 = st.columns(3)

        with col1:
            filter_agents = st.multiselect(
                "Filter by Agent",
                options=df_analytics["agent_name"].unique().tolist(),
                default=df_analytics["agent_name"].unique().tolist(),
                help="Select agents to include"
            )

        with col2:
            exclude_test_analytics = st.checkbox(
                "Exclude test data",
                value=True,
                help="Exclude runs with job_type='test'"
            )

        with col3:
            refresh_analytics = st.button("🔄 Refresh Charts", width='stretch')

        # Apply filters
        df_filtered = df_analytics[df_analytics["agent_name"].isin(filter_agents)]

        if exclude_test_analytics:
            df_filtered = df_filtered[df_filtered["job_type"] != "test"]

        st.info(f"📊 Analyzing {len(df_filtered)} run(s)")

        st.divider()

        # Import plotly
        import plotly.express as px
        import plotly.graph_objects as go
        from datetime import datetime

        # Chart 1: Success Rate by Agent
        st.subheader("1. Success Rate by Agent")

        status_by_agent = df_filtered.groupby(["agent_name", "status"]).size().reset_index(name="count")

        if len(status_by_agent) == 0:
            st.info("📊 No status data available for the selected filters.")
        else:
            fig1 = px.bar(
                status_by_agent,
                x="agent_name",
                y="count",
                color="status",
                title="Run Status Distribution by Agent",
                labels={"count": "Number of Runs", "agent_name": "Agent Name"},
                color_discrete_map={
                    "success": "#28a745",
                    "failed": "#dc3545",
                    "running": "#ffc107",
                    "partial": "#fd7e14",
                    "timeout": "#6c757d",
                    "cancelled": "#17a2b8"
                }
            )
            fig1.update_layout(height=400)
            st.plotly_chart(fig1, width='stretch')

        st.divider()

        # Chart 2: Agent Activity Timeline
        st.subheader("2. Agent Activity Timeline")

        # Convert start_time to date
        df_timeline = df_filtered.copy()
        df_timeline["date"] = pd.to_datetime(df_timeline["start_time"]).dt.date

        timeline_data = df_timeline.groupby(["date", "agent_name"]).size().reset_index(name="count")

        if len(timeline_data) == 0:
            st.info("📊 No timeline data available for the selected filters.")
        else:
            fig2 = px.line(
                timeline_data,
                x="date",
                y="count",
                color="agent_name",
                title="Daily Agent Activity",
                labels={"count": "Number of Runs", "date": "Date"},
                markers=True
            )
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, width='stretch')

        st.divider()

        # Chart 3: Item Processing Metrics
        st.subheader("3. Item Processing Metrics")

        # Aggregate items by agent
        items_data = df_filtered.groupby("agent_name").agg({
            "items_discovered": "sum",
            "items_succeeded": "sum",
            "items_failed": "sum",
            "items_skipped": "sum"
        }).reset_index()

        if len(items_data) == 0:
            st.info("📊 No item processing data available for the selected filters.")
        else:
            fig3 = go.Figure()

            fig3.add_trace(go.Bar(
                name="Discovered",
                x=items_data["agent_name"],
                y=items_data["items_discovered"],
                marker_color="#17a2b8"
            ))

            fig3.add_trace(go.Bar(
                name="Succeeded",
                x=items_data["agent_name"],
                y=items_data["items_succeeded"],
                marker_color="#28a745"
            ))

            fig3.add_trace(go.Bar(
                name="Failed",
                x=items_data["agent_name"],
                y=items_data["items_failed"],
                marker_color="#dc3545"
            ))

            fig3.add_trace(go.Bar(
                name="Skipped",
                x=items_data["agent_name"],
                y=items_data["items_skipped"],
                marker_color="#ffc107"
            ))

            fig3.update_layout(
                title="Item Processing by Agent",
                xaxis_title="Agent Name",
                yaxis_title="Item Count",
                barmode="group",
                height=400
            )

            st.plotly_chart(fig3, width='stretch')

        st.divider()

        # Chart 4: Duration Distribution
        st.subheader("4. Duration Distribution")

        # Filter out null durations
        df_duration = df_filtered[df_filtered["duration_ms"].notna()].copy()

        if len(df_duration) > 0:
            # Convert to seconds for better readability
            df_duration["duration_s"] = df_duration["duration_ms"] / 1000

            fig4 = px.histogram(
                df_duration,
                x="duration_s",
                nbins=30,
                title="Run Duration Distribution",
                labels={"duration_s": "Duration (seconds)", "count": "Number of Runs"},
                color_discrete_sequence=["#007bff"]
            )
            fig4.update_layout(height=400)
            st.plotly_chart(fig4, width='stretch')

            # Show duration stats
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Min Duration", f"{df_duration['duration_s'].min():.1f}s")
            with col2:
                st.metric("Max Duration", f"{df_duration['duration_s'].max():.1f}s")
            with col3:
                st.metric("Avg Duration", f"{df_duration['duration_s'].mean():.1f}s")
            with col4:
                st.metric("Median Duration", f"{df_duration['duration_s'].median():.1f}s")
        else:
            st.info("No duration data available for selected runs.")

        st.divider()

        # Chart 5: Job Type Breakdown
        st.subheader("5. Job Type Breakdown")

        # Prepare data for treemap
        job_type_data = df_filtered.groupby(["agent_name", "job_type"]).size().reset_index(name="count")

        if len(job_type_data) == 0:
            st.info("📊 No job type data available for the selected filters.")
        else:
            fig5 = px.treemap(
                job_type_data,
                path=["agent_name", "job_type"],
                values="count",
                title="Job Type Distribution by Agent",
                color="count",
                color_continuous_scale="Blues"
            )
            fig5.update_layout(height=500)
            st.plotly_chart(fig5, width='stretch')

        st.divider()

        # Summary Statistics
        st.subheader("📊 Summary Statistics")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            total_runs = len(df_filtered)
            st.metric("Total Runs", total_runs)

        with col2:
            success_rate = (len(df_filtered[df_filtered["status"] == "success"]) / total_runs * 100) if total_runs > 0 else 0
            st.metric("Success Rate", f"{success_rate:.1f}%")

        with col3:
            total_items_processed = df_filtered["items_discovered"].sum()
            st.metric("Total Items Processed", f"{total_items_processed:,.0f}")

        with col4:
            total_items_succeeded = df_filtered["items_succeeded"].sum()
            st.metric("Total Items Succeeded", f"{total_items_succeeded:,.0f}")

# ============================================================================
# Tab 5: Export
# ============================================================================

with tab5:
    st.header("Export Data")

    # Check if we have runs data
    if "runs_data" not in st.session_state or not st.session_state.runs_data:
        st.warning("⚠️ No runs data available. Please go to the 'Browse Runs' tab and load some data first.")
    else:
        runs_data = st.session_state.runs_data
        df_export = pd.DataFrame(runs_data)

        st.info(f"📊 Ready to export {len(df_export)} run(s)")

        st.divider()

        # Export configuration
        st.subheader("Export Configuration")

        # Column selection
        all_columns = df_export.columns.tolist()
        default_columns = [
            "event_id", "run_id", "agent_name", "job_type", "status",
            "start_time", "end_time", "duration_ms",
            "items_discovered", "items_succeeded", "items_failed",
            "error_summary", "output_summary"
        ]
        # Only include columns that exist in the data
        default_columns = [col for col in default_columns if col in all_columns]

        selected_columns = st.multiselect(
            "Select columns to export",
            options=all_columns,
            default=default_columns,
            help="Choose which fields to include in the export"
        )

        # Filter configuration
        col1, col2 = st.columns(2)

        with col1:
            exclude_test_export = st.checkbox(
                "Exclude test data (job_type='test')",
                value=True,
                help="Filter out test entries from export"
            )

        with col2:
            limit_rows = st.number_input(
                "Limit rows (0 = all)",
                min_value=0,
                value=0,
                step=100,
                help="Limit number of rows to export (0 for all)"
            )

        # Apply filters
        df_to_export = df_export.copy()

        if exclude_test_export:
            df_to_export = df_to_export[df_to_export["job_type"] != "test"]

        if selected_columns:
            # Only select columns that exist in the dataframe
            valid_columns = [col for col in selected_columns if col in df_to_export.columns]
            df_to_export = df_to_export[valid_columns]

        if limit_rows > 0:
            df_to_export = df_to_export.head(limit_rows)

        if len(df_to_export) == 0:
            st.warning("⚠️ No data to export with current filters. Try adjusting your criteria.")
        else:
            st.success(f"✅ {len(df_to_export)} row(s) with {len(df_to_export.columns)} column(s) ready to export")

        st.divider()

        # Preview
        st.subheader("Preview")

        if len(df_to_export) > 0:
            with st.expander("👁️ Preview Export Data (first 100 rows)"):
                st.dataframe(df_to_export.head(100), width='stretch')

        st.divider()

        # Export buttons
        st.subheader("Export Options")

        # Only show export buttons if there's data
        if len(df_to_export) == 0:
            st.warning("⚠️ No data available to export. Please load data in the Browse tab first.")
            st.stop()

        col1, col2, col3 = st.columns(3)

        with col1:
            # CSV Export
            st.markdown("### 📄 CSV Export")

            csv_data = df_to_export.to_csv(index=False)

            st.download_button(
                label="⬇️ Download CSV",
                data=csv_data,
                file_name=f"telemetry_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                width='stretch'
            )

        with col2:
            # Excel Export
            st.markdown("### 📊 Excel Export")

            from io import BytesIO

            excel_buffer = BytesIO()

            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                # Write runs data
                df_to_export.to_excel(writer, sheet_name='Runs', index=False)

                # Write summary statistics
                summary_data = {
                    "Metric": [
                        "Total Runs",
                        "Successful Runs",
                        "Failed Runs",
                        "Success Rate (%)",
                        "Total Items Discovered",
                        "Total Items Succeeded",
                        "Total Items Failed"
                    ],
                    "Value": [
                        len(df_to_export),
                        len(df_to_export[df_to_export["status"] == "success"]),
                        len(df_to_export[df_to_export["status"] == "failed"]),
                        f"{(len(df_to_export[df_to_export['status'] == 'success']) / len(df_to_export) * 100):.2f}" if len(df_to_export) > 0 else "0",
                        df_to_export["items_discovered"].sum() if "items_discovered" in df_to_export.columns else 0,
                        df_to_export["items_succeeded"].sum() if "items_succeeded" in df_to_export.columns else 0,
                        df_to_export["items_failed"].sum() if "items_failed" in df_to_export.columns else 0
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)

                # Write agent breakdown
                if "agent_name" in df_to_export.columns and "status" in df_to_export.columns:
                    agent_breakdown = df_to_export.groupby(["agent_name", "status"]).size().reset_index(name="count")
                    agent_breakdown.to_excel(writer, sheet_name='Agent Breakdown', index=False)

            excel_data = excel_buffer.getvalue()

            st.download_button(
                label="⬇️ Download Excel",
                data=excel_data,
                file_name=f"telemetry_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch'
            )

        with col3:
            # JSON Export
            st.markdown("### 📦 JSON Export")

            json_data = df_to_export.to_json(orient="records", indent=2)

            st.download_button(
                label="⬇️ Download JSON",
                data=json_data,
                file_name=f"telemetry_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                width='stretch'
            )

        st.divider()

        # Export tips
        st.info("""
        **💡 Export Tips:**
        - **CSV**: Best for importing into spreadsheet software or data analysis tools
        - **Excel**: Includes multiple sheets (Runs, Summary, Agent Breakdown) for comprehensive reporting
        - **JSON**: Best for programmatic processing or re-importing into other systems
        - Use the column selector to customize which fields to include
        - Use filters to export only relevant data (e.g., exclude test runs)
        """)

# ============================================================================
# Footer
# ============================================================================

st.divider()
st.caption(f"Telemetry Dashboard | API: {API_BASE_URL} | Streamlit v{st.__version__}")
