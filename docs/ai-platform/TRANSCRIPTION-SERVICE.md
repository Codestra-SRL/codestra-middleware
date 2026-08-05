# Transcription service

`POST /api/v1/transcriptions` accepts `call_transcript_v1` requests over authenticated private transport. The runtime uses Faster-Whisper/CTranslate2 when the approved model is loaded. Concurrency defaults to one for canaries. Speaker labels remain `UNKNOWN`/`SPEAKER_n` unless reliable channel or diarization evidence supports agent/customer attribution. Audio is size- and format-limited and temporary files are always removed.

