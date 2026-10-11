# UI foundation component contracts

These primitives are scoped to the development-only foundation preview. Future product screens may reuse them after review; the existing dark legacy routes are not changed by this slice.

| Component | Contract |
| --- | --- |
| FrameLogo | Deterministic SVG Frame mark; 24, 28, 32, or 64px. The standalone mark has an accessible name. Lockup reads SafeBot with a 12px gap. |
| Button | Primary, secondary, and subtle variants. Native disabled behavior, visible keyboard focus, and type=button by default. |
| Input / TextArea | Explicitly associated label, optional helper and error, linked descriptions, aria-invalid on error, and native disabled/required behavior. |
| Card | White surface with a thin boundary and 16px radius; padding is opt-in so layout remains explicit. |
| StatusBadge | Text-first preview, info, success, warning, danger, and neutral tones. A tone never substitutes for its visible label. |
| Modal | Named modal dialog with initial focus, Tab/Shift+Tab containment, inert and aria-hidden background, body scroll lock, Escape, close control, backdrop close, focus return, bounded scrolling, and a narrow-screen width. |
| Tabs | Named tab list, one rendered panel at a time, selected state and relationships, click selection, and Arrow/Home/End keyboard navigation. |

The preview intentionally disables sample save and check actions. The modal's Cancel and close controls only dismiss the local preview. Profile/security field drafts are held in component memory; no browser storage or API call is used.
