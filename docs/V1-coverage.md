# V1: every item of spec §6.8, with the test that proves it

V1 ends (roadmap M15) when every V1 item of §6.8 of the specification, and the First Milestone, is covered by a test or an eval case that runs green in CI.

All the tests below run in the `build-and-test` CI job. The two security tests marked *gate* also run in their own step, and the eval cases run in the eval gate: `python evals/run_evals.py --baseline evals/baseline.json`, 44 cases, no regression allowed.

| # | §6.8 item (V1) | Covered by |
|---|---|---|
| 1 | **HITL end to end:** approval really blocks. | `tests/agent_engine/test_hitl.py`, `tests/agent_engine/test_approval.py`. Eval cases `hitl-approve-email`, `hitl-deny-email`, `hitl-queued-call-after-approval`, `hitl-queued-call-dropped-on-deny`, `home-unlock-typed-waits`, `voice-unlock-approved`. Real browser: `tests/desktop/test_desktop_sidecar.py::test_browser_smoke`, where the HIGH call is allowed from the Nucleo after its events arrive live. |
| 2 | **Guardrails and prompt injection:** external content never drives a HIGH action. | *Gate:* `tests/agent_engine/test_prompt_injection.py` (corpus) and `tests/security/test_boundary_hardening.py`. Also `tests/agent_engine/test_guardrails.py` and `tests/agent_engine/test_tool_selection.py`. Eval cases `security-*`, including documents (`security-document-injection`, `security-document-injection-recalled`, `security-document-injection-unlock`) and voice (`voice-direct-injection`, `voice-high-action-waits`). |
| 3 | **Loopback security:** the local sidecar cannot be reached by other processes or pages. | `tests/desktop/test_desktop_runtime.py`: Host check (DNS rebinding), cross-origin writes, one-time launch token, Postgres on loopback with a password. `tests/desktop/test_desktop_sidecar.py::test_install_to_first_approved_run`: the same against the running sidecar. `tests/security/test_boundary_hardening.py`: WebSocket Origin. |
| 4 | **Minimal RAG.** | `tests/agent_engine/test_context_rag.py`, `tests/agent_engine/test_memory_isolation.py`, `tests/agent_engine/test_documents.py`. Eval cases `memory-*`, `documents-*` (citations checked: an invented one counts as a hallucination). |
| 5 | **Agent budget with enforcement.** | `tests/agent_engine/test_budget.py`, `tests/agent_engine/test_budget_killswitch.py`, `tests/agent_engine/test_engine_limits.py`. Eval cases `budget-run-cap-stops`, `limit-*`. |
| 6 | **Security tests and a gate in CI.** | `.github/workflows/ci.yml`: pip-audit, bandit, ruff, Trivy, TruffleHog, the prompt-injection gate, the eval gate against the baseline, `tests/security/test_api_surface.py` (the exact list of routes). |
| 7 | **Cost and activity dashboard.** | `tests/agent_engine/test_budget_killswitch.py::test_stats_report_inferences_cost_and_failed_tools` (`/api/runs/stats`), `frontend/tests/components.test.tsx` (run view: cost, tokens, calls). Real browser: the Runs page in `test_browser_smoke`. |

**First Milestone:** "install, set up in about ten minutes, give a real command; a dangerous one waits for approval; then see what happened and what it cost."

- **Desktop:** `tests/desktop/test_desktop_sidecar.py::test_install_to_first_approved_run`. From an empty data folder to an approved HIGH call and a completed, priced run. The same flow is driven in a browser by `test_browser_smoke`.
- **Windows installer:** built and smoke-tested in the `desktop-windows` job (`desktop/scripts/smoke_sidecar.py`).
- **Docker:** `tests/agent_engine/test_settings_onboarding.py::test_onboarding_from_empty_database_to_first_completed_run`.

**Added in M15:**

- **Voice.** Local STT/TTS, and a HIGH action asked by voice waits for approval. Tested in `tests/agent_engine/test_voice.py` and by the `voice-*` eval cases.
- **First home node.** MQTT, with the risk set per action. Tested in `tests/agent_engine/test_home.py`, including a real broker in CI.
- **Skill index.** Tested in `tests/agent_engine/test_tool_selection.py` and by `tool-selection-picks-the-light`. It also cut the mean eval cost per case from $0.00888 to $0.00573.
