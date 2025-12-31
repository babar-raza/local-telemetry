# Dashboard Smoke Test Checklist

## Prerequisites
- [ ] API service running: `python telemetry_service.py`
- [ ] Health check passes: `curl http://localhost:8765/health`

## Test Execution (5 minutes)

### Tab 1: Browse Runs
- [ ] Loads without errors
- [ ] Displays at least 10 records
- [ ] Agent name filter works
- [ ] Status filter works
- [ ] Pagination controls visible
- [ ] Can select a run for editing

### Tab 2: Edit Single Run
- [ ] Can paste/enter event_id
- [ ] "Fetch Current Values" populates form
- [ ] All 11 editable fields display current values
- [ ] Can modify status dropdown
- [ ] Validation prevents negative counts

### Tab 3: Bulk Edit
- [ ] Shows warning if no data loaded
- [ ] After loading data in Tab 1, can select runs
- [ ] Preview table shows old → new values
- [ ] Progress bar displays during execution

### Tab 4: Analytics
- [ ] All 5 charts render without errors
- [ ] Filters work (agent, exclude test)
- [ ] Summary statistics display

### Tab 5: Export
- [ ] CSV download button works
- [ ] Excel download button works
- [ ] JSON download button works
- [ ] Preview shows correct row count

## Pass Criteria
- [ ] All tabs load without Python exceptions
- [ ] Can complete one full edit workflow (Browse → Edit → Update)
- [ ] Charts render with production data
- [ ] At least one export format downloads successfully
