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
        concept_id="ontology:workforce_metrics",
        table_name="workforce_metrics",
        columns=[
            ColumnDef(name="employee_id", classification=ColumnClassification.IDENTIFIER, sql_type="VARCHAR"),
            ColumnDef(name="employee_name", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="department", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="job_level", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="hire_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
            ColumnDef(name="office_location", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="base_salary", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="bonus_pct", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="utilization_rate", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="training_hours", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="certifications", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="engagement_score", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="is_remote", classification=ColumnClassification.CATEGORICAL, sql_type="BOOLEAN"),
        ],
        filter_mappings=[
            FilterMapping(keyword="department", target_column="department", operator="equals"),
            FilterMapping(keyword="departments", target_column="department", operator="equals"),
            FilterMapping(keyword="job_level", target_column="job_level", operator="equals"),
            FilterMapping(keyword="level", target_column="job_level", operator="equals"),
            FilterMapping(keyword="office_location", target_column="office_location", operator="equals"),
            FilterMapping(keyword="location", target_column="office_location", operator="equals"),
            FilterMapping(keyword="remote", target_column="is_remote", operator="equals"),
            FilterMapping(keyword="in-office", target_column="is_remote", operator="equals"),
            FilterMapping(keyword="bonus", target_column="bonus_pct", operator="equals"),
            FilterMapping(keyword="bonus percentage", target_column="bonus_pct", operator="equals"),
            FilterMapping(keyword="bonus pct", target_column="bonus_pct", operator="equals"),
            FilterMapping(keyword="bonus_pct", target_column="bonus_pct", operator="equals"),
            FilterMapping(keyword="salary", target_column="base_salary", operator="equals"),
        ],
    ),
    TableMapping(
        concept_id="ontology:support_tickets",
        table_name="support_tickets",
        columns=[
            ColumnDef(name="ticket_id", classification=ColumnClassification.IDENTIFIER, sql_type="VARCHAR"),
            ColumnDef(name="created_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
            ColumnDef(name="resolved_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
            ColumnDef(name="customer_tier", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="channel", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="priority", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="issue_category", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="assigned_team", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="resolution_hours", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="satisfaction_rating", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="escalated", classification=ColumnClassification.NUMERIC, sql_type="BOOLEAN"),
            ColumnDef(name="first_contact_resolution", classification=ColumnClassification.NUMERIC, sql_type="BOOLEAN"),
        ],
        filter_mappings=[
            FilterMapping(keyword="customer_tier", target_column="customer_tier", operator="equals"),
            FilterMapping(keyword="tier", target_column="customer_tier", operator="equals"),
            FilterMapping(keyword="enterprise", target_column="customer_tier", operator="equals"),
            FilterMapping(keyword="free", target_column="customer_tier", operator="equals"),
            FilterMapping(keyword="channel", target_column="channel", operator="equals"),
            FilterMapping(keyword="support channel", target_column="channel", operator="equals"),
            FilterMapping(keyword="priority", target_column="priority", operator="equals"),
            FilterMapping(keyword="issue_category", target_column="issue_category", operator="equals"),
            FilterMapping(keyword="category", target_column="issue_category", operator="equals"),
            FilterMapping(keyword="assigned_team", target_column="assigned_team", operator="equals"),
            FilterMapping(keyword="team", target_column="assigned_team", operator="equals"),
            FilterMapping(keyword="escalated", target_column="escalated", operator="equals"),
            FilterMapping(keyword="escalation", target_column="escalated", operator="equals"),
            FilterMapping(keyword="first_contact_resolution", target_column="first_contact_resolution", operator="equals"),
            FilterMapping(keyword="first contact resolution", target_column="first_contact_resolution", operator="equals"),
            FilterMapping(keyword="first-contact resolution", target_column="first_contact_resolution", operator="equals"),
            FilterMapping(keyword="first-contact", target_column="first_contact_resolution", operator="equals"),
            FilterMapping(keyword="first_contact", target_column="first_contact_resolution", operator="equals"),
            FilterMapping(keyword="fcr", target_column="first_contact_resolution", operator="equals"),
            FilterMapping(keyword="resolution", target_column="resolution_hours", operator="equals"),
            FilterMapping(keyword="resolution time", target_column="resolution_hours", operator="equals"),
            FilterMapping(keyword="resolution times", target_column="resolution_hours", operator="equals"),
            FilterMapping(keyword="resolution hours", target_column="resolution_hours", operator="equals"),
        ],
    ),
    TableMapping(
        concept_id="ontology:marketing_campaigns",
        table_name="marketing_campaigns",
        columns=[
            ColumnDef(name="campaign_id", classification=ColumnClassification.IDENTIFIER, sql_type="VARCHAR"),
            ColumnDef(name="campaign_name", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="launch_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
            ColumnDef(name="end_date", classification=ColumnClassification.CATEGORICAL, sql_type="DATE"),
            ColumnDef(name="channel", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="target_audience", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
            ColumnDef(name="budget", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="spend", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="impressions", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="clicks", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="conversions", classification=ColumnClassification.NUMERIC, sql_type="INTEGER"),
            ColumnDef(name="revenue_attributed", classification=ColumnClassification.NUMERIC, sql_type="DECIMAL"),
            ColumnDef(name="status", classification=ColumnClassification.CATEGORICAL, sql_type="VARCHAR"),
        ],
        filter_mappings=[
            FilterMapping(keyword="channel", target_column="channel", operator="equals"),
            FilterMapping(keyword="marketing channel", target_column="channel", operator="equals"),
            FilterMapping(keyword="target_audience", target_column="target_audience", operator="equals"),
            FilterMapping(keyword="audience", target_column="target_audience", operator="equals"),
            FilterMapping(keyword="status", target_column="status", operator="equals"),
            FilterMapping(keyword="ctr", target_column="clicks", operator="equals"),
            FilterMapping(keyword="click-through", target_column="clicks", operator="equals"),
            FilterMapping(keyword="click-through rate", target_column="clicks", operator="equals"),
            FilterMapping(keyword="click through rate", target_column="clicks", operator="equals"),
            FilterMapping(keyword="clicks", target_column="clicks", operator="equals"),
            FilterMapping(keyword="impressions", target_column="impressions", operator="equals"),
            FilterMapping(keyword="conversions", target_column="conversions", operator="equals"),
            FilterMapping(keyword="conversion rate", target_column="conversions", operator="equals"),
            FilterMapping(keyword="revenue", target_column="revenue_attributed", operator="equals"),
            FilterMapping(keyword="revenue attributed", target_column="revenue_attributed", operator="equals"),
            FilterMapping(keyword="roi", target_column="revenue_attributed", operator="equals"),
            FilterMapping(keyword="budget", target_column="budget", operator="equals"),
            FilterMapping(keyword="spend", target_column="spend", operator="equals"),
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
            entity_ref: The ontology concept_id (e.g. "ontology:workforce_metrics").

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
