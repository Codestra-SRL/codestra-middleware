# Recording API rollback

Rollback restores the previously approved Middleware image and Compose
definition by exact digest/checksum. Before rollback, disable recording
delivery on Server B. After rollback, verify that the five recording API routes
are absent, no recording completion is accepted, and existing objects and Odoo
metadata remain untouched. Rollback never deletes an object or Odoo record.
