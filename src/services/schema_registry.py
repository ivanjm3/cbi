"""Schema Registry for Redshift table metadata.

Maps ontology concept_ids to Redshift table metadata, enabling the SQL Generator
to resolve entity_refs to valid table/column information for query generation.
"""

import logging

from src.models.redshift_models import (
    ColumnClassification,
    ColumnDef,
    FilterMapping,
    TableMapping,
)

logger = logging.getLogger(__name__)

SCHEMA_MAPPINGS: list[TableMapping] = [
    TableMapping(
        concept_id="ontology:sales_transactions",
        table_name="sales_transactions",
        columns=[
            ColumnDef(name="transaction_id", classification=ColumnClassification.IDENTIFIER, sql_type="VARCHAR"),
            ColumnDef(name="transaction_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
            ColumnDef(name="customer_id", classification=ColumnClassification.IDENTIFIER, sql_type="VARCHAR"),
            ColumnDef(name="product_name", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="category", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="region", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="quantity", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="unit_price", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="total_amount", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="payment_method", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
        ],
        filter_mappings=[
            FilterMapping(keyword="category", target_column="category", operator="equals"),
            FilterMapping(keyword="region", target_column="region", operator="equals"),
            FilterMapping(keyword="payment_method", target_column="payment_method", operator="equals"),
            FilterMapping(keyword="product_name", target_column="product_name", operator="like"),
        ],
    ),
    TableMapping(
        concept_id="ontology:customer_segments",
        table_name="customer_segments",
        columns=[
            ColumnDef(name="customer_id", classification=ColumnClassification.IDENTIFIER, sql_type="VARCHAR"),
            ColumnDef(name="customer_name", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="segment", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="lifetime_value", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="signup_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
            ColumnDef(name="region", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="total_orders", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="last_order_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
        ],
        filter_mappings=[
            FilterMapping(keyword="segment", target_column="segment", operator="equals"),
            FilterMapping(keyword="region", target_column="region", operator="equals"),
        ],
    ),
    TableMapping(
        concept_id="ontology:employee_performance",
        table_name="employee_performance",
        columns=[
            ColumnDef(name="employee_id", classification=ColumnClassification.IDENTIFIER, sql_type="VARCHAR"),
            ColumnDef(name="employee_name", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="department", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="role", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="hire_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
            ColumnDef(name="region", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="quarterly_target", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="quarterly_actual", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="deals_closed", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="customer_satisfaction_score", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
        ],
        filter_mappings=[
            FilterMapping(keyword="department", target_column="department", operator="equals"),
            FilterMapping(keyword="region", target_column="region", operator="equals"),
            FilterMapping(keyword="role", target_column="role", operator="equals"),
        ],
    ),
]


class SchemaRegistry:
    """Maps ontology concept_ids to Redshift table metadata.

    Provides resolution of entity_refs to TableMapping objects, column
    classification queries, and validation against a live Redshift cluster.
    """

    def __init__(self) -> None:
        """Initialize the SchemaRegistry with the static SCHEMA_MAPPINGS."""
        self._mappings: list[TableMapping] = SCHEMA_MAPPINGS
        self._by_concept: dict[str, TableMapping] = {
            m.concept_id: m for m in self._mappings
        }
        self._by_table: dict[str, TableMapping] = {
            m.table_name: m for m in self._mappings
        }

    def resolve(self, entity_ref: str) -> TableMapping | None:
        """Resolve an entity_ref to its corresponding TableMapping.

        Args:
            entity_ref: The ontology concept_id (e.g. "ontology:sales_transactions").

        Returns:
            The matching TableMapping, or None if not found.
        """
        return self._by_concept.get(entity_ref)

    def get_numeric_columns(self, table_name: str) -> list[ColumnDef]:
        """Get columns classified as numeric for a given table.

        Args:
            table_name: The Redshift table name.

        Returns:
            List of ColumnDef objects with numeric classification.
            Empty list if the table is not in the registry.
        """
        mapping = self._by_table.get(table_name)
        if mapping is None:
            return []
        return [
            col for col in mapping.columns
            if col.classification == ColumnClassification.NUMERIC
        ]

    def get_categorical_columns(self, table_name: str) -> list[ColumnDef]:
        """Get columns classified as categorical for a given table.

        Args:
            table_name: The Redshift table name.

        Returns:
            List of ColumnDef objects with categorical classification.
            Empty list if the table is not in the registry.
        """
        mapping = self._by_table.get(table_name)
        if mapping is None:
            return []
        return [
            col for col in mapping.columns
            if col.classification == ColumnClassification.CATEGORICAL
        ]

    async def validate_against_redshift(self, connector) -> list[str]:
        """Validate that all mapped tables exist in the configured Redshift database.

        Queries the Redshift information_schema to verify each table in the
        schema mappings exists. Returns the list of valid concept_ids for
        tables that were confirmed to exist.

        Args:
            connector: A RedshiftConnector instance used to execute validation queries.

        Returns:
            List of valid concept_ids whose tables exist in Redshift.
            If a table doesn't exist, logs a warning and excludes that concept.
        """
        valid_concept_ids: list[str] = []

        for mapping in self._mappings:
            sql = (
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :table_name"
            )
            parameters = [{"name": "table_name", "value": mapping.table_name}]

            result = await connector.execute_statement(sql, parameters=parameters)

            # If the result is an error, the table lookup failed
            if hasattr(result, "error_type"):
                logger.warning(
                    "Failed to validate table '%s': %s",
                    mapping.table_name,
                    result.description,
                )
                continue

            # Check if the table was found in the results
            if result.row_count > 0:
                valid_concept_ids.append(mapping.concept_id)
                logger.info(
                    "Validated table '%s' exists for concept '%s'",
                    mapping.table_name,
                    mapping.concept_id,
                )
            else:
                logger.warning(
                    "Table '%s' does not exist in Redshift for concept '%s'",
                    mapping.table_name,
                    mapping.concept_id,
                )

        return valid_concept_ids
