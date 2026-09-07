/**
 * Structured parser for PLAN.md and review artifacts.
 *
 * Unlike rag-gateway's entity extractor (which uses an LLM to extract
 * entities from unstructured conversation text), this parser operates
 * on the well-known structure of PLAN.md files:
 *
 *   # Plan: <title>
 *   ## Goal
 *   ## Constraints & assumptions
 *   ## Approach
 *   ## Key decisions & tradeoffs
 *   ## Validation plan
 *   ## Risks / non-blocking open questions
 *   ## Out of scope
 *
 * And PLAN-REVIEW-LOG.md:
 *   - MAX_ROUNDS, Reviewers
 *   - Round N - <reviewer> → Flaws → VERDICT
 *   - Orchestrator response: Accepted / Rejected
 *   - Resolution
 *
 * No LLM calls needed — pure structural parsing.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type {
	PlanSections,
	PlanArtifact,
	PlanResolution,
} from "./types.js";

// ─── PLAN.md parser ──────────────────────────────────────────────────

const SECTION_PATTERNS: Array<{
	key: keyof PlanSections;
	regex: RegExp;
}> = [
	{ key: "goal", regex: /^##\s+Goal\s*$/im },
	{ key: "constraints", regex: /^##\s+Constraints\s*[&]\s*assumptions\s*$/im },
	{ key: "approach", regex: /^##\s+Approach\s*$/im },
	{ key: "decisions", regex: /^##\s+Key\s+decisions\s*[&]\s*tradeoffs\s*$/im },
	{ key: "validation", regex: /^##\s+Validation\s+plan\s*$/im },
	{ key: "risks", regex: /^##\s+Risks\s*\/\s*non-blocking\s+open\s+questions\s*$/im },
	{ key: "outOfScope", regex: /^##\s+Out\s+of\s+scope\s*$/im },
];

/**
 * Extract the title from the first H1 heading in PLAN.md content.
 */
function extractTitle(content: string): string {
	const match = content.match(/^#\s+(.+?)(?:\s*\{[^}]*\})?\s*$/m);
	return match ? match[1].trim() : "Untitled Plan";
}

/**
 * Parse a PLAN.md file into structured sections.
 */
export function parsePlan(content: string): PlanSections {
	const title = extractTitle(content);

	// Normalize line endings
	const normalized = content.replace(/\r\n/g, "\n");

	// Find section boundaries
	const sections = new Map<keyof PlanSections, { start: number; end: number }>();

	for (const { key, regex } of SECTION_PATTERNS) {
		const match = normalized.match(regex);
		if (match && match.index !== undefined) {
			sections.set(key, { start: match.index + match[0].length, end: Infinity });
		}
	}

	// Sort sections by their position in the document
	const sorted = Array.from(sections.entries())
		.sort((a, b) => a[1].start - b[1].start);

	// Set end of each section to the start of the next one (or end of doc)
	for (let i = 0; i < sorted.length; i++) {
		if (i + 1 < sorted.length) {
			sections.get(sorted[i][0])!.end = sorted[i + 1][1].start;
		}
	}

	function getSection(key: keyof PlanSections): string {
		const range = sections.get(key);
		if (!range) return "";
		const text = normalized.slice(range.start, range.end).trim();
		// Remove trailing section header lines that leaked in
		return cleanupSection(text);
	}

	return {
		title,
		goal: getSection("goal"),
		constraints: getSection("constraints"),
		approach: getSection("approach"),
		decisions: getSection("decisions"),
		validation: getSection("validation"),
		risks: getSection("risks"),
		outOfScope: getSection("outOfScope"),
	};
}

/**
 * Clean up a section body: remove any trailing section headers from other sections.
 */
function cleanupSection(text: string): string {
	// Remove any remaining H2 headers that might have leaked in
	return text.replace(/^##\s+.+$/gm, "").trim();
}

// ─── PLAN-REVIEW-LOG.md parser ──────────────────────────────────────

/** Parsed review metadata from PLAN-REVIEW-LOG.md. */
export interface ReviewMetadata {
	resolution: PlanResolution;
	reviewers: string[];
}

/**
 * Parse PLAN-REVIEW-LOG.md to extract review metadata (resolution, reviewers).
 * Handles the multi-round format with retries.
 */
export function parseReviewLog(content: string): ReviewMetadata {
	const resolution = extractResolution(content);
	const reviewers = extractReviewers(content);
	return { resolution, reviewers };
}

function extractResolution(content: string): PlanResolution {
	// Find the LAST ## Resolution section (after retries)
	const resolutionMatches = [...content.matchAll(/^##\s+(?:Retry\s+\d+\s+)?Resolution\s*$/gim)];
	if (resolutionMatches.length > 0) {
		// Look at content after the last resolution header
		const lastMatch = resolutionMatches[resolutionMatches.length - 1];
		const afterResolution = content.slice((lastMatch.index ?? 0) + lastMatch[0].length);

		if (/approved/i.test(afterResolution.slice(0, 500))) return "approved";
		if (/deadlock/i.test(afterResolution.slice(0, 500))) return "deadlock";
		if (/failed/i.test(afterResolution.slice(0, 500))) return "failed";

		return "pending";
	}

	// Fallback for auto-code-review logs that use `VERDICT: APPROVED|REVISE`
	// instead of a `## Resolution` section.
	if (/deadlock/i.test(content)) return "deadlock";
	const verdicts = [...content.matchAll(/^\s*VERDICT:\s*(APPROVED|REVISE)\s*$/gim)]
		.map((m) => m[1].toUpperCase());
	if (verdicts.length > 0) {
		const last = verdicts[verdicts.length - 1];
		if (last === "APPROVED") return "approved";
		return "failed";
	}

	return "pending";
}

function extractReviewers(content: string): string[] {
	const reviewers: string[] = [];

	// Match the Reviewers: section near the top
	const reviewerSection = content.match(/^Reviewers:\s*\n((?:^-\s+.+\n?)+)/m);
	if (reviewerSection) {
		for (const line of reviewerSection[1].split("\n")) {
			const name = line.match(/^-\s+(\S+)/);
			if (name) reviewers.push(name[1].toLowerCase());
		}
	}

	return reviewers;
}

// ─── Directory scanner ───────────────────────────────────────────────

/**
 * Scan the .plan-reviews/ directory and return metadata for all plans.
 */
export function scanPlansDir(rootDir: string): PlanArtifact[] {
	const plansDir = path.join(rootDir, ".plan-reviews");
	if (!fs.existsSync(plansDir)) return [];

	const artifacts: PlanArtifact[] = [];
	const entries = fs.readdirSync(plansDir, { withFileTypes: true });

	for (const entry of entries) {
		if (!entry.isDirectory()) continue;
		// Skip hidden directories such as the JSON cache location.
		if (entry.name.startsWith(".")) continue;

		const planPath = path.join(plansDir, entry.name);

		// ── Checkpoint artifact (checkpoint-persist) ──
		if (entry.name === "checkpoint") {
			scanCheckpointDir(planPath, artifacts);
			continue;
		}

		const planFile = path.join(planPath, "PLAN.md");
		const reviewFile = path.join(planPath, "PLAN-REVIEW-LOG.md");
		const architectureFile = path.join(planPath, "architecture-analysis.md");
		const summaryFile = path.join(planPath, "SUMMARY.md");

		// ── Plan artifact (plan-grill / cross-model-review) ──
		if (fs.existsSync(planFile)) {
			try {
				const planContent = fs.readFileSync(planFile, "utf-8");
				const sections = parsePlan(planContent);

				let reviewers: string[] = [];
				let resolution: PlanResolution = "pending";
				let reviewLogText: string | undefined;

				if (fs.existsSync(reviewFile)) {
					const reviewContent = fs.readFileSync(reviewFile, "utf-8");
					reviewLogText = reviewContent;
					const meta = parseReviewLog(reviewContent);
					reviewers = meta.reviewers;
					resolution = meta.resolution;
				}
				const architectureAnalysis = fs.existsSync(architectureFile)
					? fs.readFileSync(architectureFile, "utf-8")
					: undefined;
				const summaryText = fs.existsSync(summaryFile)
					? fs.readFileSync(summaryFile, "utf-8")
					: undefined;

				artifacts.push({
					id: entry.name,
					path: planPath,
					sections,
					architectureAnalysis,
					reviewLogText,
					summaryText,
					hasReview: fs.existsSync(reviewFile),
					resolution,
					reviewers,
					createdAt: extractDateFromId(entry.name),
					kind: "plan",
				});
			} catch (err) {
				console.warn(`[plan-reviews] Failed to parse ${entry.name}: ${(err as Error).message}`);
			}
		} else {
			// ── Code-review artifact (auto-code-review) ──
			const codeReviewArtifact = parseCodeReview(entry.name, planPath);
			if (codeReviewArtifact) {
				artifacts.push(codeReviewArtifact);
			} else {
				// ── Prompt-optimization artifact (prompt-optimizer) ──
				const promptOptArtifact = parsePromptOptimization(entry.name, planPath);
				if (promptOptArtifact) artifacts.push(promptOptArtifact);
			}
		}
	}

	// Sort by date, newest first
	artifacts.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

	return artifacts;
}

/**
 * Extract ISO date from plan directory name prefix (e.g. "2026-07-06-login-rate-limit").
 */
function extractDateFromId(id: string): string {
	const match = id.match(/^(\d{4}-\d{2}-\d{2})/);
	return match ? match[1] : "unknown";
}

/**
 * Parse an auto-code-review directory into a PlanArtifact.
 *
 * A code-review directory contains REVIEW-LOG.md + diff.patch (and optionally
 * QUESTION.md / RESPONSE.md) but no PLAN.md. We synthesize a `sections` object
 * so the existing entity/chunk extractors can index it without special-casing:
 *   - title  ← first heading line of QUESTION.md, else the directory name
 *   - goal   ← user question text (QUESTION.md)
 *   - approach ← change summary (RESPONSE.md "变更目的" section)
 * The raw diff and review log are carried as `diffText` / `reviewLogText` and
 * turned into searchable chunks by the extractor.
 *
 * Returns null if the directory is not a recognizable code-review artifact.
 */
function parseCodeReview(
	id: string,
	planPath: string,
): PlanArtifact | null {
	const reviewLogFile = path.join(planPath, "REVIEW-LOG.md");
	const diffFile = path.join(planPath, "diff.patch");
	const questionFile = path.join(planPath, "QUESTION.md");
	const responseFile = path.join(planPath, "RESPONSE.md");

	// Must look like an auto-code-review artifact.
	if (!fs.existsSync(reviewLogFile) || !fs.existsSync(diffFile)) return null;

	let title = id;
	let goal = "";
	let approach = "";
	let diffText = "";
	let reviewLogText = "";
	let responseText = "";

	try {
		if (fs.existsSync(questionFile)) {
			const q = fs.readFileSync(questionFile, "utf-8");
			const h1 = q.match(/^#\s+(.+?)\s*$/m);
			if (h1) title = h1[1].trim();
			// Drop the first heading line; keep the rest as the goal.
			goal = q.replace(/^#\s+.+$/m, "").trim();
		}
		if (fs.existsSync(responseFile)) {
			const r = fs.readFileSync(responseFile, "utf-8");
			responseText = r;
			const m = r.match(/##\s*变更目的\s*\n([\s\S]*?)(?=\n##\s|$)/);
			approach = m ? m[1].trim() : "";
		}
		diffText = fs.readFileSync(diffFile, "utf-8");
		reviewLogText = fs.readFileSync(reviewLogFile, "utf-8");

		const meta = parseReviewLog(reviewLogText);

		const sections: PlanSections = {
			title,
			goal,
			constraints: "",
			approach,
			decisions: "",
			validation: "",
			risks: "",
			outOfScope: "",
		};

		return {
			id,
			path: planPath,
			sections,
			hasReview: true,
			resolution: meta.resolution,
			reviewers: meta.reviewers,
			createdAt: extractDateFromId(id),
			kind: "code-review",
			diffText,
			reviewLogText,
			responseText,
		};
	} catch (err) {
		console.warn(`[plan-reviews] Failed to parse code-review ${id}: ${(err as Error).message}`);
		return null;
	}
}

/**
 * Parse a prompt-optimizer directory into a PlanArtifact.
 *
 * A prompt-optimization directory stores each archive field in its own file so
 * arbitrary user text (which may contain `## 澄清结论` / `## 优化后提示词` or
 * any other Markdown) never collides with field delimiters:
 *   - PROMPT-OPTIMIZATION.md → manifest carrying the `# <title>` line
 *   - QUESTION.md            → 原始提问 (the user's original question)
 *   - CLARIFICATION.md       → 澄清结论 (clarification outcome)
 *   - OPTIMIZED.md           → 优化后提示词 (the optimized prompt)
 *
 * Returns null unless at least one field file is present. A lone manifest
 * (the retired single-file layout) is refused, never indexed as an empty
 * artifact.
 */
function parsePromptOptimization(
	id: string,
	planPath: string,
): PlanArtifact | null {
	const manifestFile = path.join(planPath, "PROMPT-OPTIMIZATION.md");
	const questionFile = path.join(planPath, "QUESTION.md");
	const clarificationFile = path.join(planPath, "CLARIFICATION.md");
	const optimizedFile = path.join(planPath, "OPTIMIZED.md");

	const hasManifest = fs.existsSync(manifestFile);
	const hasFieldFiles =
		fs.existsSync(questionFile) ||
		fs.existsSync(clarificationFile) ||
		fs.existsSync(optimizedFile);
	if (!hasFieldFiles) {
		// A lone manifest without field files is the retired single-file layout;
		// refuse to index it as an empty-but-valid-looking artifact.
		if (hasManifest) {
			console.warn(
				`[plan-reviews] Skipping legacy single-file prompt-optimization archive at ${planPath}; ` +
					`migrate to per-field files (QUESTION.md / CLARIFICATION.md / OPTIMIZED.md) to index it.`,
			);
		}
		return null;
	}

	try {
		const readText = (file: string): string =>
			fs.existsSync(file)
				? fs.readFileSync(file, "utf-8").replace(/\r\n/g, "\n").trim()
				: "";

		// Title lives in the manifest's first H1 line; fall back to the dir id.
		let title = id;
		if (hasManifest) {
			const h1 = readText(manifestFile).match(/^#\s+(.+?)\s*$/m);
			if (h1) title = h1[1].trim();
		}

		const goal = readText(questionFile);
		const constraints = readText(clarificationFile);
		const approach = readText(optimizedFile);

		const sections: PlanSections = {
			title,
			goal,
			constraints,
			approach,
			decisions: "",
			validation: "",
			risks: "",
			outOfScope: "",
		};

		return {
			id,
			path: planPath,
			sections,
			hasReview: false,
			resolution: "pending",
			reviewers: [],
			createdAt: extractDateFromId(id),
			kind: "prompt-optimization",
		};
	} catch (err) {
		console.warn(`[plan-reviews] Failed to parse prompt-optimization ${id}: ${(err as Error).message}`);
		return null;
	}
}

/**
 * Parse a checkpoint-persist artifact directory into a PlanArtifact.
 *
 * A checkpoint directory (`.plan-reviews/checkpoint/<task-slug>/CHECKPOINT.md`)
 * carries mid-flight intermediate conclusions produced by the global
 * `checkpoint-persist` skill. Unlike a finished PLAN.md, it is "in progress":
 *   - title     ← `# Checkpoint: <主题>` heading (fallback: directory name)
 *   - goal      ← `## 任务摘要` (task summary)
 *   - decisions ← `## 已产出结论` (conclusions + decisions produced so far)
 *   - risks     ← `- 未决问题：` lines extracted from conclusions
 *   - approach  ← `## 下一步` (remaining items to analyze)
 *
 * Returns null if the directory has no CHECKPOINT.md.
 */
function parseCheckpoint(slug: string, taskDir: string): PlanArtifact | null {
	const checkpointFile = path.join(taskDir, "CHECKPOINT.md");
	if (!fs.existsSync(checkpointFile)) return null;

	try {
		const content = fs.readFileSync(checkpointFile, "utf-8").replace(/\r\n/g, "\n");
		const titleMatch = content.match(/^#\s+(?:Checkpoint\s*:\s*)?(.+?)\s*$/m);
		const title = titleMatch ? titleMatch[1].trim() : slug;
		const summary = extractMarkdownSection(content, "任务摘要");
		const conclusions = extractMarkdownSection(content, "已产出结论");
		const next = extractMarkdownSection(content, "下一步");
		// Drop blank placeholders (无 / N/A / none / …) so a template default is
		// never indexed as a real risk; leave risks empty when nothing remains.
		const openQuestions = filterBlankValues(extractLabeledLines(conclusions, "未决问题"));

		const sections: PlanSections = {
			title,
			goal: summary,
			constraints: "",
			approach: next,
			decisions: conclusions,
			validation: "",
			risks: openQuestions,
			outOfScope: "",
		};

		return {
			// Namespace checkpoint ids with a reserved prefix so an in-progress
			// checkpoint can never collide with a finished plan sharing the same
			// directory slug (PlanStore / sync / chunks / entities all key on planId).
			id: `checkpoint:${slug}`,
			path: taskDir,
			sections,
			hasReview: false,
			resolution: "pending",
			reviewers: [],
			createdAt:
				extractDateFromId(slug) !== "unknown"
					? extractDateFromId(slug)
					: isoDateFromMtime(checkpointFile),
			kind: "checkpoint",
		};
	} catch (err) {
		console.warn(`[plan-reviews] Failed to parse checkpoint ${slug}: ${(err as Error).message}`);
		return null;
	}
}

/**
 * Scan `.plan-reviews/checkpoint/` for per-task checkpoint directories.
 * Each sub-directory containing a CHECKPOINT.md becomes a checkpoint artifact.
 */
function scanCheckpointDir(checkpointDir: string, artifacts: PlanArtifact[]): void {
	if (!fs.existsSync(checkpointDir)) return;

	let entries: fs.Dirent[];
	try {
		entries = fs.readdirSync(checkpointDir, { withFileTypes: true });
	} catch {
		return;
	}

	for (const entry of entries) {
		if (!entry.isDirectory()) continue;
		if (entry.name.startsWith(".")) continue;

		const taskDir = path.join(checkpointDir, entry.name);
		const artifact = parseCheckpoint(entry.name, taskDir);
		if (artifact) artifacts.push(artifact);
	}
}

/**
 * Extract the body of a `## <header>` Markdown section (up to the next `## `).
 */
function extractMarkdownSection(content: string, header: string): string {
	const pattern = new RegExp(`^##\\s+${header}\\s*$`, "m");
	const match = pattern.exec(content);
	if (!match || match.index === undefined) return "";

	const start = match.index + match[0].length;
	const rest = content.slice(start);
	const next = rest.match(/^##\s+/m);
	const end = next ? start + (next.index ?? 0) : content.length;
	return content.slice(start, end).trim();
}

/**
 * Extract the values of all `- <label>：<value>` lines within a section body.
 */
function extractLabeledLines(section: string, label: string): string {
	const pattern = new RegExp(`^\\s*-\\s*${label}\\s*[：:]\\s*(.+)$`, "gm");
	const lines: string[] = [];
	let m: RegExpExecArray | null;
	while ((m = pattern.exec(section)) !== null) {
		lines.push(m[1].trim());
	}
	return lines.join("\n");
}

/**
 * Drop blank placeholders (无 / 暂无 / N/A / none / …) from newline-joined lines.
 * Returns the remaining non-blank lines; empty string when nothing remains.
 */
function filterBlankValues(lines: string): string {
	return lines
		.split("\n")
		.map((line) => line.trim())
		.filter((line) => line !== "" && !isBlankValue(line))
		.join("\n");
}

/**
 * Recognize a value that semantically means "no open question" (template default),
 * so it is never indexed as a real risk entity.
 */
function isBlankValue(value: string): boolean {
	const normalized = value.replace(/[。.；;]\s*$/u, "").trim().toLowerCase();
	return ["无", "暂无", "没有", "none", "n/a", "na", "null", "nil", "-", "—", "~"].includes(normalized);
}

/**
 * ISO date (YYYY-MM-DD) from a file's mtime, for artifacts without a date prefix.
 */
function isoDateFromMtime(file: string): string {
	try {
		return new Date(fs.statSync(file).mtimeMs).toISOString().slice(0, 10);
	} catch {
		return "unknown";
	}
}

/**
 * Check if a plan file has been modified since the given timestamp.
 */
export function getPlanMtime(planPath: string): number {
	const planFile = path.join(planPath, "PLAN.md");
	const reviewFile = path.join(planPath, "PLAN-REVIEW-LOG.md");
	const architectureFile = path.join(planPath, "architecture-analysis.md");
	// auto-code-review artifacts
	const codeReviewLog = path.join(planPath, "REVIEW-LOG.md");
	const diffFile = path.join(planPath, "diff.patch");
	const questionFile = path.join(planPath, "QUESTION.md");
	const responseFile = path.join(planPath, "RESPONSE.md");
	const summaryFile = path.join(planPath, "SUMMARY.md");
	const promptOptFile = path.join(planPath, "PROMPT-OPTIMIZATION.md");
	const promptClarificationFile = path.join(planPath, "CLARIFICATION.md");
	const promptOptimizedFile = path.join(planPath, "OPTIMIZED.md");
	// checkpoint-persist artifacts
	const checkpointFile = path.join(planPath, "CHECKPOINT.md");

	let mtime = 0;
	if (fs.existsSync(planFile)) {
		mtime = Math.max(mtime, fs.statSync(planFile).mtimeMs);
	}
	if (fs.existsSync(reviewFile)) {
		mtime = Math.max(mtime, fs.statSync(reviewFile).mtimeMs);
	}
	if (fs.existsSync(architectureFile)) {
		mtime = Math.max(mtime, fs.statSync(architectureFile).mtimeMs);
	}
	if (fs.existsSync(codeReviewLog)) {
		mtime = Math.max(mtime, fs.statSync(codeReviewLog).mtimeMs);
	}
	if (fs.existsSync(diffFile)) {
		mtime = Math.max(mtime, fs.statSync(diffFile).mtimeMs);
	}
	if (fs.existsSync(questionFile)) {
		mtime = Math.max(mtime, fs.statSync(questionFile).mtimeMs);
	}
	if (fs.existsSync(responseFile)) {
		mtime = Math.max(mtime, fs.statSync(responseFile).mtimeMs);
	}
	if (fs.existsSync(summaryFile)) {
		mtime = Math.max(mtime, fs.statSync(summaryFile).mtimeMs);
	}
	if (fs.existsSync(promptOptFile)) {
		mtime = Math.max(mtime, fs.statSync(promptOptFile).mtimeMs);
	}
	if (fs.existsSync(promptClarificationFile)) {
		mtime = Math.max(mtime, fs.statSync(promptClarificationFile).mtimeMs);
	}
	if (fs.existsSync(promptOptimizedFile)) {
		mtime = Math.max(mtime, fs.statSync(promptOptimizedFile).mtimeMs);
	}
	if (fs.existsSync(checkpointFile)) {
		mtime = Math.max(mtime, fs.statSync(checkpointFile).mtimeMs);
	}
	return mtime;
}
