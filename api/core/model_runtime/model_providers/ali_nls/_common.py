from core.model_runtime.errors.invoke import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)


class _CommonAli:
    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [
            ],
            InvokeServerUnavailableError: [

            ],
            InvokeRateLimitError: [

            ],
            InvokeAuthorizationError: [

            ],
            InvokeBadRequestError: [

            ]
        }
