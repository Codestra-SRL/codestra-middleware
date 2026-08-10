# Media pipeline

Media assets have a Codestra UUID, MIME type, size, SHA-256, backend, opaque location, status and expiry. JPEG, PNG, WebP, MP4 and WebM are initially allowed; extension/MIME mismatch, executable types, invalid checksums and excessive size fail closed.

`LocalStorageBackend` is staging-only with owner-only files and opaque references. `ObjectStorageBackend` is an intentionally disabled interface. Malware scanning, image dimensions and video metadata are required activation gates.
