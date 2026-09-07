/**
 * Unified search entry point for the plan-reviews knowledge base.
 *
 * Combines two search modes:
 *   1. Semantic search — vector similarity over embedded plan chunks
 *   2. Graph search — structured entity/relationship traversal
 *
 * Operates entirely in-process; all data comes from the in-memory PlanStore.
 */

import type { PlanStore } from "./store.js";
import type { EmbeddingService } from "./embed.js";
import type { VectorIndex } from "./vector.js";
import type {
	SearchQuery,
	SearchResponse,
	SemanticHit,
	GraphSearchResult,
	PlanEntity,
	PlanRelation,
	PlanEntityType,
} from "./types.js";

export class SearchEngine {
	private store: PlanStore;
	private embed: EmbeddingService;
	private vector: VectorIndex;

	constructor(store: PlanStore, embed: EmbeddingService, vector: VectorIndex) {
		this.store = store;
		this.embed = embed;
		this.vector = vector;
	}

	async search(query: SearchQuery): Promise<SearchResponse> {
		const [semantic, graph] = await Promise.all([
			this.semanticSearch(query),
			this.graphSearch(query),
		]);
		return { query: query.query, semantic: this.collapseMergedHits(semantic), graph };
	}

	async semanticSearch(query: SearchQuery): Promise<SemanticHit[]> {
		if (!this.embed.isAvailable || this.vector.size === 0) {
			return this.keywordSearch(query);
		}

		try {
			const queryVector = await this.embed.embed(query.query);
			return this.vector.search(queryVector, {
				limit: query.limit ?? 5,
				planId: query.planId,
				scoreThreshold: 0.35,
			}).map((hit) => {
				const chunk = this.store.getChunk(hit.chunkId);
				return { ...hit, matchType: "semantic" as const, promptInjectionSuspected: chunk?.promptInjectionSuspected, promptInjectionSignals: chunk?.promptInjectionSignals };
			});
		} catch (err) {
			console.warn(`[plan-reviews] Semantic search failed: ${(err as Error).message}`);
			return this.keywordSearch(query);
		}
	}

	keywordSearch(query: SearchQuery): SemanticHit[] {
		return this.store.searchChunksTextScored(query.query, {
			limit: query.limit ?? 5,
			planId: query.planId,
		}).map(({ chunk, score, matchedTerms }) => ({
			chunkId: chunk.id,
			planId: chunk.planId,
			section: chunk.section,
			text: chunk.text,
			score,
			matchType: "keyword" as const,
			matchedTerms,
			promptInjectionSuspected: chunk.promptInjectionSuspected,
			promptInjectionSignals: chunk.promptInjectionSignals,
		}));
	}

	private collapseMergedHits(hits: SemanticHit[]): SemanticHit[] {
		const points = this.store.getMergedKnowledge();
		const matchedPoints = points.filter((point) =>
			point.memberChunkIds.some((id) => hits.some((hit) => hit.chunkId === id)),
		);
		if (matchedPoints.length === 0) return hits;

		const consumedPlans = new Set(matchedPoints.flatMap((point) => point.planIds));
		const mergedHits = matchedPoints.map((point) => {
			const memberHits = hits.filter((hit) => point.memberChunkIds.includes(hit.chunkId));
			return {
				chunkId: point.id,
				planId: point.planIds[0] ?? "",
				section: "merged",
				text: point.consolidatedText,
				score: Math.max(...memberHits.map((hit) => hit.score)),
				matchType: "merged" as const,
				sourcePlanIds: point.planIds,
				promptInjectionSuspected: memberHits.some((hit) => hit.promptInjectionSuspected),
				promptInjectionSignals: [...new Set(memberHits.flatMap((hit) => hit.promptInjectionSignals ?? []))],
			};
		});
		return [...mergedHits, ...hits.filter((hit) => !consumedPlans.has(hit.planId))];
	}

	async graphSearch(query: SearchQuery): Promise<GraphSearchResult[]> {
		const matchedEntities = this.store.searchEntities(query.query, {
			limit: query.limit ?? 5,
			entityType: query.entityType,
			planId: query.planId,
		});

		if (matchedEntities.length === 0) return [];

		const entityIds = matchedEntities.map((e) => e.id);
		const { entities, edges } = this.store.getSubgraph(entityIds);

		const entityMap = new Map<string, PlanEntity>();
		for (const e of entities) {
			entityMap.set(e.id, e);
		}

		return matchedEntities.map((matchedEntity) => {
			entityMap.set(matchedEntity.id, matchedEntity);

			const matchedRelations = edges
				.filter(
					(edge) =>
						edge.fromEntityId === matchedEntity.id ||
						edge.toEntityId === matchedEntity.id,
				)
				.map((edge) => ({
					relation: edge,
					fromEntity:
						entityMap.get(edge.fromEntityId) ??
						placeholderEntity(edge.fromEntityId),
					toEntity:
						entityMap.get(edge.toEntityId) ??
						placeholderEntity(edge.toEntityId),
				}));

			return { entity: matchedEntity, relations: matchedRelations };
		});
	}

	formatResults(response: SearchResponse): string {
		const lines: string[] = [];

		if (response.semantic.length > 0) {
			lines.push("## Semantic Search Results");
			for (const hit of response.semantic) {
				const planLabel =
					hit.planId !== "" ? ` [${hit.planId}:${hit.section}]` : "";
				const scoreLabel = hit.matchType === "semantic"
					? `(cosine=${hit.score.toFixed(2)})`
					: hit.matchType === "merged"
						? `(merged-score=${hit.score.toFixed(2)}, sources=${hit.sourcePlanIds?.join(",") ?? ""})`
						: `(lexical=${hit.score.toFixed(2)})`;
				const trustLabel = hit.promptInjectionSuspected ? ` [PROMPT-INJECTION-SUSPECTED:${hit.promptInjectionSignals?.join(",")}]` : " [UNTRUSTED-HISTORY]";
				const kindLabel = this.store.getPlan(hit.planId)?.kind === "checkpoint"
					? " [进行中 checkpoint]"
					: "";
				lines.push(`- ${scoreLabel}${planLabel}${kindLabel}${trustLabel}: ${truncate(hit.text, 200)}`);
			}
			lines.push("");
		}

		if (response.graph.length > 0) {
			lines.push("## Entity Graph Results");
			const seenRelations = new Set<string>();

			for (const r of response.graph) {
				const graphKindLabel = this.store.getPlan(r.entity.planId)?.kind === "checkpoint"
					? " [checkpoint]"
					: "";
				lines.push(
					`### [${r.entity.type}] ${r.entity.name} (plan: ${r.entity.planId}${graphKindLabel})`,
				);
				if (r.entity.description) {
					lines.push(`  ${truncate(r.entity.description, 150)}`);
				}

				for (const rel of r.relations) {
					const key = `${rel.relation.id}`;
					if (seenRelations.has(key)) continue;
					seenRelations.add(key);

					const direction =
						rel.relation.fromEntityId === r.entity.id ? "→" : "←";
					const otherEntity =
						rel.relation.fromEntityId === r.entity.id
							? rel.toEntity
							: rel.fromEntity;
					lines.push(
						`  ${direction} [${rel.relation.relation}] → [${otherEntity.type}] ${otherEntity.name}`,
					);
				}
				lines.push("");
			}
		}

		if (response.semantic.length === 0 && response.graph.length === 0) {
			lines.push("No results found.");
		}

		return lines.join("\n");
	}
}

function placeholderEntity(id: string): PlanEntity {
	return {
		id,
		planId: "unknown",
		type: "technology",
		name: id,
		description: "",
		properties: {},
		createdAt: "",
	};
}

function truncate(text: string, maxLen: number): string {
	return text.length > maxLen ? text.slice(0, maxLen) + "..." : text;
}
