# SafeBot Product Handbook

**A concise guide to the product, its users, its technical shape, and its limits**

**Source snapshot:** `codex/test-lab-feedback`, October 14, 2026

**Product name:** SafeBot (the GitHub repository is named *AI-Agent-Validator*)
**Estimated reading time:** 30–35 minutes

SafeBot is a small AI-safety control plane and prompt-checking API. A team configures text checks and business rules, sends prompts through SafeBot before its model call, and gets an `allow`, `redact`, or `block` decision with a reason. The app also provides an activity record, a synthetic regression-test workspace, and a way for people to review decisions. It is an early local MVP, not a certified security product or a replacement for the application’s own authorization checks.

## 1. Technical prerequisites

This section gives enough context for a product, design, or engineering reader to follow the rest of the handbook. It is not a full installation manual.

### Concepts to know

| Concept | Plain-language meaning | Why it matters here |
|---|---|---|
| LLM / model | A service that accepts text and produces text or structured output. | SafeBot sits in front of a model call; it does not train or host the model. |
| AI agent | An LLM-driven application that may also read data, call tools, or change external systems. | SafeBot’s intended audience builds tool-using agents, but the current integration screens only prompt text. Tool authorization remains outside SafeBot. |
| Prompt injection | Untrusted text that tries to override the instructions an AI application is meant to follow. | SafeBot’s input checks attempt to detect some injection patterns before a prompt is sent to a model. No detector catches every attack. |
| PII | Personally identifiable information, such as an email address or phone number. | Configured detectors can replace selected values before text continues through the checked flow. Current built-in categories are Aadhaar, PAN, email, Indian phone, and UPI ID. |
| Guardrail | A check or policy placed around an AI interaction to allow, transform, or stop it. | SafeBot combines configurable checks and returns a decision; the calling application must honor it. |
| REST API / JSON | A web endpoint that accepts and returns structured data. | An application sends a JSON prompt to SafeBot over HTTPS and reads the decision. |
| Tenant | A customer-owned data boundary in the app. | Each signup creates one tenant/company record. The current product has no team-member invitations, roles, or shared-workspace administration. |
| JWT and API key | A JWT authenticates a person to the web app; an API key authenticates an integration. | The browser and the agent integration use different credentials and permissions. Keep both secret. |
| Vector similarity | A numerical comparison of text meaning, represented as vectors. | Semantic rules can match text by similarity, but a similarity score is a heuristic, not proof that a rule was logically violated. |

### What is needed to run the local application

- **Python 3.11 or newer** for the FastAPI backend and worker.
- **Node.js and npm** compatible with the frontend’s Vite/React toolchain.
- **Docker Engine/Desktop**, or equivalent local services, for **PostgreSQL 16 with the pgvector extension** and **Redis 7**. PostgreSQL stores tenants, rules, audit records, and Test Lab cases. Redis supports session/rate-limit state, request coordination, and the background-task broker. The API checks Redis during startup.
- **Environment configuration** for database, Redis, and a strong JWT secret. Use the example file as a starting point; never commit real credentials.
- **Cached local ML model weights** for the full local detector path: the prompt-injection classifier and semantic embedding model are loaded from local cache, not downloaded during application startup. Without the weights, some checks report incomplete evaluation rather than silently claiming full coverage. The optional spaCy entity recognizer can fall back to regular-expression PII checks.
- **SMTP credentials** when testing real email verification and password-reset delivery outside development. Development/test mode auto-verifies accounts and exposes development-only reset/verification links. In non-development mode, signup requires email verification; SMTP is therefore part of a usable onboarding flow.
- **Optional Groq API key and explicit configuration** only for the sample protected-chat generation and `llm_eval` rules. The current adapter requires the key, live-enable flag, free-plan confirmation, and an allowlisted model. This is an external provider call, not needed for the core local prompt checks. Do not use real customer content in the demo.
- **Optional Algorand application/wallet configuration and a running Celery worker** for chain anchoring. `ALGORAND_APP_ID=0` leaves anchoring disabled, as in the local demo. Chain anchoring is not required for ordinary guardrail checks.

**Local setup footnote:** the development Compose file publishes PostgreSQL on host port `55432`, while `.env.example` uses `localhost:5432`. Align `DATABASE_URL` with the port actually exposed by the local database before migrating or starting the API.

### System shape

```text
AI application / agent
        │ prompt + tenant API key
        ▼
FastAPI ── authenticate tenant, load current settings/rules
        │
        ├── injection check ── PII redaction ── configured rule checks
        │
        ├── decision: allow / redact / block (or explicit evaluation error)
        ├── sanitized audit evidence → PostgreSQL
        └── optional async task → Redis/Celery → Algorand (if configured)
        │
        ▼
Calling application must decide whether and how to call its model
```

The React/Vite web app is the customer-facing control plane. The FastAPI API owns authentication, tenant isolation, configuration, evaluation, and audit writes. PostgreSQL plus pgvector stores relational data and policy embeddings; Redis backs runtime coordination and queued work; a Celery worker performs optional background tasks. The separate sample “Protected Chat” path performs a pre-check, makes one Groq generation request when explicitly enabled, then checks the generated answer before returning it. It is a demo integration, not a universal SDK interceptor.

## 2. What SafeBot does

SafeBot is intended to make a few important safety controls easier to configure and inspect around an AI application:

1. A developer connects an application with an API key and sends prompt text to SafeBot.
2. SafeBot loads a tenant-specific, versioned snapshot of settings and rules.
3. The evaluation pipeline checks enabled prompt-injection protections, configured PII redaction, and custom rules.
4. SafeBot returns an action and reason. If text was redacted, it can return the transformed text. A block or an evaluation failure may return a fallback response according to the configured failure mode.
5. The caller must use the response correctly: stop on `block`, pass only returned sanitized text on `redact`, and decide how to handle an evaluation error. If an app skips SafeBot or ignores its verdict, SafeBot cannot enforce the decision.
6. The activity view gives a sanitized record of decisions. Teams can inspect, export, and annotate a decision, then create a fictional regression case for later checks.

The ordinary integration’s central contract is **prompt in → safety decision out**. The API does not hold a model session, observe all future actions, or automatically wrap arbitrary agent frameworks.

### Rule and decision behavior

- **Prompt-injection protection:** heuristic patterns plus a locally cached classifier, with strict/moderate/lenient sensitivity. The detector is a best-effort check, not a guarantee.
- **PII redaction:** selected supported categories are replaced with placeholders. It is not a general-purpose global PII detector and does not guarantee complete removal.
- **Custom rules:**
  - `keyword` checks for a configured literal word or phrase.
  - `regex_match` checks a bounded regular expression.
  - `semantic` compares text to an embedding of the rule text.
  - `llm_eval` asks the configured external LLM judge to assess a short rubric; sanitized text/rules leave the local application for that call.
  - `pii_redaction` and `prompt_injection` rules configure those specific checks.
- **Safety settings:** enable/disable checks, sensitivity, global block, failure mode (`closed` or `open`), fallback message, and displayed log-retention setting.
- **Versioning:** behavior-changing settings and rules advance the tenant policy version. Test Lab stores a settings/rules snapshot fingerprint so an old result can be marked stale after behavior changes.

An affirmative injection or configured-rule violation blocks. PII can be redacted. Check failures are surfaced separately as evaluation errors; the default safety posture is fail-closed. A fail-open configuration is a conscious risk decision, not a recommended way to conceal incomplete checks.

### What it does not do today

- It does **not** authorize or reject proposed tool calls, tool arguments, tool results, database queries, or external side effects. A tool-using agent still needs application-level allowlists, argument validation, scoped credentials, and resource-owner authorization.
- The general API examples validate input text; they do not automatically inspect every model response. The sample Protected Chat checks its generated answer, but this behavior is not automatically added to a customer’s application.
- It does not establish that a model is safe, prove policy compliance, or guarantee protection from prompt injection, data leakage, harmful outputs, or hallucinations.
- It does not currently offer team roles/invitations, enterprise SSO, a public hosted service, formal compliance certification, or a measured uptime/latency commitment.
- It provides copyable HTTP examples, not a packaged SDK that automatically wraps a framework or model-provider client.
- An audit hash is supporting evidence for a record; a local database and a hash alone are not an immutable or legally sufficient audit trail. Optional chain anchoring is disabled in the local demo.

## 3. Who it is for and the problems to solve

### Intended customer

The first intended customer is a **small team building a tool-using AI agent**—for example, a product team connecting an LLM to company knowledge, support workflows, or internal actions. The product owner selected this audience; the pain points below are product hypotheses to validate in pilots, not claims from a completed representative user study.

### People involved

| Person | Job to be done | What they need from SafeBot |
|---|---|---|
| Agent developer / technical lead | Add useful controls without rebuilding the app around one model vendor. | A clear API contract, copyable examples, predictable response states, and test cases before changing behavior. |
| Security / privacy owner | Reduce avoidable exposure of sensitive text and understand which requests were blocked or transformed. | Understandable rules, conservative failure behavior, minimized audit evidence, and a reviewable history. |
| Product / operations reviewer | Decide whether a guardrail acted correctly and identify repeated false positives or misses. | A human review action, concise decision context, and a way to turn a synthetic example into a regression check. |
| Business owner / founder | Demonstrate that the team has a repeatable safety workflow without hiring a dedicated platform group. | A small surface area, explicit states, quick integration, and no claim that the product replaces security engineering. |

These are roles in the customer’s team, **not product roles supported by the app**. Today, one account/tenant has one company name, email, API key, and configuration boundary.

### Core pain-point hypotheses

1. **Safety controls are scattered across prompts, providers, and custom code.** A developer may have content filters in one SDK, regexes in an API, and special cases in a prompt. A small, explicit check boundary can make the decision easier to see and change. It cannot unify controls the application never sends through it.
2. **Sensitive text can reach a model provider unnecessarily.** An input may include identifiers that are not needed to answer the request. Redaction can reduce that exposure for supported patterns, while the developer still has to decide what data to retain and whether a transformed prompt remains useful.
3. **A written policy is hard to know how to enforce.** A short rubric or rule gives teams a place to encode intent. Keyword/regex checks are exact but brittle; semantic checks are approximate; LLM judges are slower and external. Each needs examples and review.
4. **A verdict without context is difficult to trust.** Developers need to know whether a request was allowed, redacted, blocked, or could not be checked. Sanitized history and reason fields make investigation easier without intentionally storing full raw prompts.
5. **A policy change can fix one case and break another.** Reusable synthetic examples let a team check expected `allow`, `redact`, or `block` outcomes against current settings before release. Feedback links operational decisions back to cases, but it does not automatically change policy.
6. **Guardrail mistakes have two costs.** Missed attacks can expose data or trigger unintended behavior; false positives frustrate legitimate users and can break a workflow. SafeBot should make both errors visible and measurable, not imply that every block is correct.

The product’s best initial value proposition is therefore **a visible, testable prompt-decision workflow**: connect a prompt boundary, configure rules, inspect what happened, and retest known cases. Whether this is valuable enough compared with a framework library or provider-native controls is a pilot question.

## 4. Main user journeys and features

| Journey / feature | What happens | User problem addressed and expected result |
|---|---|---|
| **Landing and account creation** | A visitor reads the value proposition, signs up with company name/email/password, verifies email outside development, then signs in. Login, logout, refresh, forgot-password, reset-password, and resend-verification routes exist. | Lets a team create its own isolated configuration. In development/test, email verification is auto-completed and links are exposed for local use; a real non-development flow needs working SMTP. There is no invite/member-management journey. |
| **Home dashboard** | Shows a last-seven-day summary of request outcomes and average latency, with daily trend. | Gives an operator a quick “is the integration being used and what is happening?” view. Metrics are derived from audit activity; an empty graph means no recorded traffic, not that the agent is safe. |
| **Protection Rules** | Create, view, edit, enable/disable, and delete tenant rules; configure safety behavior and thresholds. | Gives developers and reviewers a place to express policy rather than editing each caller independently. Rule design and detector accuracy still require representative test cases. |
| **Connect Your AI** | Displays the API-key prefix and copyable cURL, Python, and JavaScript examples. The full key is returned at signup or rotation and should be stored securely by the customer. | Shortens integration setup. The app should call SafeBot server-side, not expose its key in browser/client code. The integration must honor the returned action and sanitized text. |
| **Prompt validation API** | The `POST /api/v1/validate` example accepts a prompt and optional caller user ID; API-key authentication selects the tenant. The decision contains action, reason, evaluation state, and redacted text when applicable. `/hooks/check` and `/hooks/sanitize` are additional checked/audited endpoints. | Adds a visible prompt gate before a model call and records a decision. `/validate` audit insertion runs as a best-effort background task; `/check` and `/sanitize` write their audit row in the request. It is not a sidecar that can prevent an unintegrated or non-compliant caller from bypassing the check. |
| **Protected Chat sample** | A user enters a synthetic prompt. When the provider gates are satisfied, SafeBot checks the input, makes one Groq generation request with accepted/sanitized text, checks the answer, and returns a result or explicit error. Pre/post activity records are linked to a conversation. | Demonstrates how a pre-check and post-check can surround one model call. This is a sample route using Groq, not an agent runtime, and it has no tool execution. |
| **Activity History / audit** | Browse tenant audit records, search and filter by outcome/date/review status, inspect detail, and export up to 10,000 filtered rows as CSV. The preview is bounded and sanitized; records include processing time, policy version, violations/evaluation state, and a hash when available. | Helps investigate “what happened?” without deliberately retaining full raw prompt text. A sanitized preview can still contain sensitive context not recognized by detectors; treat exports as sensitive. |
| **Decision Feedback** | Attach one human review to an audit decision: Correct, Incorrect (with expected action), or Unsure; add a short note and mark it Open or Resolved. A reviewer can start a follow-up Test Lab case with a blank prompt and enter a complete synthetic scenario. | Captures human judgment and makes disagreement actionable. It does not alter the original audit event or change active rules automatically. The reviewer must manually create a fictional case; audit previews are not copied into it. |
| **Test Lab** | Save up to 20 manually authored synthetic cases per tenant (up to 4,000 characters each), acknowledge that content is synthetic, select expected action, run against a frozen settings/rules snapshot, compare actual vs expected, and inspect results. Recognized credential patterns are rejected. Editing a case or changing policy makes a prior result stale. | Gives teams a lightweight regression check for known scenarios. It does not send prompts to an LLM, create audit/usage rows, generate attack cases, or prove security. If an enabled `llm_eval` rule needs an external judge, the case is reported unavailable rather than calling a provider. |
| **Account and settings** | Update company name/email, change password, configure safety posture and displayed retention period, and rotate the API key. Rotating invalidates the prior integration key; the new full key is displayed once. | Supports account maintenance and credential rotation. Updating email requires re-verification; keep the replacement key in a secret manager before rotation. |
| **Optional audit anchoring** | A configured worker can submit eligible audit hashes or policy hashes to Algorand and attach transaction IDs. | Offers an external timestamp/anchor for selected evidence. It is optional and disabled in the local demo; it does not publish full prompts and must not be described as “compliance-grade” without a legal/operational review. |

### Important states users should understand

- **Allowed:** the enabled checks completed without a block/redaction finding. This is not a guarantee that the prompt or agent behavior is safe.
- **Redacted:** supported sensitive values were replaced; the caller should send the returned transformed text, not the original.
- **Blocked:** an enabled control found an affirmative reason to stop. The caller should not send the original prompt onward.
- **Evaluation failed / unavailable:** at least one required evaluation did not complete. Show the error separately from a successful “allowed” state and follow the configured fail mode. Test Lab’s “unavailable” state specifically means it could not produce a trustworthy comparison.
- **Stale:** the saved Test Lab result was produced using an older case or rule/settings snapshot; rerun before relying on it.
- **Feedback open/resolved:** a human review is a work item. Resolution records that it was handled, not that a rule was automatically fixed.

## 5. Competitors and differentiation

This is a category map, not a claim that these products are identical or that a formal feature-by-feature procurement study has been completed. Official product documentation changes; descriptions below reflect the linked pages checked for this handbook.

| Product / category | What it overlaps on | How SafeBot is different today—and where it is behind |
|---|---|---|
| [Check Point AI Guardrails (Lakera documentation)](https://docs.lakera.ai/docs/api) | Managed runtime screening for text and agent interactions, including tool responses/definitions, data leakage, and policy decisions. | SafeBot’s local MVP offers its own basic rules, dashboard, audit review, and synthetic prompt regression loop. Lakera’s documented API covers broader agent/tool surfaces and a managed detector product; SafeBot does not currently authorize tool calls or have comparable threat coverage. |
| [Microsoft Azure AI Content Safety Prompt Shields](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection) | Managed detection for user-prompt and document prompt attacks, integrated with Microsoft’s AI platform. | SafeBot has a small provider-independent HTTP boundary and UI for rules/history. Azure has native platform integration and managed controls; SafeBot does not yet have comparable provider integration, model coverage, or operational maturity. |
| [NVIDIA NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/resources/runtime-security-faq) | Open-source, configurable runtime rails around an LLM application. | SafeBot emphasizes a small web control plane, tenant-specific rules, audit review, and feedback-to-regression flow. NeMo’s documented rail types span inputs, retrieval, dialog, execution, tools, and outputs; SafeBot’s general integration is much narrower. |
| [Guardrails AI](https://github.com/guardrails-ai/guardrails) | Developer library for input/output validators and custom checks around LLM calls. | SafeBot packages configuration and decision history in a web app/API rather than requiring only a library integration. Guardrails AI is a composable developer toolkit; SafeBot currently has fewer extension points and a smaller validator ecosystem. |
| [Promptfoo](https://www.promptfoo.dev/docs/faq/) | Evaluation and security testing; Promptfoo can run repeatable evaluations and adversarial red-team tests against applications and agent targets. | SafeBot’s Test Lab is intentionally small and operational: saved expected actions against SafeBot’s current rules plus human feedback on actual audit decisions. Promptfoo is broader for generated attacks, target/provider comparison, CI, and red teaming. SafeBot is not a replacement for it. |

### A credible differentiation statement

The defensible statement is currently a **product hypothesis**, not a moat: “SafeBot brings a simple prompt-check API, editable safety rules, understandable decision history, human review, and small regression cases into one approachable workflow for a team that does not want to assemble those pieces first.”

To make this real, SafeBot would need to prove it is easier to integrate, that its checks are useful at an acceptable latency/false-positive rate, and that the review-to-test loop changes team behavior. It should not claim superior detection, agent-wide protection, compliance certification, or uptime until those have been independently measured and supported.

## 6. Architecture map and code pointers

| Area | What lives there |
|---|---|
| [Backend entry point](../backend/app/main.py) | FastAPI setup, middleware, startup/readiness checks, and router registration. |
| [API routes](../backend/app/api/v1/) | Auth, dashboard, demo, prompt hooks, rules, audit history, health, and Test Lab/feedback endpoints. |
| [Guardrail services](../backend/app/services/guardrails/) | Evaluation pipeline, detector, PII handling, policy engine, provider adapter, audit sanitization, and protected-chat orchestration. |
| [Models and schemas](../backend/app/models/) · [schemas](../backend/app/schemas/) | SQLAlchemy records and request/response validation. Tenant IDs scope customer data. |
| [Migrations](../backend/alembic/) | PostgreSQL schema evolution, including policies, audit evidence, and Test Lab/feedback. |
| [Frontend routes](../frontend/src/App.tsx) | Public auth routes and protected application pages. |
| [Frontend pages](../frontend/src/pages/) | Home, history, Test Lab, Protection Rules, integration, account, and settings. |
| [Frontend services](../frontend/src/services/) | Typed API calls and authentication/session handling. |
| [Development Compose](../docker-compose.dev.yml) · [production Compose](../docker-compose.prod.yml) | Local PostgreSQL/Redis services and a production-shaped container configuration. The latter is configuration, not proof of a currently deployed service. |
| [Test Lab notes](test-lab-feedback.md) | Current limits, safety expectations, result semantics, and feedback behavior. |

## 7. Risks, open questions, and next useful work

1. **Match audience, name, and positioning to capability.** The README describes middleware for SMBs, while the owner-selected first audience is teams building tool-using agents. Current enforcement is prompt-text checking. Decide whether the first product is explicitly a prompt-safety gateway or whether tool-call policy enforcement is necessary before using “agent protection” broadly.
2. **Prove detector quality.** Build a representative, synthetic evaluation set and measure both missed attacks and false positives by detector/rule type. A handful of demo prompts is not an accuracy benchmark.
3. **Test the integration contract.** Document exactly what callers must do for `allow`, `redact`, `block`, timeout, and evaluator failure. Add tested examples for safe use in Python/Node and keep API keys server-side.
4. **Protect sensitive data end to end.** Audit previews are minimized and sanitized, but databases, backups, exports, logs, and optional external judging still need explicit access, retention, deletion, and provider-data policies. Do not paste actual customer data into Test Lab; it accepts only acknowledged synthetic examples.
5. **Validate actual signup and email flows.** Production-like signup depends on SMTP delivery. Development auto-verification is a convenience and is not proof of the deployed email flow.
6. **Verify retention scheduling before promising deletion.** A retention setting and purge task exist, and the worker code configures a daily Celery Beat schedule. The supplied production Compose file starts a Celery worker but no separate Beat scheduler; verify that Beat runs in the actual deployment before telling users that old records are purged automatically.
7. **Avoid unsupported or overbroad marketing claims.** The landing page currently displays `<100ms` average latency and a `99.9%` uptime SLA without benchmark/SLO evidence in this repository. It also describes PII redaction for requests and responses, but response checking is only in the Protected Chat sample, not the general validation API. Scope or substantiate these statements before real-user release.
8. **State the deployment posture plainly.** A production-shaped Compose file and deployment guide are not the same as a hardened, monitored, backed-up production service. Hosting, incident handling, restore testing, capacity, privacy/legal review, and operational ownership remain separate work.

### Glossary

- **Audit record:** a tenant-scoped account of a checked request, with a bounded sanitized preview and decision metadata.
- **Expected action:** the human-selected `allow`, `redact`, or `block` outcome for a Test Lab case.
- **False positive:** safe/useful text is incorrectly redacted or blocked.
- **False negative:** unsafe text is incorrectly allowed through a check.
- **Fail-closed:** if an enabled safety evaluation is incomplete, stop rather than assume the prompt is safe.
- **Policy snapshot:** the frozen safety settings and enabled rules used to evaluate a request or Test Lab run.
- **Synthetic data:** fictional test content that does not contain real customers, credentials, or personal records.

## Sources and reading

**Repository sources:** `README.md`, `backend/app/main.py`, `backend/app/services/guardrails/`, `backend/app/api/v1/`, `backend/app/models/`, `frontend/src/`, `docker-compose.dev.yml`, `docker-compose.prod.yml`, `.env.example`, and `docs/test-lab-feedback.md` in this source snapshot.

**Competitor primary sources:** [Check Point AI Guardrails API](https://docs.lakera.ai/docs/api), [Microsoft Prompt Shields](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection), [NVIDIA NeMo Guardrails runtime security FAQ](https://docs.nvidia.com/nemo/guardrails/resources/runtime-security-faq), [Guardrails AI repository](https://github.com/guardrails-ai/guardrails), and [Promptfoo FAQ](https://www.promptfoo.dev/docs/faq/) / [red-team quickstart](https://www.promptfoo.dev/docs/red-team/quickstart/).

This handbook is an orientation document, not a security assessment, deployment approval, or guarantee that every feature has been independently tested in every environment.
