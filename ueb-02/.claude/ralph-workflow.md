# Ralph Loop Workflow — ueb-02 GPU benchmark roadmap

Execute the roadmap in `docs/superpowers/plans/2026-06-30-gpu-simt-bandwidth.md`,
**one plan-task per iteration**, until all 11 tasks are complete.

## Orient (every iteration)
1. Read the plan file's checkboxes and run `git log --oneline -15`.
2. Identify the lowest-numbered Task (1..11) that is NOT yet fully `- [x]`.
3. Work on exactly that ONE task this iteration.

## Environment facts (this VM)
- Only a **POCL CPU** OpenCL device exists (no GPU passthrough; the device name
  string says "890M" but it is the CPU device). Confirmed working: kernels compile,
  run, and profile.
- Use `./.venv/bin/python` (has pyopencl, numpy, matplotlib, pytest).
- `latexmk`, `pdflatex`, `biber` are installed — the PDF CAN be built here.
- All OpenCL tests/benchmarks must target the **CPU** device
  (`--device cpu` / `PYOPENCL_CTX`). Code stays device-agnostic.
- Task 10's `--device gpu` sweep CANNOT run here. Instead generate **CPU-device**
  result JSON so the full pipeline (plots, report) is proven end-to-end, and leave
  the GPU run as a documented command for the user to run on the host.

## Per-task workflow
1. **(writing-plans)** Briefly refine the task's steps only if needed; else proceed.
2. **Implement with parallel subagents** — dispatch implementation and
   test-writing concurrently for independent files (TDD where the plan specifies:
   failing test first, then implementation).
3. **In parallel**: run `./.venv/bin/python -m pytest -q` AND a clean code review
   (`/code-review`) on the working diff.
4. **If tests fail or the review finds real issues**: refactor, then repeat 2-4
   until tests are green and no real issues remain.
5. **Eliminate AI slop and em-dashes**: no `—`/`–` in code, comments, labels, or
   report prose; use plain ASCII hyphens and direct wording. Remove filler comments
   and over-explanation.
6. **Close out**: tick the task's checkboxes to `- [x]` in the plan file, commit
   with a clear message, update the harness task to completed.

## Completion
When all 11 tasks are `- [x]`, the test suite passes on the CPU device, CPU-device
result JSON + figures exist, and the report builds (or its GPU-data dependency is
documented), output exactly:

    <promise>ROADMAP COMPLETE</promise>
