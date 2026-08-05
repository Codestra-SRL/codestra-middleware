# Transcription service

The middleware contract accepts `call_transcript_v1` structured output with
speaker labels, confidence and redaction status. The AI server must retrieve a
short-lived protected reference and never receive permanent VICIdial storage
access. Faster-Whisper deployment is an infrastructure task pending AI-server
access.
