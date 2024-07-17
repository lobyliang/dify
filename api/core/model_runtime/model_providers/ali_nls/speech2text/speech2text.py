from typing import IO, Optional

from requests import post

from core.model_runtime.errors.validate import CredentialsValidateFailedError
from core.model_runtime.model_providers.__base.speech2text_model import Speech2TextModel
from core.model_runtime.model_providers.ali_nls._client import AliAccessToken
from core.model_runtime.model_providers.ali_nls._common import _CommonAli


class AliNlsSpeech2TextModel(_CommonAli, Speech2TextModel):
    """
    阿里云语音到文本模型 一句话识别 的模型类。
    """

    def _invoke(self, model: str, credentials: dict,
                file: IO[bytes], user: Optional[str] = None) \
            -> str:
        """
        调用ASR文本模型

        ：param model：模型名称
        ：param凭据：模型凭据
        ：param文件：音频文件
        ：param user：唯一的用户id
        ：return：给定音频文件的文本
        """
        return self._speech2text_invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            audio_file_path = self._get_demo_file_path()

            with open(audio_file_path, 'rb') as audio_file:
                self._speech2text_invoke(model, credentials, audio_file)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _speech2text_invoke(self, model: str, credentials: dict, file: IO[bytes]) -> str:
        """
        调用ASR文本模型

        ：param model：模型名称
        ：param凭据：模型凭据
        ：param文件：音频文件
        ：return：给定音频文件的文本
        """
        print("执行阿里云 ASR")
        token = AliAccessToken.get_access_token(credentials['access_key_id'], credentials['access_key_secret'])
        query_param = {
            "appkey": credentials["ali_nls_app_key"],
            "token": token.access_token,
            "format": "mp3"
        }
        response = post("https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr", params=query_param, data=file)
        """
        错误返回
        {
            "task_id": "d31a188d780e4a7082ade4916c0db168",
            "result": "",
            "status": 40000001,
            "message": "Meta:ACCESS_DENIED:The token 'af8d2e27b643415297d53f5e981cbc0a' is invalid!"
        }
        """
        """
        正常返回
        {
            "task_id": "d822d854cc2c41f68ae55bcbe655bcd4",
            "result": "一二三四五零二十七",
            "status": 20000000,
            "message": "SUCCESS"
        }
        """
        ali_result = response.json()
        if ali_result["status"] != 20000000:
            raise CredentialsValidateFailedError(ali_result["message"])

        return response.json()["result"]
