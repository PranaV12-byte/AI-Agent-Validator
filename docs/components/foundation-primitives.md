# UI foundation component contracts

These primitives are scoped to the development-only foundation preview. Future product screens may reuse them after review; the existing dark legacy routes are not changed by this slice.

| Component | Contract |
| --- | --- |
| FrameLogo | Deterministic SVG Frame mark; 24, 28, 32, or 64px. The standalone mark has an accessible name. Lockup reads SafeBot with a 12px gap. |
| Button | Primary, secondary, and subtle variants. Native disabled behavior, visible keyboard focus, and type=button by default. |
| Input / TextArea | Explicitly associated label, optional helper and error, linked descriptions, aria-invalid on error, and native disabled/required behavior. |
| Card | White surface with a thin boundary and 16px radius; padding is opt-in so layout remains explicit. |
| StatusBadge | Text-first preview, info, success, warning, danger, and neutral tones. A tone never substitutes for its visible label. |
| FoundationSidebar | Reusable text-first desktop navigation with an in-memory collapse control; collapsed desktop uses an 80px icon rail with named links, selected state, and hover/focus tooltips. Its footer remains reachable while the menu scrolls. At 720px and below it switches to a separate closed-by-default disclosure; Escape closes from the menu or disclosure and returns focus to the trigger. Same-page mobile hash links close the menu, move focus to the target, and temporarily add tabindex=-1 only when needed. Brand destinations, accessible labels, menu id, and navigation items are configurable; route changes and modified-link activations stay native. |
| Modal | Named modal dialog with initial focus, Tab/Shift+Tab containment, inert and aria-hidden background, body scroll lock, Escape, close control, backdrop close, focus return, bounded scrolling, and a narrow-screen width. |
| Tabs | Named tab list, one rendered panel at a time, selected state and relationships, click selection, and Arrow/Home/End keyboard navigation. |

The preview intentionally disables sample save and check actions. The modal's Cancel and close controls only dismiss the local preview. Profile/security field drafts are held in component memory; no browser storage or API call is used.

The sidebar lives in frontend/src/components/foundation/FoundationSidebar.tsx, with its self-contained responsive rules in sidebar.css. Its default navigation and brand copy are preview fixtures; callers should pass their own items and destination/labels. Collapsed tooltip show/hide timers are bounded and cleared on focus, Escape, breakpoint changes, and unmount.
