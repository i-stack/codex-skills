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
 * A prompt-optimization directory contains PROMPT-OPTIMIZATION.md (and no
 * PLAN.md / REVIEW-LOG.md / diff.patch). We synthesize a `sections` object so
 * the existing entity/chunk extractors can index it without special-casing:
 *   - title       ← first heading line of PROMPT-OPTIMIZATION.md
 *   - goal        ← 原始提问 (the user's original question)
 *   - constraints ← 澄清结论 (clarification outcome from the grilling pass)
 *   - approach    ← 优化后提示词 (the optimized prompt)
 *
 * Returns null if the directory does not contain a PROMPT-OPTIMIZATION.md.
 */
function parsePromptOptimization(
	id: string,
	planPath: string,
): PlanArtifact | null {
	const promptOptFile = path.join(planPath, "PROMPT-OPTIMIZATION.md");
	if (!fs.existsSync(promptOptFile)) return null;

	try {
		const content = fs.readFileSync(promptOptFile, "utf-8").replace(/\r\n/g, "\n");

		const titleMatch = content.match(/^#\s+(.+?)\s*$/m);
		const title = titleMatch ? titleMatch[1].trim() : id;

		const { goal, constraints, approach } = extractPromptSections(content);

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
 * Split a prompt-optimization file into its three fixed archive sections.
 *
 * Only the three fixed headings (`## 原始提问` / `## 澄清结论` / `## 优化后提示词`)
 * act as field boundaries. The final section (`优化后提示词`) runs to EOF so the
 * structured prompt's own H2 sub-headings (`## 目标` / `## 上下文` / ...) are kept
 * intact instead of being misread as the next top-level field.
 */
function extractPromptSections(content: string): { goal: string; constraints: string; approach: string } {
	const escapeRegExp = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	const headingPos = (heading: string): number => {
		const m = content.match(new RegExp(`^##\\s+${escapeRegExp(heading)}\\s*$`, "im"));
		return m && m.index !== undefined ? m.index : -1;
	};
	const afterHeadingLine = (pos: number): number => {
		if (pos < 0) return -1;
		const nl = content.indexOf("\n", pos);
		return nl < 0 ? content.length : nl + 1;
	};
	const slice = (start: number, end: number): string =>
		start < 0 ? "" : content.slice(start, end < 0 ? content.length : end).trim();

	const question = headingPos("原始提问");
	const clarify = headingPos("澄清结论");
	const optimized = headingPos("优化后提示词");

	return {
		goal: slice(afterHeadingLine(question), clarify),
		constraints: slice(afterHeadingLine(clarify), optimized),
		approach: slice(afterHeadingLine(optimized), -1),
	};
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
	return mtime;
}
