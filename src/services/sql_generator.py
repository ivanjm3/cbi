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
        # (all resolved refs pointing to the same table)
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
        """Generate a lookup query: SELECT all columns WHERE filters LIMIT 1000.

        Args:
            table: The resolved table mapping.
            intent: The structured intent with routing_metadata filters.

        Returns:
            A GeneratedQuery with parameterized SELECT ... WHERE ... LIMIT 1000.
        """
        all_columns = [col.name for col in table.columns]
        select_clause = ", ".join(all_columns)

        where_parts, parameters = self._build_where_clause(table, intent)

        if where_parts:
            sql = f"SELECT {select_clause} FROM {table.table_name} WHERE {' AND '.join(where_parts)} LIMIT 1000"
        else:
            sql = f"SELECT {select_clause} FROM {table.table_name} LIMIT 1000"

        return GeneratedQuery(
            sql=sql,
            parameters=parameters,
            table_name=table.table_name,
            query_type="lookup",
        )

    def _generate_aggregation(
        self, table: TableMapping, intent: StructuredIntent
    ) -> GeneratedQuery:
        """Generate an aggregation query with GROUP BY categorical columns.

        Uses the aggregate function from routing_metadata if specified,
        otherwise defaults to SUM. Valid aggregates: SUM, AVG, COUNT, MIN, MAX.

        When routing_metadata contains 'group_by_hint' (column names the user
        mentioned), the query groups by those specific columns instead of all
        categorical columns. This produces focused results matching user intent.

        Args:
            table: The resolved table mapping.
            intent: The structured intent with routing_metadata.

        Returns:
            A GeneratedQuery with SELECT aggregate(numeric) GROUP BY categorical.
        """
        numeric_cols = self._schema_registry.get_numeric_columns(table.table_name)
        categorical_cols = self._schema_registry.get_categorical_columns(table.table_name)

        # Determine aggregate function
        aggregate_fn = intent.routing_metadata.get("aggregate_function", DEFAULT_AGGREGATE)
        if isinstance(aggregate_fn, str):
            aggregate_fn = aggregate_fn.upper()
        if aggregate_fn not in VALID_AGGREGATES:
            aggregate_fn = DEFAULT_AGGREGATE

        # Detect aggregate function from query text if not explicitly provided
        query_text = intent.routing_metadata.get("query_text", "").lower()
        if aggregate_fn == DEFAULT_AGGREGATE:
            # Check for explicit aggregate keywords in the query
            if any(kw in query_text for kw in ["average", "avg", "mean"]):
                aggregate_fn = "AVG"
            elif any(kw in query_text for kw in ["minimum", "min", "lowest", "least"]):
                aggregate_fn = "MIN"
            elif any(kw in query_text for kw in ["maximum", "max", "highest", "most", "top"]):
                aggregate_fn = "MAX"

        # Check for group_by_hint — user mentioned specific columns
        group_by_hint = intent.routing_metadata.get("group_by_hint", [])
        target_columns = intent.routing_metadata.get("target_columns", [])
        matched_filter_keywords = intent.routing_metadata.get("matched_keywords", [])

        # Determine which categorical columns to GROUP BY
        if group_by_hint:
            # Use only the columns the user mentioned
            all_col_names = {col.name for col in table.columns}
            group_cols = [
                col for col in categorical_cols
                if col.name in group_by_hint or col.name in target_columns
            ]
            # Fallback: if hint doesn't match any categorical columns, check
            # filter_mappings for keyword→column resolution
            if not group_cols:
                filter_map = {fm.keyword: fm.target_column for fm in table.filter_mappings}
                resolved_col_names = set()
                for hint in group_by_hint:
                    if hint in filter_map:
                        resolved_col_names.add(filter_map[hint])
                    # Also check if hint matches a column name directly
                    for col_name in all_col_names:
                        if hint in col_name or col_name.replace("is_", "") == hint:
                            resolved_col_names.add(col_name)
                group_cols = [
                    col for col in categorical_cols
                    if col.name in resolved_col_names
                ]
            # If still nothing resolved, fall back to all categorical columns
            if not group_cols:
                group_cols = categorical_cols
        else:
            group_cols = categorical_cols

        # Determine if this is a COUNT query (e.g., "how many employees are remote")
        query_text = intent.routing_metadata.get("query_text", "").lower()
        is_count_query = any(
            kw in query_text for kw in ["how many", "count", "number of", "total number"]
        )

        # Build SELECT clause
        select_parts: list[str] = []
        for col in group_cols:
            select_parts.append(col.name)

        if is_count_query:
            # For "how many" queries, use COUNT(*) instead of aggregating all numeric columns
            select_parts.append("COUNT(*)")
        else:
            # Determine which numeric columns to aggregate
            # If the user mentioned specific metrics, only aggregate those
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

            for col in target_numeric_cols:
                select_parts.append(f"{aggregate_fn}({col.name})")

        select_clause = ", ".join(select_parts)

        # GROUP BY the selected categorical columns
        group_by_clause = ", ".join(col.name for col in group_cols)

        # Build WHERE clause from filters
        where_parts, parameters = self._build_where_clause(table, intent)

        if where_parts:
            sql = f"SELECT {select_clause} FROM {table.table_name} WHERE {' AND '.join(where_parts)} GROUP BY {group_by_clause}"
        else:
            sql = f"SELECT {select_clause} FROM {table.table_name} GROUP BY {group_by_clause}"

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

        Produces SELECT comparison_col, COUNT(*) or SUM(numeric_cols) GROUP BY comparison_col.

        Args:
            table: The resolved table mapping.
            intent: The structured intent with routing_metadata.

        Returns:
            A GeneratedQuery with comparison structure.
        """
        numeric_cols = self._schema_registry.get_numeric_columns(table.table_name)
        categorical_cols = self._schema_registry.get_categorical_columns(table.table_name)

        # Determine comparison dimension from group_by_hint or fallback to first categorical
        group_by_hint = intent.routing_metadata.get("group_by_hint", [])
        target_columns = intent.routing_metadata.get("target_columns", [])

        first_categorical = None
        if group_by_hint or target_columns:
            # Try to find a categorical column matching the hint
            hints = group_by_hint or target_columns
            filter_map = {fm.keyword: fm.target_column for fm in table.filter_mappings}
            for hint in hints:
                # Direct column name match
                for col in categorical_cols:
                    if col.name == hint or col.name.replace("is_", "") == hint:
                        first_categorical = col.name
                        break
                if first_categorical:
                    break
                # Filter mapping keyword match
                if hint in filter_map:
                    first_categorical = filter_map[hint]
                    break

        if not first_categorical:
            first_categorical = categorical_cols[0].name if categorical_cols else None

        # Determine if this is a COUNT query
        query_text = intent.routing_metadata.get("query_text", "").lower()
        is_count_query = any(
            kw in query_text for kw in ["how many", "count", "number of", "total number"]
        )

        # Build SELECT clause
        select_parts: list[str] = []
        if first_categorical:
            select_parts.append(first_categorical)

        if is_count_query:
            select_parts.append("COUNT(*)")
        else:
            for col in numeric_cols:
                select_parts.append(f"SUM({col.name})")

        select_clause = ", ".join(select_parts)

        # Build WHERE clause from filters
        where_parts, parameters = self._build_where_clause(table, intent)

        # GROUP BY first categorical column
        if first_categorical:
            if where_parts:
                sql = f"SELECT {select_clause} FROM {table.table_name} WHERE {' AND '.join(where_parts)} GROUP BY {first_categorical}"
            else:
                sql = f"SELECT {select_clause} FROM {table.table_name} GROUP BY {first_categorical}"
        else:
            # Edge case: no categorical columns - just aggregate
            if where_parts:
                sql = f"SELECT {select_clause} FROM {table.table_name} WHERE {' AND '.join(where_parts)}"
            else:
                sql = f"SELECT {select_clause} FROM {table.table_name}"

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
