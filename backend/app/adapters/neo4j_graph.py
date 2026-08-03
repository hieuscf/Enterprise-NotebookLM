# =============================================================================
# File: neo4j_graph.py
# Module/Service: Pipeline Worker / LightRAG Low-Level Graph / Hybrid Retrieval
# Layer: Adapter
# Purpose: Neo4j writer + entity/chunk graph reader for Low-Level Retrieval (FR2/FR3).
# Responsibilities:
#   - Upsert Entity nodes, RELATES_TO edges, optional Chunk + MENTIONED_IN
#   - Search entities by name/alias scoped by workspace_id
# Dependencies:
#   - neo4j driver, app.core.config.Settings
# Public Exports:
#   - Neo4jGraphAdapter, get_neo4j_graph
# Database/Table: entities, entity_relations (Postgres is source of truth; Neo4j mirror)
# Related Modules: app.ai.graph_extraction, app.services.retrieval.graph_search
# Important Notes: Non-LLM graph I/O; Postgres remains canonical for entity rows.
# =============================================================================

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from neo4j import GraphDatabase

from app.core.config import Settings, get_settings


class Neo4jGraphAdapter:
    def __init__(self, settings: Settings) -> None:
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        self._driver.close()

    def upsert_entities_and_relations(
        self,
        *,
        workspace_id: UUID,
        source_version_id: UUID,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        mentions: list[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert entities/relations and optional ``(Entity)-[:MENTIONED_IN]->(Chunk)``.

        Args:
            mentions: Optional list of
                ``{entity_id, chunk_id, document_id, content, aliases?}``.
        """
        with self._driver.session() as session:
            session.execute_write(
                self._write_graph,
                str(workspace_id),
                str(source_version_id),
                entities,
                relations,
                mentions or [],
            )

    def search_entities_with_chunks(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Match entities by name/alias; return linked chunks via MENTIONED_IN.

        Returns:
            Rows with ``entity_id``, ``entity_name``, ``source_version_id``,
            ``chunk_id`` (nullable), ``document_id`` (nullable), ``content``, ``score``.
        """
        q = (query_text or "").strip()
        if not q:
            return []
        with self._driver.session() as session:
            return list(
                session.execute_read(
                    self._read_entities,
                    str(workspace_id),
                    q,
                    max(1, top_k),
                )
            )

    def expand_related_entities(
        self,
        *,
        workspace_id: UUID,
        seed_entity_ids: list[str],
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """Expand seed entities via ``RELATES_TO`` (1–2 hops) + ``MENTIONED_IN`` docs.

        Returns:
            Rows with ``entity_id``, ``document_id`` (nullable), ``hops``.
            Empty list on empty seeds. Caps ``max_hops`` at 2.
        """
        seeds = [str(eid) for eid in seed_entity_ids if eid]
        if not seeds:
            return []
        hops = max(1, min(2, int(max_hops)))
        with self._driver.session() as session:
            return list(
                session.execute_read(
                    self._expand_entities,
                    str(workspace_id),
                    seeds,
                    hops,
                )
            )

    @staticmethod
    def _write_graph(
        tx: Any,
        workspace_id: str,
        source_version_id: str,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        mentions: list[dict[str, Any]],
    ) -> None:
        for ent in entities:
            aliases = ent.get("aliases") or []
            tx.run(
                """
                MERGE (e:Entity {id: $id})
                SET e.name = $name,
                    e.type = $type,
                    e.description = $description,
                    e.aliases = $aliases,
                    e.workspace_id = $workspace_id,
                    e.source_version_id = $source_version_id
                """,
                id=ent["id"],
                name=ent["name"],
                type=ent["type"],
                description=ent.get("description"),
                aliases=list(aliases),
                workspace_id=workspace_id,
                source_version_id=source_version_id,
            )
        for rel in relations:
            tx.run(
                """
                MATCH (a:Entity {id: $source_id})
                MATCH (b:Entity {id: $target_id})
                MERGE (a)-[r:RELATES_TO {id: $id}]->(b)
                SET r.relation_type = $relation_type,
                    r.description = $description,
                    r.weight = $weight
                """,
                id=rel["id"],
                source_id=rel["source_entity_id"],
                target_id=rel["target_entity_id"],
                relation_type=rel["relation_type"],
                description=rel.get("description"),
                weight=rel.get("weight"),
            )
        for mention in mentions:
            tx.run(
                """
                MATCH (e:Entity {id: $entity_id})
                MERGE (c:Chunk {id: $chunk_id})
                SET c.document_id = $document_id,
                    c.document_version_id = $document_version_id,
                    c.workspace_id = $workspace_id,
                    c.content = $content
                MERGE (e)-[:MENTIONED_IN]->(c)
                """,
                entity_id=mention["entity_id"],
                chunk_id=mention["chunk_id"],
                document_id=mention.get("document_id"),
                document_version_id=mention.get("document_version_id"),
                workspace_id=workspace_id,
                content=(mention.get("content") or "")[:2000],
            )

    @staticmethod
    def _read_entities(
        tx: Any,
        workspace_id: str,
        query_text: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        result = tx.run(
            """
            MATCH (e:Entity)
            WHERE e.workspace_id = $workspace_id
              AND (
                toLower(e.name) CONTAINS toLower($query_text)
                OR any(
                  a IN coalesce(e.aliases, [])
                  WHERE toLower(a) CONTAINS toLower($query_text)
                )
              )
            OPTIONAL MATCH (e)-[:MENTIONED_IN]->(c:Chunk)
            WHERE c IS NULL OR c.workspace_id = $workspace_id
            RETURN e.id AS entity_id,
                   e.name AS entity_name,
                   e.source_version_id AS source_version_id,
                   c.id AS chunk_id,
                   c.document_id AS document_id,
                   c.content AS content,
                   CASE
                     WHEN toLower(e.name) = toLower($query_text) THEN 1.0
                     WHEN toLower(e.name) CONTAINS toLower($query_text) THEN 0.85
                     ELSE 0.7
                   END AS score
            ORDER BY score DESC
            LIMIT $top_k
            """,
            workspace_id=workspace_id,
            query_text=query_text,
            top_k=top_k,
        )
        rows: list[dict[str, Any]] = []
        for record in result:
            rows.append(
                {
                    "entity_id": record["entity_id"],
                    "entity_name": record["entity_name"],
                    "source_version_id": record["source_version_id"],
                    "chunk_id": record["chunk_id"],
                    "document_id": record["document_id"],
                    "content": record["content"] or "",
                    "score": float(record["score"] or 0.0),
                }
            )
        return rows

    @staticmethod
    def _expand_entities(
        tx: Any,
        workspace_id: str,
        seed_entity_ids: list[str],
        max_hops: int,
    ) -> list[dict[str, Any]]:
        """Traverse RELATES_TO up to ``max_hops`` and collect related docs."""
        result = tx.run(
            """
            MATCH (seed:Entity)
            WHERE seed.workspace_id = $workspace_id
              AND seed.id IN $seed_ids
            MATCH path = (seed)-[:RELATES_TO*1..2]-(related:Entity)
            WHERE related.workspace_id = $workspace_id
              AND length(path) <= $max_hops
            WITH related, min(length(path)) AS hops
            OPTIONAL MATCH (related)-[:MENTIONED_IN]->(c:Chunk)
            WHERE c IS NULL OR c.workspace_id = $workspace_id
            RETURN DISTINCT related.id AS entity_id,
                   c.document_id AS document_id,
                   hops
            LIMIT 200
            """,
            workspace_id=workspace_id,
            seed_ids=seed_entity_ids,
            max_hops=max_hops,
        )
        rows: list[dict[str, Any]] = []
        for record in result:
            rows.append(
                {
                    "entity_id": record["entity_id"],
                    "document_id": record["document_id"],
                    "hops": int(record["hops"] or 1),
                }
            )
        return rows


@lru_cache
def get_neo4j_graph() -> Neo4jGraphAdapter:
    return Neo4jGraphAdapter(get_settings())
