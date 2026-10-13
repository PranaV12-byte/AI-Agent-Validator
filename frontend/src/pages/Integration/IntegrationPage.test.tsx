import { cleanup, render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import IntegrationPage from "./IntegrationPage"
import { useAuth } from "../../hooks/useAuth"
import {
  fetchProtectedChatReadiness,
  submitProtectedChat,
  type ProtectedChatResponse,
} from "../../services/protectedChatService"

vi.mock("../../hooks/useAuth", () => ({ useAuth: vi.fn() }))
vi.mock("../../services/protectedChatService", () => ({
  fetchProtectedChatReadiness: vi.fn(),
  submitProtectedChat: vi.fn(),
}))

afterEach(() => cleanup())

describe("IntegrationPage", () => {
  beforeEach(() => {
    vi.mocked(fetchProtectedChatReadiness).mockResolvedValue({
      ready: false,
      error_code: "groq_api_key_missing",
      model: "openai/gpt-oss-20b",
    })
    vi.mocked(submitProtectedChat).mockReset()
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "tok",
      user: { id: "t1", company_name: "Co", email: "a@b.com", api_key_prefix: "abc12345", active_policy_version: 0 },
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
  })

  it("shows the full-key callout with a link to settings", () => {
    render(<MemoryRouter><IntegrationPage /></MemoryRouter>)
    expect(screen.getByText(/If you don't have it, go to/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Go to Settings/i })).toBeInTheDocument()
  })

  it("navigates to /settings when the callout button is clicked", () => {
    render(
      <MemoryRouter initialEntries={["/integration"]}>
        <Routes>
          <Route path="/integration" element={<IntegrationPage />} />
          <Route path="/settings" element={<div>settings page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByRole("button", { name: /Go to Settings/i }))
    expect(screen.getByText("settings page")).toBeInTheDocument()
  })

  it("explains when provider setup is missing without pretending to generate", async () => {
    render(<MemoryRouter><IntegrationPage /></MemoryRouter>)

    expect(await screen.findByText(/Backend setup is incomplete/)).toBeInTheDocument()
    expect(screen.getByText(/Provider not ready/)).toBeInTheDocument()
  })

  it("shows a real blocked result without an answer", async () => {
    vi.mocked(submitProtectedChat).mockResolvedValue({
      conversation_id: "conversation-1",
      status: "blocked",
      answer: null,
      fallback_message: "Stopped by a configured rule.",
      error_code: null,
      input_redacted: false,
      output_redacted: false,
      policy_version: 4,
      audit_ids: ["audit-1"],
    })
    render(<MemoryRouter><IntegrationPage /></MemoryRouter>)

    fireEvent.change(await screen.findByLabelText("Message"), {
      target: { value: "synthetic blocked example" },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run protected request/i }))

    expect(await screen.findByText(/Request blocked/)).toBeInTheDocument()
    expect(screen.getByText("Stopped by a configured rule.")).toBeInTheDocument()
    expect(screen.queryByText("unsafe generated answer")).not.toBeInTheDocument()
  })

  it("shows provider failure explicitly and never fabricates a response", async () => {
    vi.mocked(submitProtectedChat).mockResolvedValue({
      conversation_id: "conversation-2",
      status: "provider_unavailable",
      answer: null,
      fallback_message: "Generation is not configured.",
      error_code: "groq_api_key_missing",
      input_redacted: false,
      output_redacted: false,
      policy_version: 4,
      audit_ids: ["audit-2"],
    })
    render(<MemoryRouter><IntegrationPage /></MemoryRouter>)

    fireEvent.change(await screen.findByLabelText("Message"), {
      target: { value: "synthetic ordinary request" },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run protected request/i }))

    expect(await screen.findByText(/Provider unavailable/)).toBeInTheDocument()
    expect(screen.getByText(/Generation is not configured/)).toBeInTheDocument()
    expect(screen.queryByText(/Protected response/)).not.toBeInTheDocument()
  })

  it("cancels an in-flight request and prevents repeat submission", async () => {
    let requestSignal: AbortSignal | undefined
    vi.mocked(submitProtectedChat).mockImplementation((_message, signal) => {
      requestSignal = signal
      return new Promise(() => {})
    })
    render(<MemoryRouter><IntegrationPage /></MemoryRouter>)

    fireEvent.change(await screen.findByLabelText("Message"), {
      target: { value: "synthetic prompt" },
    })
    const submit = screen.getByRole("button", { name: /Run protected request/i })
    fireEvent.click(submit)

    expect(submit).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: /Stop waiting/i }))
    expect(requestSignal?.aborted).toBe(true)
    expect(screen.getByRole("button", { name: /Run protected request/i })).toBeEnabled()
    expect(screen.getByText(/Server-side processing may continue/)).toBeInTheDocument()
  })

  it("aborts an in-flight request when the authenticated session ends", async () => {
    let requestSignal: AbortSignal | undefined
    vi.mocked(submitProtectedChat).mockImplementation((_message, signal) => {
      requestSignal = signal
      return new Promise(() => {})
    })
    const view = render(<MemoryRouter><IntegrationPage /></MemoryRouter>)

    fireEvent.change(await screen.findByLabelText("Message"), {
      target: { value: "synthetic prompt" },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run protected request/i }))
    expect(requestSignal?.aborted).toBe(false)

    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      isHydrated: true,
      isLoading: false,
      accessToken: null,
      user: null,
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
    view.rerender(<MemoryRouter><IntegrationPage /></MemoryRouter>)

    expect(requestSignal?.aborted).toBe(true)
  })

  it("keeps an in-flight request across a routine token refresh for the same tenant", async () => {
    let resolveRequest: ((value: ProtectedChatResponse) => void) | undefined
    let requestSignal: AbortSignal | undefined
    vi.mocked(submitProtectedChat).mockImplementation((_message, signal) => {
      requestSignal = signal
      return new Promise((resolve) => { resolveRequest = resolve })
    })
    const view = render(<MemoryRouter><IntegrationPage /></MemoryRouter>)

    fireEvent.change(await screen.findByLabelText("Message"), {
      target: { value: "synthetic prompt" },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run protected request/i }))

    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: true,
      accessToken: "tok-refreshing",
      user: { id: "t1", company_name: "Co", email: "a@b.com", api_key_prefix: "abc12345", active_policy_version: 0 },
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
    view.rerender(<MemoryRouter><IntegrationPage /></MemoryRouter>)
    expect(requestSignal?.aborted).toBe(false)

    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "tok-refreshed",
      user: { id: "t1", company_name: "Co", email: "a@b.com", api_key_prefix: "abc12345", active_policy_version: 0 },
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
    view.rerender(<MemoryRouter><IntegrationPage /></MemoryRouter>)
    expect(requestSignal?.aborted).toBe(false)

    resolveRequest?.({
      conversation_id: "conversation-refresh",
      status: "allowed",
      answer: "Protected answer after refresh.",
      fallback_message: null,
      error_code: null,
      input_redacted: false,
      output_redacted: false,
      policy_version: 4,
      audit_ids: ["audit-refresh"],
    })
    expect(await screen.findByText("Protected answer after refresh.")).toBeInTheDocument()
    expect(screen.getByText(/No enabled rule blocked this request/)).toBeInTheDocument()
    expect(screen.getByText(/An allowed result is not a guarantee that a message is safe/)).toBeInTheDocument()
  })

  it("does not show an in-flight response after switching tenants", async () => {
    let resolveRequest: ((value: ProtectedChatResponse) => void) | undefined
    let requestSignal: AbortSignal | undefined
    vi.mocked(submitProtectedChat).mockImplementation((_message, signal) => {
      requestSignal = signal
      return new Promise((resolve) => { resolveRequest = resolve })
    })
    const view = render(<MemoryRouter><IntegrationPage /></MemoryRouter>)

    fireEvent.change(await screen.findByLabelText("Message"), {
      target: { value: "synthetic prompt" },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run protected request/i }))

    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "tenant-b-token",
      user: { id: "tenant-b", company_name: "Other", email: "b@b.com", api_key_prefix: "def67890", active_policy_version: 0 },
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
    view.rerender(<MemoryRouter><IntegrationPage /></MemoryRouter>)
    expect(requestSignal?.aborted).toBe(true)

    resolveRequest?.({
      conversation_id: "conversation-old",
      status: "allowed",
      answer: "Stale answer.",
      fallback_message: null,
      error_code: null,
      input_redacted: false,
      output_redacted: false,
      policy_version: 4,
      audit_ids: ["audit-old"],
    })
    expect(screen.queryByText("Stale answer.")).not.toBeInTheDocument()
  })
})
