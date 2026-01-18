"""Tests for RoutedStdout output capture."""

import sys

from routilux.core import (
    JobContext,
    RoutedStdout,
    clear_job_output,
    get_job_output,
    install_routed_stdout,
    set_current_job,
    uninstall_routed_stdout,
)


class TestRoutedStdout:
    """Test RoutedStdout class."""

    def test_routed_stdout_creation(self):
        """Test creating a RoutedStdout instance."""
        stdout = RoutedStdout()

        assert stdout.real is not None
        assert stdout.keep_default is True

    def test_routed_stdout_write_without_job(self):
        """Test writing to stdout when no job is bound."""
        stdout = RoutedStdout(keep_default=True)
        original_stdout = sys.stdout

        try:
            sys.stdout = stdout
            print("test output", end="")
        finally:
            sys.stdout = original_stdout

        # Should write to real stdout when no job is bound
        # (we can't easily verify this without capturing real stdout)

    def test_routed_stdout_write_with_job(self):
        """Test writing to stdout when a job is bound."""
        stdout = RoutedStdout(keep_default=False)
        job = JobContext(job_id="test-job-123")

        set_current_job(job)
        try:
            stdout.write("test output\n")
        finally:
            set_current_job(None)

        output = stdout.get_buffer("test-job-123")
        assert "test output" in output

    def test_routed_stdout_multiple_jobs(self):
        """Test that output is separated by job ID."""
        stdout = RoutedStdout(keep_default=False)

        job1 = JobContext(job_id="job-1")
        job2 = JobContext(job_id="job-2")

        set_current_job(job1)
        stdout.write("output from job 1\n")
        set_current_job(None)

        set_current_job(job2)
        stdout.write("output from job 2\n")
        set_current_job(None)

        output1 = stdout.get_buffer("job-1")
        output2 = stdout.get_buffer("job-2")

        assert "output from job 1" in output1
        assert "output from job 2" not in output1
        assert "output from job 2" in output2
        assert "output from job 1" not in output2

    def test_routed_stdout_pop_chunks(self):
        """Test getting incremental output chunks."""
        stdout = RoutedStdout(keep_default=False)
        job = JobContext(job_id="test-job")

        set_current_job(job)
        try:
            stdout.write("chunk1\n")
            stdout.write("chunk2\n")
        finally:
            set_current_job(None)

        chunks = stdout.pop_chunks("test-job")

        assert len(chunks) == 2
        assert "chunk1" in chunks[0]
        assert "chunk2" in chunks[1]

        # After pop, chunks should be cleared
        chunks2 = stdout.pop_chunks("test-job")
        assert len(chunks2) == 0


class TestOutputHelpers:
    """Test output helper functions."""

    def test_install_routed_stdout(self):
        """Test installing RoutedStdout."""
        original_stdout = sys.stdout

        try:
            install_routed_stdout()
            assert isinstance(sys.stdout, RoutedStdout)
        finally:
            sys.stdout = original_stdout

    def test_uninstall_routed_stdout(self):
        """Test uninstalling RoutedStdout."""
        original_stdout = sys.stdout

        try:
            # Uninstall any existing routed stdout first
            uninstall_routed_stdout()
            install_routed_stdout()
            assert isinstance(sys.stdout, RoutedStdout)
            uninstall_routed_stdout()
            # After uninstall, should not be RoutedStdout anymore
            assert not isinstance(sys.stdout, RoutedStdout)
            # Should restore to original stdout
            assert sys.stdout is original_stdout
        finally:
            uninstall_routed_stdout()
            sys.stdout = original_stdout

    def test_get_job_output(self):
        """Test getting job output."""
        original_stdout = sys.stdout

        try:
            # Uninstall any existing routed stdout first
            uninstall_routed_stdout()
            install_routed_stdout()
            job = JobContext(job_id="test-job-unique")

            set_current_job(job)
            try:
                print("test output", flush=True)
            finally:
                set_current_job(None)

            # Use incremental=False to get full buffer without clearing
            output = get_job_output("test-job-unique", incremental=False)
            assert "test output" in output
        finally:
            uninstall_routed_stdout()
            sys.stdout = original_stdout

    def test_clear_job_output(self):
        """Test clearing job output."""
        original_stdout = sys.stdout

        try:
            # Uninstall any existing routed stdout first
            uninstall_routed_stdout()
            install_routed_stdout()
            job = JobContext(job_id="test-job-clear")

            set_current_job(job)
            try:
                print("test output", flush=True)
            finally:
                set_current_job(None)

            # Use incremental=False to get full buffer without clearing
            output1 = get_job_output("test-job-clear", incremental=False)
            assert "test output" in output1

            clear_job_output("test-job-clear")

            # After clear, both incremental and buffer should be empty
            output2 = get_job_output("test-job-clear", incremental=False)
            assert output2 == ""
        finally:
            uninstall_routed_stdout()
            sys.stdout = original_stdout
