import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import Layout from "./Layout"

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
}))

describe("responsive navigation", () => {
  let desktop: { matches: boolean; addEventListener: ReturnType<typeof vi.fn>; removeEventListener: ReturnType<typeof vi.fn> }
  let onResize: (() => void) | undefined
  const showDescriptor = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal")
  const closeDescriptor = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close")

  beforeEach(() => {
    // JSDOM does not manage the native dialog top layer; real modality/focus
    // trapping is exercised separately in Chromium at mobile widths.
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value(this: HTMLDialogElement) { this.open = true },
    })
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.open = false
        this.dispatchEvent(new Event("close"))
      },
    })
    desktop = {
      matches: false,
      addEventListener: vi.fn((_type, listener) => { onResize = listener }),
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal("matchMedia", vi.fn(() => desktop))
  })

  afterEach(() => {
    cleanup()
    if (showDescriptor) Object.defineProperty(HTMLDialogElement.prototype, "showModal", showDescriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal")
    if (closeDescriptor) Object.defineProperty(HTMLDialogElement.prototype, "close", closeDescriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, "close")
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  function mount() {
    return render(
      <MemoryRouter initialEntries={["/integration"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/integration" element={<h1>Integration content</h1>} />
            <Route path="/policies" element={<h1>Policy content</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
  }

  it("opens a labelled native drawer and dismisses it with focus returned", async () => {
    mount()
    const user = userEvent.setup()
    const toggle = screen.getByRole("button", { name: "Open navigation" })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    await user.click(toggle)
    const dialog = screen.getByRole("dialog", { name: "Navigation" })
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    await user.click(within(dialog).getByRole("button", { name: "Close navigation" }))
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    expect(toggle).toHaveFocus()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("closes after navigation and preserves every destination", async () => {
    mount()
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "Open navigation" }))
    const dialog = screen.getByRole("dialog", { name: "Navigation" })
    expect(within(dialog).getAllByRole("link")).toHaveLength(6)
    await user.click(within(dialog).getByRole("link", { name: "Protection Rules" }))
    expect(await screen.findByRole("heading", { name: "Policy content" })).toBeVisible()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("handles Escape cancellation and backdrop dismissal", async () => {
    mount()
    const user = userEvent.setup()
    const toggle = screen.getByRole("button", { name: "Open navigation" })
    await user.click(toggle)
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }))
    expect(toggle).toHaveFocus()
    await user.click(toggle)
    fireEvent.click(screen.getByRole("dialog"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("closes on desktop resize and removes the media listener on unmount", async () => {
    const view = mount()
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "Open navigation" }))
    desktop.matches = true
    // The application listens to the media query, not a window width guess.
    act(() => onResize?.())
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    view.unmount()
    expect(desktop.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function))
  })
})
