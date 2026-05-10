"""DEPRECATED — Thread-local stdout redirect approach for benchmark streaming.

This module previously provided _CallbackWriter, _ThreadLocalStdout, and
run_benchmark_with_callback() to stream benchmark output to the LogTab via
a thread-local sys.stdout override.

That approach has been replaced by true subprocess isolation:

    New entry point:  app/workers/benchmark_worker.py
    Runner service:   app/services/subprocess_runner.py (SubprocessRunner)

The subprocess approach eliminates:
  - Thread-local stdout poisoning risks with Flet's event loop
  - Permanent RAM floor increases from pymalloc retaining freed pages
  - The need for manual gc.collect() / sys.modules cleanup after benchmark

All benchmark output now streams via multiprocessing.Queue (ExtractionMessage
with OUTPUT type) from a short-lived child process, and the OS reclaims all
RAM unconditionally when the child exits.

Feature: subprocess-isolation
Requirements: 4.4
See also: console-diagnostics (original feature that introduced this module)
"""

# This module is intentionally empty. It exists only as a deprecation marker
# to document the migration path for anyone referencing the old approach.
#
# Safe to delete entirely once all documentation references are updated.
