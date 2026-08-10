# Platform rollback

No N5 production deployment occurs. Code rollback is a reviewed revert. Workflow rollback imports the exact prior Git artifact recorded in `workflow_deployment_states`. Disable campaign and AI automation before worker rollback.

Database rollback is rehearsed only on disposable PostgreSQL: remove N5 tables in reverse dependency order after exporting required evidence. Core social posts, provider ownership, IntegrationEvent, delivery and existing audit state are not rewritten.
