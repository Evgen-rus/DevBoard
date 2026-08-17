---
name: devboard-task
description: Fetch a DevBoard task by DEV-ID from its remote URL, materialize current task context and image attachments, verify the target repository, and run an analysis-first coding handoff. Use when a prompt invokes $devboard-task or asks Codex to take a DEV-N task from DevBoard in any local project.
---

# DevBoard task handoff

Keep the current repository as the working project. Use DevBoard only as the task and attachment source.

1. Extract the `DEV-N` ID and DevBoard base URL from the prompt. If either is missing, ask only for the missing value.
2. Locate the DevBoard CLI. Prefer `DEVBOARD_CLI`; otherwise use `D:\My_dev_project\DevBoard\cli\devtask.py`. Do not change the current working directory.
3. Run:

   ```powershell
   python <cli-path> get <DEV-N> --url <devboard-url> --materialize --skip-audio
   ```

   The CLI reads `~/.devboard/client.env` and writes to the user cache. Never print the token or load it into chat.
4. If network or filesystem permission is denied, request the standard approval for the exact fetch operation. Do not bypass authentication.
5. Read the emitted `task.json`. Treat it as a working snapshot; the GitHub Issue referenced by it remains the task source of truth.
6. Inspect every downloaded attachment with `kind=image` using the available image viewer. Read other downloaded files only when relevant. Prefer the stored transcript over downloading audio; fetch audio separately only when a material ambiguity cannot be resolved from the transcript and the user authorizes it.
7. If task context or a potentially decision-relevant image is unavailable, stop and report the exact missing item. Do not infer its content.
8. Verify that the current repository corresponds to the task `project`. If it clearly does not, stop and ask the user to reopen the task in the correct project.
9. Follow the current repository's `AGENTS.md`. Read its required architecture/source-of-truth files, related code and tests, and inspect `git status` without changing files.
10. Report: understanding, existing behavior, real gaps, ambiguities/questions, and an implementation/verification plan. Make no changes until the user gives explicit implementation approval in the current task.
11. After approval, implement the minimum scoped change, preserve unrelated worktree changes, run the repository-required checks, and reference the DEV-ID in the handoff. Do not make paid, production, deployment, CRM-write, push, commit, or PR actions without the authority required by the current repository and user request.
