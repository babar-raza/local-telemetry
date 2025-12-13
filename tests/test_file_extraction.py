"""
Tests for agent output file extraction.

Tests automated extraction of file contents from agent output logs.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from extract_files_from_agent_output import (
    extract_file_blocks,
    validate_file_block,
    write_extracted_files,
    FileBlock,
    ExtractionResult
)


@pytest.fixture
def temp_project():
    """Create temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_agent_output():
    """Create sample agent output with file content blocks."""
    return """
Agent output log:

Writing to scripts/example.py:

```python
def hello():
    print("Hello, world!")

if __name__ == "__main__":
    hello()
```

Creating docs/README.md:

```markdown
# README

This is documentation.
```

File `config/settings.yaml` created:

```yaml
server:
  port: 8080
  host: localhost
```
"""


class TestFileBlockExtraction:
    """Tests for file block extraction from agent output."""

    def test_extract_python_file(self, sample_agent_output):
        """Test extraction of Python file."""
        blocks = extract_file_blocks(sample_agent_output)

        python_blocks = [b for b in blocks if b.filepath.endswith('.py')]
        assert len(python_blocks) >= 1

        py_block = python_blocks[0]
        assert 'def hello' in py_block.content
        assert py_block.block_type == 'python'

    def test_extract_markdown_file(self, sample_agent_output):
        """Test extraction of markdown file."""
        blocks = extract_file_blocks(sample_agent_output)

        md_blocks = [b for b in blocks if b.filepath.endswith('.md')]
        assert len(md_blocks) >= 1

        md_block = md_blocks[0]
        assert '# README' in md_block.content

    def test_extract_yaml_file(self, sample_agent_output):
        """Test extraction of YAML file."""
        blocks = extract_file_blocks(sample_agent_output)

        yaml_blocks = [b for b in blocks if b.filepath.endswith('.yaml')]
        assert len(yaml_blocks) >= 1

        yaml_block = yaml_blocks[0]
        assert 'server:' in yaml_block.content

    def test_extract_multiple_files(self, sample_agent_output):
        """Test extraction of multiple files."""
        blocks = extract_file_blocks(sample_agent_output)

        assert len(blocks) >= 3
        filepaths = [b.filepath for b in blocks]
        assert 'scripts/example.py' in filepaths
        assert 'docs/README.md' in filepaths
        assert 'config/settings.yaml' in filepaths

    def test_extract_no_files(self):
        """Test extraction when no files present."""
        output = "Agent output with no file blocks."
        blocks = extract_file_blocks(output)

        assert len(blocks) == 0

    def test_confidence_scores(self, sample_agent_output):
        """Test that extracted blocks have confidence scores."""
        blocks = extract_file_blocks(sample_agent_output)

        for block in blocks:
            assert 0.0 <= block.confidence <= 1.0
            assert block.confidence >= 0.5  # Minimum threshold

    def test_line_numbers_tracked(self, sample_agent_output):
        """Test that line numbers are tracked."""
        blocks = extract_file_blocks(sample_agent_output)

        for block in blocks:
            assert block.line_number > 0


class TestFileBlockValidation:
    """Tests for file block validation."""

    def test_validate_valid_block(self):
        """Test validation of valid block."""
        block = FileBlock(
            filepath='test.py',
            content='def test(): pass\n',
            line_number=10,
            block_type='python',
            confidence=0.9
        )

        assert validate_file_block(block) is True

    def test_reject_empty_content(self):
        """Test rejection of empty content."""
        block = FileBlock(
            filepath='test.py',
            content='',
            line_number=10,
            block_type='python',
            confidence=0.9
        )

        assert validate_file_block(block) is False

    def test_reject_low_confidence(self):
        """Test rejection of low confidence blocks."""
        block = FileBlock(
            filepath='test.py',
            content='def test(): pass',
            line_number=10,
            block_type='python',
            confidence=0.3  # Too low
        )

        assert validate_file_block(block) is False

    def test_reject_invalid_extension(self):
        """Test rejection of invalid file extensions."""
        block = FileBlock(
            filepath='test.exe',  # Invalid extension
            content='binary content',
            line_number=10,
            block_type='unknown',
            confidence=0.9
        )

        assert validate_file_block(block) is False

    def test_reject_short_content(self):
        """Test rejection of too-short content."""
        block = FileBlock(
            filepath='test.py',
            content='x',  # Too short
            line_number=10,
            block_type='python',
            confidence=0.9
        )

        assert validate_file_block(block) is False


class TestFileWriting:
    """Tests for writing extracted files."""

    def test_write_files_success(self, temp_project):
        """Test successful file writing."""
        blocks = [
            FileBlock('test.py', 'print("hello")\n' * 10, 1, 'python', 0.9)
        ]

        results = write_extracted_files(blocks, temp_project, dry_run=False)

        assert len(results) == 1
        assert results[0].success is True
        assert (temp_project / 'test.py').exists()

    def test_dry_run_no_write(self, temp_project):
        """Test dry run doesn't write files."""
        blocks = [
            FileBlock('test.py', 'print("hello")\n' * 10, 1, 'python', 0.9)
        ]

        results = write_extracted_files(blocks, temp_project, dry_run=True)

        assert len(results) == 1
        assert results[0].success is True
        assert not (temp_project / 'test.py').exists()

    def test_no_overwrite_existing(self, temp_project):
        """Test that existing files aren't overwritten without flag."""
        # Create existing file
        test_file = temp_project / 'test.py'
        test_file.write_text('existing content')

        blocks = [
            FileBlock('test.py', 'new content', 1, 'python', 0.9)
        ]

        results = write_extracted_files(blocks, temp_project, dry_run=False, overwrite=False)

        assert results[0].success is False
        assert 'already exists' in results[0].error.lower()
        # Original content preserved
        assert test_file.read_text() == 'existing content'

    def test_overwrite_existing(self, temp_project):
        """Test overwriting existing files with flag."""
        # Create existing file
        test_file = temp_project / 'test.py'
        test_file.write_text('existing content')

        blocks = [
            FileBlock('test.py', 'new content', 1, 'python', 0.9)
        ]

        results = write_extracted_files(blocks, temp_project, dry_run=False, overwrite=True)

        assert results[0].success is True
        assert test_file.read_text() == 'new content'

    def test_create_nested_directories(self, temp_project):
        """Test creation of nested directory structures."""
        blocks = [
            FileBlock('src/lib/module.py', 'code', 1, 'python', 0.9)
        ]

        results = write_extracted_files(blocks, temp_project, dry_run=False)

        assert results[0].success is True
        assert (temp_project / 'src' / 'lib' / 'module.py').exists()

    def test_line_count_tracking(self, temp_project):
        """Test that line counts are tracked correctly."""
        content = '\n'.join([f'line{i}' for i in range(50)])
        blocks = [
            FileBlock('test.py', content, 1, 'python', 0.9)
        ]

        results = write_extracted_files(blocks, temp_project, dry_run=False)

        assert results[0].lines_written == 50


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
