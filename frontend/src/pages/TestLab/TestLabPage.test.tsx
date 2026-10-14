import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import TestLabPage from "./TestLabPage"
import {
  createTestCase,
  fetchTestCases,
  runTestCases,
} from "../../services/testLabService"
import type { TestCase, TestResult, TestRunResponse } from "../../types/api"

vi.mock("../../services/testLabService", () => ({
  createTestCase: vi.fn(),
  deleteTestCase: vi.fn(),
  fetchTestCases: vi.fn(),
  runTestCases: vi.fn(),
  updateTestCase: vi.fn(),
}))

afterEach(cleanup)

const now = "2026-10-14T10:00:00Z"
const savedCase: TestCase = {
  id: "case-1",
  name: "Fictional greeting",
  prompt: "Greet fictional user Riley.",
  expected_action: "allow",
  synthetic_data_acknowledged: true,
  revision: 1,
  source_feedback_id: null,
  last_result: null,
  last_run_at: null,
  created_at: now,
  updated_at: now,
}

function renderTestLab(initialEntry: string | { pathname: string; state: unknown } = "/test-lab") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <TestLabPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(fetchTestCases).mockReset().mockResolvedValue([])
  vi.mocked(createTestCase).mockReset().mockResolvedValue(savedCase)
  vi.mocked(runTestCases).mockReset()
})

describe("TestLabPage", () => {
  it("requires synthetic-data acknowledgement before saving a manually written test", async () => {
    const user = userEvent.setup()
    renderTestLab()

    await user.click(await screen.findByRole("button", { name: "Create a test" }))
    await user.type(screen.getByLabelText("Test name"), "Fictional contact test")
    await user.type(screen.getByLabelText("Synthetic test prompt"), "A fictional user asks to update a made-up account.")
    const save = screen.getByRole("button", { name: "Save test" })
    expect(save).toBeDisabled()
    await user.click(screen.getByLabelText(/I confirm this prompt contains synthetic data/i))
    await user.click(save)

    await waitFor(() => expect(createTestCase).toHaveBeenCalledWith({
      name: "Fictional contact test",
      prompt: "A fictional user asks to update a made-up account.",
      expected_action: "allow",
      synthetic_data_acknowledged: true,
    }, undefined))
  })

  it("starts review conversion with a blank prompt and requires manual synthetic entry", async () => {
    const user = userEvent.setup()
    renderTestLab({
      pathname: "/test-lab",
      state: {
        draft: {
          sourceFeedbackId: "feedback-1",
          name: "Follow-up scenario",
          expectedAction: "block",
        },
      },
    })

    const prompt = await screen.findByLabelText("Synthetic test prompt") as HTMLTextAreaElement
    expect(prompt).toHaveValue("")
    expect(screen.getByText(/Activity History stores short excerpts/i)).toBeInTheDocument()
    expect(screen.getByLabelText("Test name")).toHaveFocus()
    expect(screen.getByRole("button", { name: "Save test" })).toBeDisabled()

    await user.type(prompt, "A fresh fictional scenario written by the reviewer.")
    await user.click(screen.getByLabelText(/I confirm this prompt contains synthetic data/i))
    await user.click(screen.getByRole("button", { name: "Save test" }))
    await waitFor(() => expect(createTestCase).toHaveBeenCalledWith({
      name: "Follow-up scenario",
      prompt: "A fresh fictional scenario written by the reviewer.",
      expected_action: "block",
      synthetic_data_acknowledged: true,
    }, "feedback-1"))
  })

  it("requires a chosen outcome when converting an ERROR review without an expected action", async () => {
    renderTestLab({
      pathname: "/test-lab",
      state: { draft: { sourceFeedbackId: "feedback-error", name: "Follow-up" } },
    })

    expect(await screen.findByLabelText("Expected guardrail outcome")).toHaveValue("")
    expect(screen.getByRole("button", { name: "Save test" })).toBeDisabled()
    expect(screen.getByLabelText("Synthetic test prompt")).toHaveValue("")
  })

  it("keeps the editor open with the draft after a save failure", async () => {
    const user = userEvent.setup()
    vi.mocked(createTestCase).mockRejectedValue(new Error("network unavailable"))
    renderTestLab()

    await user.click(await screen.findByRole("button", { name: "Create a test" }))
    await user.type(screen.getByLabelText("Test name"), "Retry me")
    const promptText = "Made-up details only for this scenario."
    await user.type(screen.getByLabelText("Synthetic test prompt"), promptText)
    await user.click(screen.getByLabelText(/I confirm this prompt contains synthetic data/i))
    await user.click(screen.getByRole("button", { name: "Save test" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save this test case.")
    expect(screen.getByLabelText("Test name")).toHaveValue("Retry me")
    expect(screen.getByLabelText("Synthetic test prompt")).toHaveValue(promptText)
  })

  it("ignores a late create response after the editor closes", async () => {
    const user = userEvent.setup()
    let resolveCreate: ((value: TestCase) => void) | undefined
    vi.mocked(createTestCase).mockReturnValueOnce(new Promise((resolve) => { resolveCreate = resolve }))
    renderTestLab()

    await user.click(await screen.findByRole("button", { name: "Create a test" }))
    await user.type(screen.getByLabelText("Test name"), "Close while saving")
    await user.type(screen.getByLabelText("Synthetic test prompt"), "A fictional test prompt.")
    await user.click(screen.getByLabelText(/I confirm this prompt contains synthetic data/i))
    await user.click(screen.getByRole("button", { name: "Save test" }))
    await user.click(screen.getByRole("button", { name: "Close" }))
    resolveCreate?.(savedCase)

    await waitFor(() => expect(screen.queryByTestId("test-case-editor")).not.toBeInTheDocument())
    expect(screen.queryByLabelText("Synthetic test prompt")).not.toBeInTheDocument()
  })

  it("disables case edits while saving but keeps close available", async () => {
    const user = userEvent.setup()
    let resolveCreate: ((value: TestCase) => void) | undefined
    vi.mocked(createTestCase).mockReturnValueOnce(new Promise((resolve) => { resolveCreate = resolve }))
    renderTestLab()

    await user.click(await screen.findByRole("button", { name: "Create a test" }))
    await user.type(screen.getByLabelText("Test name"), "Pending save")
    await user.type(screen.getByLabelText("Synthetic test prompt"), "A fully made-up scenario.")
    await user.click(screen.getByLabelText(/I confirm this prompt contains synthetic data/i))
    await user.click(screen.getByRole("button", { name: "Save test" }))

    expect(screen.getByLabelText("Test name")).toBeDisabled()
    expect(screen.getByLabelText("Synthetic test prompt")).toBeDisabled()
    expect(screen.getByLabelText("Expected guardrail outcome")).toBeDisabled()
    expect(screen.getByLabelText(/I confirm this prompt contains synthetic data/i)).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "Close" }))
    resolveCreate?.(savedCase)
    await waitFor(() => expect(screen.queryByTestId("test-case-editor")).not.toBeInTheDocument())
  })

  it("shows external-judge unavailability without implying a provider call", async () => {
    const user = userEvent.setup()
    const result = {
      case_id: savedCase.id,
      case_revision: 1,
      status: "unavailable" as const,
      expected_action: "allow" as const,
      observed_action: null,
      failure_codes: ["external_judge_required"],
      preview: null,
      redaction_counts: {},
      snapshot_hash: null,
      completed_at: now,
    }
    const runResponse: TestRunResponse = {
      results: [result], passed: 0, mismatched: 0, unavailable: 1, not_run: 0, revision_conflicts: 0,
    }
    vi.mocked(fetchTestCases)
      .mockResolvedValueOnce([savedCase])
      .mockResolvedValueOnce([{ ...savedCase, last_result: result, last_run_at: now }])
    vi.mocked(runTestCases).mockResolvedValue(runResponse)
    renderTestLab()

    await user.click(await screen.findByRole("button", { name: "Run Fictional greeting" }))
    expect(await screen.findByText(/This policy needs an external judge/i)).toBeInTheDocument()
    expect(screen.getByText(/Test Lab does not contact providers/i)).toBeInTheDocument()
    expect(screen.getByText("Unavailable")).toBeInTheDocument()
    expect(runTestCases).toHaveBeenCalledWith([savedCase.id])
  })

  it("keeps a newer refreshed case revision when an older run response arrives late", async () => {
    const user = userEvent.setup()
    const staleResult: TestResult = {
      case_revision: 1,
      status: "stale",
      expected_action: "allow",
      observed_action: "allow",
      failure_codes: ["case_revision_changed"],
      preview: null,
      redaction_counts: {},
      snapshot_hash: "hash-1",
      completed_at: now,
    }
    const newerCase: TestCase = { ...savedCase, revision: 2, last_result: staleResult, last_run_at: now }
    const latePassed: TestResult = { ...staleResult, status: "passed", failure_codes: [] }
    let resolveRun: ((value: TestRunResponse) => void) | undefined
    vi.mocked(fetchTestCases)
      .mockResolvedValueOnce([savedCase])
      .mockResolvedValueOnce([newerCase])
      .mockResolvedValueOnce([newerCase])
    vi.mocked(runTestCases).mockReturnValueOnce(new Promise((resolve) => { resolveRun = resolve }))
    renderTestLab()

    await user.click(await screen.findByRole("button", { name: "Run Fictional greeting" }))
    await user.click(screen.getByRole("button", { name: "Refresh" }))
    await screen.findByText("Expected: Allow · Revision 2")

    resolveRun?.({
      results: [{ ...latePassed, case_id: savedCase.id }],
      passed: 1,
      mismatched: 0,
      unavailable: 0,
      not_run: 0,
      revision_conflicts: 0,
    })

    expect(await screen.findByText("Stale result")).toBeInTheDocument()
    expect(screen.getByText("Expected: Allow · Revision 2")).toBeInTheDocument()
  })

  it("shows a failed run attempt instead of retaining a previous passed result", async () => {
    const user = userEvent.setup()
    const previousPass: TestResult = {
      case_revision: 1,
      status: "passed",
      expected_action: "allow",
      observed_action: "allow",
      failure_codes: [],
      preview: null,
      redaction_counts: {},
      snapshot_hash: "hash-old",
      completed_at: "2026-10-14T09:00:00Z",
    }
    const previouslyPassedCase: TestCase = { ...savedCase, last_result: previousPass, last_run_at: previousPass.completed_at }
    const failedAttempt: TestResult = {
      ...previousPass,
      status: "unavailable",
      failure_codes: ["result_commit_failed"],
      snapshot_hash: null,
      completed_at: now,
    }
    vi.mocked(fetchTestCases)
      .mockResolvedValueOnce([previouslyPassedCase])
      .mockResolvedValueOnce([previouslyPassedCase])
    vi.mocked(runTestCases).mockResolvedValue({
      results: [{ ...failedAttempt, case_id: savedCase.id }],
      passed: 0,
      mismatched: 0,
      unavailable: 1,
      not_run: 0,
      revision_conflicts: 0,
    })
    renderTestLab()

    await user.click(await screen.findByRole("button", { name: "Run Fictional greeting" }))

    expect(await screen.findByText("Unavailable")).toBeInTheDocument()
    expect(screen.queryByText("Matching expected outcome")).not.toBeInTheDocument()
  })

  it("keeps a newer same-revision result fetched before a late successful response", async () => {
    const user = userEvent.setup()
    const newerMismatch: TestResult = {
      case_revision: 1,
      status: "mismatch",
      expected_action: "allow",
      observed_action: "block",
      failure_codes: [],
      preview: null,
      redaction_counts: {},
      snapshot_hash: "hash-current",
      completed_at: "2026-10-14T10:01:00Z",
    }
    const currentCase: TestCase = { ...savedCase, last_result: newerMismatch, last_run_at: newerMismatch.completed_at }
    const latePassed: TestResult = {
      ...newerMismatch,
      status: "passed",
      observed_action: "allow",
      snapshot_hash: "hash-old",
      completed_at: now,
    }
    let resolveRun: ((value: TestRunResponse) => void) | undefined
    vi.mocked(fetchTestCases)
      .mockResolvedValueOnce([savedCase])
      .mockResolvedValueOnce([currentCase])
      .mockResolvedValueOnce([currentCase])
    vi.mocked(runTestCases).mockReturnValueOnce(new Promise((resolve) => { resolveRun = resolve }))
    renderTestLab()

    await user.click(await screen.findByRole("button", { name: "Run Fictional greeting" }))
    await user.click(screen.getByRole("button", { name: "Refresh" }))
    await waitFor(() => expect(fetchTestCases).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled())
    await act(async () => {
      resolveRun?.({
        results: [{ ...latePassed, case_id: savedCase.id }],
        passed: 1,
        mismatched: 0,
        unavailable: 0,
        not_run: 0,
        revision_conflicts: 0,
      })
    })

    await waitFor(() => expect(fetchTestCases).toHaveBeenCalledTimes(3))
    expect(await screen.findByText("Outcome differs")).toBeInTheDocument()
    expect(screen.queryByText("Matching expected outcome")).not.toBeInTheDocument()
  })
})
