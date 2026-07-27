\set ON_ERROR_STOP on

\if :{?ingestion_role}
\else
  \echo 'required psql variable ingestion_role is missing'
  \quit 64
\endif

SELECT
  has_schema_privilege(:'ingestion_role', 'public', 'USAGE')
    AS schema_usage,
  has_table_privilege(
    :'ingestion_role', 'public.telephony_call_lifecycle', 'SELECT'
  ) AS lifecycle_select,
  has_table_privilege(
    :'ingestion_role', 'public.telephony_call_lifecycle', 'INSERT'
  ) AS lifecycle_insert,
  has_table_privilege(
    :'ingestion_role', 'public.telephony_call_lifecycle', 'UPDATE'
  ) AS lifecycle_update,
  has_table_privilege(
    :'ingestion_role', 'public.telephony_call_lifecycle_event', 'INSERT'
  ) AS history_insert,
  has_table_privilege(
    :'ingestion_role', 'public.telephony_call_lifecycle_event', 'SELECT'
  ) AS history_select,
  has_table_privilege(
    :'ingestion_role', 'public.telephony_call_lifecycle', 'DELETE'
  ) AS lifecycle_delete,
  has_table_privilege(
    :'ingestion_role', 'public.telephony_call_lifecycle_event', 'DELETE'
  ) AS history_delete;
