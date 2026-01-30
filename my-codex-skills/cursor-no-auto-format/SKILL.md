---
name: cursor-no-auto-format
description: Prevent automatic code formatting, re-indentation, reordering, or stylistic refactoring. Use when editing or generating code where formatting must be preserved exactly, or when users complain about unwanted auto-formatting. Only allow formatting when the user explicitly requests it (e.g. says "format", "reformat", "格式化代码").
---

# Cursor No Auto Format

Enforce strict non-formatting behavior when editing or generating code.

## Core Rule

Do NOT format code by default.

Formatting includes (but is not limited to):

- Re-indenting code
- Changing line breaks
- Wrapping or unwrapping lines
- Reordering imports, properties, or methods
- Applying prettier / swift-format / clang-format / gofmt / black
- Stylistic refactors that do not change behavior

Preserve the original formatting exactly as provided.

## When Formatting Is Allowed

Formatting is allowed **only if** the user explicitly requests it using words such as:

- "format"
- "reformat"
- "format this code"
- "整理代码"
- "格式化代码"
- "apply formatter"

If the request is ambiguous, assume formatting is NOT allowed.

## Editing Behavior (Non-formatting Mode)

When formatting is not explicitly requested:

- Make the smallest possible code change
- Modify logic only where required
- Keep indentation, spacing, and line breaks unchanged
- Avoid touching unrelated lines
- Prefer localized edits over refactors

If a change would normally trigger formatting, rewrite the logic while preserving the existing layout.

## Language-Specific Guidance

### Swift

- Treat formatting as semantically significant
- Never assume style changes are acceptable
- Do not normalize access modifiers, spacing, or brace placement

### General

- Avoid “cleanup” edits
- Avoid “improving readability” unless requested
- Prefer correctness over aesthetics

## Conflict Resolution

If a requested change cannot be made without reformatting:

- Explain briefly why formatting would be required
- Ask the user whether formatting is allowed
- Do not proceed until confirmed

