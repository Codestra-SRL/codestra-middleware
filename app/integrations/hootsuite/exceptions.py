class HootsuiteError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        unknown_result: bool = False,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.unknown_result = unknown_result
        self.status = status
        self.retry_after = retry_after
