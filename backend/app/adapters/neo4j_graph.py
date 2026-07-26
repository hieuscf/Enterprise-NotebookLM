# =============================================================================
# File: neo4j_graph.py
# Module/Service: Pipeline Worker / LightRAG Low-Level Graph
# Layer: Adapter
# Purpose: Neo4j writer for entities and relations extracted in graph_extraction.
# Responsibilities:
#   - Upsert Entity nodes and RELATES_TO edges scoped by workspace/version
# Dependencies:
#   - neo4j driver, app.core.config.Settings
# Public Exports:
#   - Neo4jGraphAdapter, get_neo4j_graph
# Database/Table: entities, entity_relations (Postgres is source of truth; Neo4j mirror)
# Related Modules: app.ai.graph_extraction, app.workers.pipeline
# Important Notes: Non-LLM graph write from Celery; Postgres remains canonical.
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
    ) -> None:
        with self._driver.session() as session:
            session.execute_write(
                self._write_graph,
                str(workspace_id),
                str(source_version_id),
                entities,
                relations,
            )

    @staticmethod
    def _write_graph(
        tx: Any,
        workspace_id: str,
        source_version_id: str,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> None:
        for ent in entities:
            tx.run(
                """
                MERGE (e:Entity {id: $id})
                SET e.name = $name,
                    e.type = $type,
                    e.description = $description,
                    e.workspace_id = $workspace_id,
                    e.source_version_id = $source_version_id
                """,
                id=ent["id"],
                name=ent["name"],
                type=ent["type"],
                description=ent.get("description"),
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


@lru_cache
def get_neo4j_graph() -> Neo4jGraphAdapter:
    return Neo4jGraphAdapter(get_settings())
