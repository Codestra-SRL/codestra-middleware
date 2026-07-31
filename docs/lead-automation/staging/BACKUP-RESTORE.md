# Disposable backup and restore rehearsal

Use uniquely named temporary PostgreSQL containers on an internal temporary
network. Populate only synthetic fixtures, upgrade Middleware to the sole
Alembic head, and install the Odoo module in a separate synthetic database.

Create logical dumps, encrypt them with an ephemeral rehearsal key, record
SHA-256 checksums, restore into new temporary containers, and verify the
Alembic head and Odoo module state. Destroy containers, network, volumes,
plaintext dumps, encrypted dumps, and the ephemeral key after evidence is
recorded. Production data and existing volumes are prohibited.

