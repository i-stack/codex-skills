/**
 * Shared types for the plan-reviews knowledge base.
 *
 * Mirrors the rag-gateway types but specialized for structured
 * PLAN.md artifacts rather than arbitrary conversation text.
 */

// ─── Plan artifact types ────────────────────────────────────────────

/** Parsed sections of a PLAN.md file (the seven required sections). */
export interface PlanSections {
	title: string;
	goal: string;
	constraints: string;
	approach: string;
	decisions: string;
	validation: string;
	risks: string;
	outOfScope: string;
}

/** Artifact kind: a plan-grill/cross-model-review plan, an auto-code-review code review, or a prompt-optimizer prompt optimization. */
export type PlanKind = "plan" | "code-review" | "prompt-optimization";

/** Metadata about a single plan-review directory. */
export interface PlanArtifact {
	/** Directory name, e.g. "2026-07-06-login-rate-limit" */
	id: string;
	/** Absolute path to the plan directory */
	path: string;
	/** Parsed PLAN.md sections (or synthesized sections for code-review) */
	sections: PlanSections;
	/** Optional PG-005 architecture analysis artifact */
	architectureAnalysis?: string;
	/** Whether a PLAN-REVIEW-LOG.md / REVIEW-LOG.md exists */
	hasReview: boolean;
	/** Review resolution: approved | failed | pending | deadlock */
	resolution: PlanResolution;
	/** Reviewers used */
	reviewers: string[];
	/** Created date (parsed from directory name prefix) */
	createdAt: string;
	/** Artifact kind — distinguishes plan vs code-review */
	kind: PlanKind;
	/** Raw diff text (code-review only) — indexed as a searchable chunk */
	diffText?: string;
	/** Raw review log text (code-review only) — indexed as a searchable chunk */
	reviewLogText?: string;
	/** Full response text (code-review only) — indexed without discarding non-summary sections */
	responseText?: string;
	/** Optional human-curated SUMMARY.md text */
	summaryText?: string;
}

export type PlanResolution = "approved" | "failed" | "pending" | "deadlock";

// ─── Entity / Relation types (GraphRAG equivalent) ──────────────────

/** An entity extracted from a plan or review artifact. */
export interface PlanEntity {
	id: string;
	planId: string;
	type: PlanEntityType;
	name: string;
	description: string;
	properties: Record<string, string>;
	createdAt: string;
}

/** Typed entity categories for plan-specific knowledge graphs. */
export type PlanEntityType =
	| "goal"
	| "constraint"
	| "decision"
	| "risk"
	| "technology"
	| "service"
	| "pattern"
	| "flaw"           // from PLAN-REVIEW-LOG.md
	| "reviewer"       // from PLAN-REVIEW-LOG.md
	| "out_of_scope";

/** A directed relationship between two plan entities. */
export interface PlanRelation {
	id: string;
	planId: string;
	fromEntityId: string;
	toEntityId: string;
	relation: PlanRelationType;
	properties: Record<string, string>;
	createdAt: string;
}

export type PlanRelationType =
	| "uses"
	| "addresses"
	| "mitigates"
	| "constrains"
	| "depends_on"
	| "found"          // reviewer found flaw
	| "accepted"       // orchestrator accepted flaw
	| "rejected"       // orchestrator rejected flaw
	| "references";

/** Result of a graph search: matched entity plus its neighborhood. */
export interface GraphSearchResult {
	entity: PlanEntity;
	relations: Array<{
		relation: PlanRelation;
		fromEntity: PlanEntity;
		toEntity: PlanEntity;
	}>;
}

// ─── Chunk / Embedding types ─────────────────────────────────────────

/** A text chunk from a plan section ready for embedding. */
export interface PlanChunk {
	id: string;
	planId: string;
	section: string;    // which section this chunk came from
	text: string;
}

/** A chunk with its embedding vector persisted. */
export interface EmbeddedChunk extends PlanChunk {
	embedding: number[];
	/** Source artifact path and trust boundary used during retrieval. */
	sourcePath?: string;
	trustLevel?: "untrusted-history" | "curated";
	promptInjectionSuspected?: boolean;
	promptInjectionSignals?: string[];
}

// ─── Search types ────────────────────────────────────────────────────

/** Unified search query. */
export interface SearchQuery {
	query: string;
	/** Maximum results per search mode */
	limit?: number;
	/** Filter by plan ID */
	planId?: string;
	/** Filter by entity type */
	entityType?: PlanEntityType;
}

/** A single semantic search hit. */
export interface SemanticHit {
	chunkId: string;
	planId: string;
	section: string;
	text: string;
	score: number;
	/** Score semantics; cosine similarity is not a calibrated hit probability. */
	matchType?: "semantic" | "keyword" | "merged";
	matchedTerms?: string[];
	sourcePlanIds?: string[];
	promptInjectionSuspected?: boolean;
	promptInjectionSignals?: string[];
}

/** Unified search response. */
export interface SearchResponse {
	query: string;
	semantic: SemanticHit[];
	graph: GraphSearchResult[];
}

// ─── Sync types ──────────────────────────────────────────────────────

export interface SyncEvent {
	type: "added" | "modified" | "removed";
	planId: string;
}

export interface SyncStats {
	added: number;
	modified: number;
	removed: number;
	skipped: number;
	errors: string[];
}

// ─── JSON index / cache ───────────────────────────────────────────────

/** Complete in-memory knowledge base state persisted to .kb-index.json. */
export interface KbIndexData {
	/** Persisted schema; upgrades are handled one version at a time. */
	schemaVersion: number;
	plans: KbPlan[];
	entities: PlanEntity[];
	relations: PlanRelation[];
	chunks: EmbeddedChunk[];
	syncState: Record<string, KbSyncState>;
	mergedKnowledge: MergedKnowledgePoint[];
}

export interface KbPlan {
	id: string;
	title: string;
	path: string;
	goal: string;
	resolution: PlanResolution;
	hasReview: boolean;
	reviewers: string[];
	createdAt: string;
	syncedAt: string;
	/** Artifact kind — distinguishes plan vs code-review */
	kind: PlanKind;
}

export interface KbSyncState {
	planMtime: number;
	reviewMtime: number;
	lastSyncedAt: string;
}

export interface KbStats {
	plans: number;
	entities: number;
	relations: number;
	chunks: number;
}

/** A consolidated "project knowledge point" produced by the merge/metabolism layer. */
export interface MergedKnowledgePoint {
	/** Merge output id, regenerated on each merge run */
	id: string;
	/** Human-readable synthesized title */
	title: string;
	/** Number of source chunks merged */
	memberCount: number;
	/** Source plan directory ids */
	planIds: string[];
	/** Source sections (e.g. diff / review_log / approach) */
	sourceSections: string[];
	/** Exact source chunks used to build this canonical view. */
	memberChunkIds: string[];
	/** De-duplicated, joined source text */
	consolidatedText: string;
	/** Lowest pairwise cosine similarity within the merged group */
	minSimilarity: number;
	/** ISO timestamp of the merge run */
	createdAt: string;
}
