"""SQL Generator for translating StructuredIntent to parameterized SQL.

Resolves entity_refs via the Schema Registry, selects a query strategy based
on query_type, and produces parameterized SQL that is safe from injection.
"""
import logging
from typing import Any

from src.models.redshift_models import (
    ColumnClassification,
    FilterMapping,
    GeneratedQuery,
    SQLGeneratorError,
    TableMapping,
)
from src.models.shared import StructuredIntent
from src.services.schema_registry import SchemaRegistry

logger = logging.getLogger(__name__)

VALID_AGGREGATES = {"SUM", "AVG", "COUNT", "MIN", "MAX"}
DEFAULT_AGGREGATE = "SUM"


class SQLGenerator:
    """Translates StructuredIntent to parameterized SQL via Schema Registry.

    Resolves entity_refs to table/column metadata, selects the appropriate
    query strategy based on query_type, and builds parameterized SQL using
    :param_name placeholders with a parameters list.
    """

    def __init__(self, schema_registry: SchemaRegistry) -> None:
        """Initialize the SQL Generator with a Schema Registry instance.

        Args:
            schema_registry: The SchemaRegistry used to resolve entity_refs.
        """
        self._schema_registry = schema_registry

    def generate(self, intent: StructuredIntent) -> GeneratedQuery | SQLGeneratorError:
        """Generate parameterized SQL from a structured intent.

        Resolves entity_refs via the schema registry. If multiple tables are
        resolved, uses only the first resolved table. If no entity_ref resolves,
        returns an UNRESOLVED_ENTITY error.

        Args:
            intent: The structured intent containing query_type, entity_refs,
                    and routing_metadata.

        Returns:
            A GeneratedQuery on success, or SQLGeneratorError on failure.
        """
        # Resolve entity_refs to table mappings
        resolved: list[tuple[str, TableMapping]] = []
        for ref in intent.entity_refs:
            mapping = self._schema_registry.resolve(ref)
            if mapping is not None:
                resolved.append((ref, mapping))

        # If no entity_ref resolves, return error
        if not resolved:
            return SQLGeneratorError(
                error_type="UNRESOLVED_ENTITY",
                description=f"No entity_refs could be resolved: {intent.entity_refs}",
            )

        # Use only the first resolved table
        first_table = resolved[0][1]

        # For multi-table cases, filter to only entity_refs belonging to first table
        table_refs = [ref for ref, mapping in resolved if mapping.table_name == first_table.table_name]

        logger.info(
            "Resolved %d entity_refs to table '%s' (query_type=%s)",
            len(table_refs),
            first_table.table_name,
            intent.query_type,
        )

        # Select query strategy based on query_type
        if intent.query_type == "lookup":
            return self._generate_lookup(first_table, intent)
        elif intent.query_type == "aggregation":
            return self._generate_aggregation(first_table, intent)
        elif intent.query_type == "comparison":
            return self._generate_comparison(first_table, intent)
        else:
            return SQLGeneratorError(
                error_type="INVALID_QUERY_TYPE",
                description=f"Unsupported query_type: {intent.query_type}",
            )

    def _generate_lookup(
        self, table: TableMapping, intent: StructuredIntent
    ) -> GeneratedQuery:
        """Generate a lookup query: SELECT all columns WHERE filters LIMIT N.

        If target_columns are specified in routing_metadata, only those columns
        are selected (plus all categorical columns for context). Otherwise all
        columns are selected.

        Supports "top N" and "bottom N" queries by detecting superlative keywords
        and adding ORDER BY on the most relevant numeric column.

        Args:
            table: The resolved table mapping.
            intent: The structured intent with routing_metadata filters.

        Returns:
            A GeneratedQuery with parameterized SELECT ... WHERE ... LIMIT N.
        """
        import re

        target_columns: list[str] = intent.routing_metadata.get("target_columns", [])
        query_text = intent.routing_metadata.get("query_text", "").lower()

        # FIX #3: If the NLP extracted specific target columns, honour them.
        # Always include all categorical columns so the rows are identifiable.
        if target_columns:
            categorical_cols = self._schema_registry.get_categorical_columns(table.table_name)
            cat_names = [col.name for col in categorical_cols]
            all_col_names = [col.name for col in table.columns]
            # Columns in declared order: categoricals first, then requested targets
            selected = list(cat_names)
            for tc in target_columns:
                if tc in all_col_names and tc not in selected:
                    selected.append(tc)
            select_clause = ", ".join(selected) if selected else "*"
        else:
            all_columns = [col.name for col in table.columns]
            select_clause = ", ".join(all_columns)

        where_parts, parameters = self._build_where_clause(table, intent)
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # Detect "top N" / "bottom N" patterns for ORDER BY + LIMIT
        order_clause = ""
        limit_val = 1000  # Default
        top_match = re.search(r'\b(top|best|highest|largest|most)\s*(\d+)?\b', query_text)
        bottom_match = re.search(r'\b(bottom|worst|lowest|smallest|least)\s*(\d+)?\b', query_text)

        if top_match or bottom_match:
            # Determine sort direction and limit
            if top_match:
                direction = "DESC"
                n_str = top_match.group(2)
            else:
                direction = "ASC"
                n_str = bottom_match.group(2)
            limit_val = int(n_str) if n_str else 10

            # Determine ORDER BY column — use targeted numeric cols or first numeric
            numeric_cols = self._schema_registry.get_numeric_columns(table.table_name)
            matched_keywords = intent.routing_metadata.get("matched_keywords", [])
            order_col = None

            # Try to find a numeric column mentioned in the query
            for col in numeric_cols:
                if col.name in target_columns or any(kw in col.name for kw in matched_keywords if len(kw) > 3):
                    order_col = col.name
                    break

            if not order_col and numeric_cols:
                order_col = numeric_cols[-1].name  # Last numeric col (often the most meaningful)

            if order_col:
                order_clause = f" ORDER BY {order_col} {direction}"

        sql = f"SELECT {select_clause} FROM {table.table_name}{where_sql}{order_clause} LIMIT {limit_val}"

        return GeneratedQuery(
            sql=sql,
            parameters=parameters,
            table_name=table.table_name,
            query_type="lookup",
        )

    def _generate_aggregation(
        self, table: TableMapping, intent: StructuredIntent
    ) -> GeneratedQuery:
        """Generate an aggregation query, optionally with GROUP BY.

        KEY BEHAVIOUR (fixes #1, #2, #3, #4):
        - If NO group_by_hint is present → pure aggregate with NO GROUP BY.
          e.g. SELECT SUM(spend), SUM(revenue_attributed) FROM marketing_campaigns
        - If group_by_hint IS present → group only by those columns, not ALL
          categoricals.
        - If target_columns are provided → aggregate only those numeric columns,
          not every numeric column in the table.
        - COUNT queries ("how many …") always use COUNT(*) instead of SUM.

        Uses the aggregate function from routing_metadata if specified,
        otherwise defaults to SUM. Valid aggregates: SUM, AVG, COUNT, MIN, MAX.

        Args:
            table: The resolved table mapping.
            intent: The structured intent with routing_metadata.

        Returns:
            A GeneratedQuery with SELECT aggregate(numeric) [GROUP BY categorical].
        """
        numeric_cols = self._schema_registry.get_numeric_columns(table.table_name)
        categorical_cols = self._schema_registry.get_categorical_columns(table.table_name)

        # ── Determine aggregate function ────────────────────────────────────────
        aggregate_fn = intent.routing_metadata.get("aggregate_function", DEFAULT_AGGREGATE)
        if isinstance(aggregate_fn, str):
            aggregate_fn = aggregate_fn.upper()
        if aggregate_fn not in VALID_AGGREGATES:
            aggregate_fn = DEFAULT_AGGREGATE

        query_text = intent.routing_metadata.get("query_text", "").lower()

        # Detect aggregate function from query text when not explicitly provided
        if aggregate_fn == DEFAULT_AGGREGATE:
            if any(kw in query_text for kw in ["average", "avg", "mean"]):
                aggregate_fn = "AVG"
            elif any(kw in query_text for kw in ["minimum", "min", "lowest", "least"]):
                aggregate_fn = "MIN"
            elif any(kw in query_text for kw in ["maximum", "max", "highest", "most", "top"]):
                aggregate_fn = "MAX"

        # ── Detect COUNT intent ─────────────────────────────────────────────────
        is_count_query = any(
            kw in query_text for kw in ["how many", "count", "number of", "total number",
                                        "volume", "headcount", "tally"]
        )

        # ── FIX #1 & #2: Determine GROUP BY columns ─────────────────────────────
        # Only group if the user explicitly hinted at a grouping dimension.
        group_by_hint: list[str] = intent.routing_metadata.get("group_by_hint", [])
        target_columns: list[str] = intent.routing_metadata.get("target_columns", [])
        matched_filter_keywords: list[str] = intent.routing_metadata.get("matched_keywords", [])

        group_cols: list[ColumnClassification] = []  # empty = no GROUP BY

        if group_by_hint:
            # Resolve hinted names to actual categorical ColumnClassification objects
            all_col_names = {col.name for col in table.columns}
            filter_map = {fm.keyword: fm.target_column for fm in table.filter_mappings}

            group_cols = [
                col for col in categorical_cols
                if col.name in group_by_hint or col.name in target_columns
            ]

            if not group_cols:
                # Try filter_mapping keyword → column resolution as a fallback
                resolved_col_names: set[str] = set()
                for hint in group_by_hint:
                    if hint in filter_map:
                        resolved_col_names.add(filter_map[hint])
                    for col_name in all_col_names:
                        if hint in col_name or col_name.replace("is_", "") == hint:
                            resolved_col_names.add(col_name)

                group_cols = [
                    col for col in categorical_cols
                    if col.name in resolved_col_names
                ]

            # FIX #1: If nothing resolved, do NOT fall back to ALL categoricals.
            # Leave group_cols empty so we get a pure aggregate (no GROUP BY).

        # ── FIX #3: Determine which numeric columns to aggregate ────────────────
        target_numeric_cols = numeric_cols
        if target_columns or matched_filter_keywords:
            all_mentioned = set(target_columns + matched_filter_keywords)
            targeted = [
                col for col in numeric_cols
                if col.name in all_mentioned
                or col.name.replace("_", " ") in all_mentioned
                or any(kw in col.name for kw in all_mentioned if len(kw) > 3)
            ]
            if targeted:
                target_numeric_cols = targeted

        # ── Build SELECT clause ─────────────────────────────────────────────────
        select_parts: list[str] = [col.name for col in group_cols]

        if is_count_query:
            select_parts.append("COUNT(*)")
        else:
            for col in target_numeric_cols:
                alias = f"{aggregate_fn.lower()}_{col.name}"
                # BOOLEAN columns can't be CAST to INT in Redshift —
                # use CASE WHEN col THEN 1 ELSE 0 END instead
                if col.sql_type == "BOOLEAN":
                    col_expr = f"CASE WHEN {col.name} THEN 1 ELSE 0 END"
                else:
                    col_expr = col.name
                select_parts.append(f"{aggregate_fn}({col_expr}) AS {alias}")

        select_clause = ", ".join(select_parts) if select_parts else "COUNT(*)"

        # ── Build WHERE clause ──────────────────────────────────────────────────
        where_parts, parameters = self._build_where_clause(table, intent)
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # ── FIX #2: Only emit GROUP BY when there are actual grouping columns ───
        if group_cols:
            group_by_clause = ", ".join(col.name for col in group_cols)
            sql = (
                f"SELECT {select_clause} FROM {table.table_name}"
                f"{where_sql} GROUP BY {group_by_clause}"
            )
        else:
            # Pure aggregate — no GROUP BY
            sql = f"SELECT {select_clause} FROM {table.table_name}{where_sql}"

        return GeneratedQuery(
            sql=sql,
            parameters=parameters,
            table_name=table.table_name,
            query_type="aggregation",
        )

    def _generate_comparison(
        self, table: TableMapping, intent: StructuredIntent
    ) -> GeneratedQuery:
        """Generate a comparison query grouped by a relevant categorical column.

        When routing_metadata contains 'group_by_hint', uses the hinted column
        as the comparison dimension. Otherwise falls back to the first categorical
        column.

        Produces SELECT comparison_col, AGG(numeric_cols)
        GROUP BY comparison_col.

        Uses the aggregate_function from routing_metadata if specified (AVG, SUM, etc.),
        otherwise defaults to AVG for comparison queries (comparing averages is more
        common than comparing totals).

        Args:
            table: The resolved table mapping.
            intent: The structured intent with routing_metadata.

        Returns:
            A GeneratedQuery with comparison structure.
        """
        numeric_cols = self._schema_registry.get_numeric_columns(table.table_name)
        categorical_cols = self._schema_registry.get_categorical_columns(table.table_name)

        group_by_hint: list[str] = intent.routing_metadata.get("group_by_hint", [])
        target_columns: list[str] = intent.routing_metadata.get("target_columns", [])

        # Determine aggregate function — prefer AVG for comparisons unless specified
        aggregate_fn = intent.routing_metadata.get("aggregate_function", "AVG")
        if isinstance(aggregate_fn, str):
            aggregate_fn = aggregate_fn.upper()
        if aggregate_fn not in VALID_AGGREGATES:
            aggregate_fn = "AVG"

        # Detect aggregate function from query text
        query_text = intent.routing_metadata.get("query_text", "").lower()
        if any(kw in query_text for kw in ["total", "sum"]):
            aggregate_fn = "SUM"
        elif any(kw in query_text for kw in ["count", "how many", "number of"]):
            aggregate_fn = "COUNT"

        # Determine comparison dimension
        first_categorical: str | None = None
        if group_by_hint or target_columns:
            hints = group_by_hint or target_columns
            filter_map = {fm.keyword: fm.target_column for fm in table.filter_mappings}
            for hint in hints:
                for col in categorical_cols:
                    if col.name == hint or col.name.replace("is_", "") == hint:
                        first_categorical = col.name
                        break
                if first_categorical:
                    break
                if hint in filter_map:
                    first_categorical = filter_map[hint]
                    break

        if not first_categorical:
            first_categorical = categorical_cols[0].name if categorical_cols else None

        # Detect COUNT intent — but not if the query is asking about a numeric metric
        # e.g. "salary distribution" should not trigger COUNT; "ticket distribution" should.
        has_numeric_target = bool(target_columns or intent.routing_metadata.get("matched_keywords", []))
        is_count_query = any(
            kw in query_text for kw in ["how many", "number of", "total number",
                                        "volume", "headcount", "tally"]
        )
        if not has_numeric_target:
            if any(kw in query_text for kw in ["count", "distribution"]):
                is_count_query = True

        # FIX #3: Respect target_columns for numeric aggregation in comparisons too
        matched_filter_keywords: list[str] = intent.routing_metadata.get("matched_keywords", [])
        target_numeric_cols = numeric_cols
        if target_columns or matched_filter_keywords:
            all_mentioned = set(target_columns + matched_filter_keywords)
            targeted = [
                col for col in numeric_cols
                if col.name in all_mentioned
                or col.name.replace("_", " ") in all_mentioned
                or any(kw in col.name for kw in all_mentioned if len(kw) > 3)
            ]
            if targeted:
                target_numeric_cols = targeted

        # Build SELECT clause
        select_parts: list[str] = []
        if first_categorical:
            select_parts.append(first_categorical)

        if is_count_query:
            select_parts.append("COUNT(*)")
        else:
            for col in target_numeric_cols:
                alias = f"{aggregate_fn.lower()}_{col.name}"
                # BOOLEAN columns can't be CAST to INT in Redshift —
                # use CASE WHEN col THEN 1 ELSE 0 END instead
                if col.sql_type == "BOOLEAN":
                    col_expr = f"CASE WHEN {col.name} THEN 1 ELSE 0 END"
                else:
                    col_expr = col.name
                select_parts.append(f"{aggregate_fn}({col_expr}) AS {alias}")

        select_clause = ", ".join(select_parts)

        # Build WHERE clause
        where_parts, parameters = self._build_where_clause(table, intent)
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

        if first_categorical:
            sql = (
                f"SELECT {select_clause} FROM {table.table_name}"
                f"{where_sql} GROUP BY {first_categorical}"
            )
        else:
            # Edge case: no categorical columns — just aggregate
            sql = f"SELECT {select_clause} FROM {table.table_name}{where_sql}"

        return GeneratedQuery(
            sql=sql,
            parameters=parameters,
            table_name=table.table_name,
            query_type="comparison",
        )

    def _build_where_clause(
        self, table: TableMapping, intent: StructuredIntent
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Build parameterized WHERE clause conditions from routing_metadata filters.

        Maps filter keywords from routing_metadata to table columns via
        the table's filter_mappings. All values use :param_name placeholders.

        Args:
            table: The table mapping with filter_mappings.
            intent: The intent containing routing_metadata with filters.

        Returns:
            A tuple of (where_clause_parts, parameters) where parameters is
            a list of {"name": param_name, "value": value} dicts.
        """
        filters: dict[str, Any] = intent.routing_metadata.get("filters", {})
        where_parts: list[str] = []
        parameters: list[dict[str, Any]] = []

        # Build a lookup from keyword to FilterMapping
        filter_map: dict[str, FilterMapping] = {
            fm.keyword: fm for fm in table.filter_mappings
        }

        param_index = 0
        for keyword, value in filters.items():
            mapping = filter_map.get(keyword)
            if mapping is None:
                # Skip filters that don't have a mapping in this table
                continue

            param_name = f"param_{param_index}"
            param_index += 1
            condition = self._build_condition(mapping, param_name)
            where_parts.append(condition)
            parameters.append({"name": param_name, "value": value})

        return where_parts, parameters

    def _build_condition(self, mapping: FilterMapping, param_name: str) -> str:
        """Build a single WHERE condition based on the filter operator.

        Args:
            mapping: The filter mapping defining column and operator.
            param_name: The parameter placeholder name.

        Returns:
            A SQL condition string using :param_name placeholder.
        """
        column = mapping.target_column
        operator = mapping.operator

        if operator == "equals":
            return f"{column} = :{param_name}"
        elif operator == "like":
            return f"{column} LIKE :{param_name}"
        elif operator == "in":
            return f"{column} IN (:{param_name})"
        elif operator == "greater_than":
            return f"{column} > :{param_name}"
        elif operator == "less_than":
            return f"{column} < :{param_name}"
        elif operator == "between":
            return f"{column} BETWEEN :{param_name}_start AND :{param_name}_end"
        else:
            # Fallback to equals for unknown operators
            return f"{column} = :{param_name}"