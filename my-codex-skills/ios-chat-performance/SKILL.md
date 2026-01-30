---
name: ios-chat-performance
description: Enforce high-performance patterns for iOS chat interfaces. Use when designing, implementing, or modifying chat UIs using UITableView or UICollectionView, especially with dynamic height cells, streaming updates, images, WebView/Markdown rendering, or large message histories. Prioritize scroll smoothness, stable layout, and predictable performance over convenience or abstraction.
---

# iOS Chat Performance

Apply strict performance-first rules when building or modifying iOS chat interfaces.

## Core Objective

Preserve smooth scrolling and layout stability under all conditions.

Assume:
- Long message histories
- Frequent incremental updates
- Dynamic content (text, images, markdown, web content)
- High sensitivity to frame drops and layout thrashing

## Non-Negotiable Rules

Do NOT:
- Recalculate cell height during scrolling
- Trigger full layout passes on incremental updates
- Reload entire sections for single message changes
- Block the main thread with parsing, rendering, or layout work
- Create or destroy heavy views during scroll

Performance correctness is more important than architectural purity.

---

## Data → Layout → Render Separation

Strictly separate responsibilities:

- **Data layer**: message models, immutable where possible
- **Layout layer**: precomputed layout metrics (height, size)
- **Render layer**: lightweight views bound to prepared layout data

Never compute layout inside `cellForItemAt` or `willDisplay`.

---

## Cell Height Strategy (Critical)

- Heights must be:
  - Cached
  - Deterministic
  - Computed off the main thread when possible

Allowed patterns:
- Precompute height when message arrives
- Update cached height only when content actually changes
- Use estimated sizes only for initial bootstrap

Forbidden patterns:
- Auto Layout self-sizing during scroll
- Calling `systemLayoutSizeFitting` repeatedly
- Letting WebView or async content dictate cell size mid-scroll

---

## Incremental Updates (Streaming / Typing Effect)

When messages stream or update progressively:

- Update only the affected cell
- Prefer `reloadItems(at:)` over `reloadData`
- Preserve content offset unless explicitly scrolling
- Never invalidate the entire layout for partial updates

Layout invalidation must be localized.

---

## WebView & Heavy Content

Treat `WKWebView` as a hostile performance component.

Rules:
- Never allow WebView creation during scrolling
- Prefer pre-rendered snapshots or placeholders
- Reuse WebView instances via pooling
- Detach WebView from hierarchy when off-screen
- Avoid JavaScript execution on the main thread

If text selection or interaction is required:
- Defer activation until scroll ends
- Use static render during scroll

---

## Image Handling

- Decode images off the main thread
- Cache decoded images
- Avoid triggering layout when image finishes loading
- Reserve final image size up front to avoid relayout

Image loading must not cause cell height changes mid-scroll.

---

## Scrolling Behavior

Scrolling must be deterministic.

Do NOT:
- Call `scrollToItem` during layout passes
- Modify constraints during scroll callbacks
- Trigger animations tied to layout updates

If auto-scroll is required:
- Perform after layout settles
- Prefer explicit user intent signals

---

## “New Message Push-Up” Pattern

When a new message arrives:

- Insert the new cell
- Preserve previous cells’ layout and position
- Do not recalculate historical cell sizes
- Avoid shifting content unless explicitly required

Chat history should feel anchored.

---

## Diff Strategy

- Apply minimal diffs to the data source
- Avoid re-binding unchanged cells
- Avoid reconfiguring views unnecessarily

Stable data → stable UI → smooth scroll.

---

## Debugging & Verification

Assume correctness is not proven until verified.

Validate:
- Scrolling FPS under load
- Layout passes per scroll
- Main thread time during updates
- Memory growth over long sessions

If performance degrades, favor simpler code over abstractions.

---

## Conflict Resolution

If a requested feature violates these rules:

- Explain the performance risk
- Propose a safer alternative
- Do not silently accept performance regressions

Smooth scrolling is a feature.

