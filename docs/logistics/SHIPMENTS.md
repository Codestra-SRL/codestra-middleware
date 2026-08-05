# Shipments

The middleware validates the documented shipment state machine. Skipped transitions fail with HTTP 409. Customer-visible projections exclude prices, private contacts, internal notes, and precise coordinates.
