# Agent Output File Extraction

## Overview

Automatically extracts file contents from agent output logs when the Write tool fails due to permissions or other issues.

## Purpose

During task execution, agents may produce complete file contents in output but fail to write them to disk due to:
- File permission errors
- Directory permission errors
- Path resolution issues
- Sandbox restrictions

This tool recovers those files by parsing agent output logs and extracting file content blocks.

## How It Works

### 1. Agent Output Parsing

The tool scans agent output logs for file content patterns:

```
Writing to scripts/example.py:

​```python
def hello():
    print("Hello!")
​```
```

Supported formats:
- "Writing to [file]:"
- "File: [file]"
- "Creating [file]:"
- Code blocks with file paths

### 2. Content Extraction

For each detected file:
- Extracts file path
- Extracts content from code block
- Determines file type (Python, Markdown, YAML, etc.)
- Assigns confidence score

### 3. Validation

Before writing, validates:
- File extension is valid (.py, .md, .yaml, .sh, .txt, .json)
- Content is non-empty (> 10 characters)
- Confidence score > 0.5

### 4. File Writing

Writes extracted files to target directory:
- Creates parent directories as needed
- Skips existing files (unless --overwrite)
- Supports dry-run mode for preview

## Usage

### Basic Extraction

```bash
python scripts/extract_files_from_agent_output.py \
    --log-file logs/agent_output.log \
    --output-dir .
```

### Dry Run (Preview Only)

```bash
python scripts/extract_files_from_agent_output.py \
    --log-file logs/agent_output.log \
    --output-dir . \
    --dry-run
```

### Overwrite Existing Files

```bash
python scripts/extract_files_from_agent_output.py \
    --log-file logs/agent_output.log \
    --output-dir . \
    --overwrite
```

### Save Extraction Report

```bash
python scripts/extract_files_from_agent_output.py \
    --log-file logs/agent_output.log \
    --output-dir . \
    --report reports/extraction.txt
```

## Post-Agent Hook Integration

Add automatic extraction after agent completion:

### 1. Create Hook Script

Create `.claude/hooks/post_agent.sh`:

```bash
#!/usr/bin/env bash
export AGENT_LOG_FILE="logs/agent_latest.log"
export OUTPUT_DIR="."
source scripts/post_agent_file_extraction.sh
```

### 2. Make Executable

```bash
chmod +x .claude/hooks/post_agent.sh
```

### 3. Configure

The hook runs automatically after each agent completion.

## Extraction Report

Example report:

```
======================================================================
AGENT OUTPUT FILE EXTRACTION REPORT
======================================================================
Log file: logs/agent_ef82d1bf.log
Output directory: .
Mode: WRITE

SUMMARY
----------------------------------------------------------------------
Total files found: 5
Successfully extracted: 4
Failed: 1
Total lines extracted: 1,842

SUCCESSFULLY EXTRACTED FILES
----------------------------------------------------------------------
✓ docs/QUICK_START.md (230 lines)
✓ docs/TROUBLESHOOTING.md (350 lines)
✓ docs/FAQ.md (410 lines)
✓ scripts/monitor.py (850 lines)

FAILED EXTRACTIONS
----------------------------------------------------------------------
✗ config/invalid.exe
  Error: Failed validation (invalid file extension)

======================================================================
```

## Troubleshooting

### No Files Extracted

**Symptom**: Tool reports 0 files found

**Causes**:
1. Agent output format doesn't match expected patterns
2. Agent didn't include file paths with content
3. Log file path incorrect

**Solutions**:
- Check agent output manually for file content blocks
- Verify log file path is correct
- Check that content blocks have file declarations

### Partial Content Extraction

**Symptom**: Files extracted but content incomplete

**Causes**:
1. Log file truncated
2. Code block not properly closed
3. Multi-file blocks confused

**Solutions**:
- Check log file size and completeness
- Verify code blocks have closing ``` markers
- Run with --dry-run to see detected blocks

### Files Already Exist Error

**Symptom**: Extraction fails with "File already exists"

**Solution**: Use `--overwrite` flag to replace existing files

## Exit Codes

- **0**: All files extracted successfully
- **1**: Some files extracted, some failed
- **2**: No files extracted (complete failure)

## Configuration

No configuration file required. All options via CLI arguments.

---

**Last Updated**: 2025-12-11
**Version**: 1.0.0
**Status**: Production Ready
