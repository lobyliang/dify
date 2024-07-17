import logging

from core.model_runtime.model_providers.__base.model_provider import ModelProvider

logger = logging.getLogger(__name__)


class AliNlsProvider(ModelProvider):

    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        验证提供程序凭据
        如果验证失败，则引发异常

        :param credentials: 提供者凭据，在“provider_credential_schema”中定义的凭据形式
        """

