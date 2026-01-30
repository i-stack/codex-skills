---
name: swift-diff-minimizer
description: Minimize code diffs when editing Swift code. Use when modifying existing Swift code where diff size, reviewability, and behavioral safety are critical, such as production code, UI layouts, performance-sensitive paths, or large files. Prioritize smallest possible changes over refactors or stylistic improvements.
---

# Swift Diff Minimizer

Apply a strict minimal-diff strategy when editing Swift code.

## Core Principle

Make the smallest possible change that satisfies the request.

Prefer minimal diffs over cleaner code, better style, or refactoring.

## What “Minimal Diff” Means

A minimal diff:

- Changes only the lines that are strictly necessary
- Preserves surrounding code verbatim
- Avoids reformatting, reordering, or cleanup
- Avoids touching unrelated logic
- Avoids renaming unless explicitly requested

If two solutions are correct, choose the one with fewer changed lines.

## Prohibited Changes (Unless Explicitly Requested)

Do NOT:

- Reformat indentation or spacing
- Reorder properties, methods, or extensions
- Combine or split lines
- Rename variables, methods, or types
- Extract helper methods
- Inline methods
- Convert control flow styles (e.g. guard ↔ if)
- Apply “Swift best practices” refactors
- Modernize syntax (e.g. trailing closures, shorthand syntax)

Do not “clean up” code.

## Allowed Changes

You MAY:

- Fix the specific bug described
- Add the minimal required logic
- Insert condition checks inline
- Add a small local variable if unavoidable
- Add comments only if they clarify the change

Every added line must justify its existence.

## Decision Heuristics

When deciding how to apply a change:

1. Prefer modifying an existing line over adding a new one
2. Prefer adding a condition over restructuring logic
3. Prefer local changes over structural changes
4. Prefer duplication over abstraction (unless abstraction is requested)

Assume the existing structure was intentional.

## UI & Layout Sensitivity (Important)

For UIKit / SwiftUI / layout-related code:

- Treat layout code as order-sensitive
- Preserve constraint order and grouping
- Avoid regrouping or “organizing” layout blocks
- Avoid moving view setup across lifecycle methods

Small layout diffs can cause subtle regressions.

## Performance-Sensitive Code

For hot paths or frequently executed code:

- Avoid allocations unless necessary
- Avoid refactors that change execution order
- Preserve existing control flow where possible

Correctness > micro-optimizations.

## Conflict Resolution

If the request cannot be fulfilled without a large diff:

- Explain briefly why the diff would be large
- Propose the smallest viable change
- Ask for confirmation before proceeding

Never assume refactoring is acceptable.

