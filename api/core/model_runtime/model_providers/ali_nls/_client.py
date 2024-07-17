import json
from datetime import datetime, timedelta
from threading import Lock

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

# 存储token信息
ali_access_tokens: dict[str, 'AliAccessToken'] = {}
ali_access_tokens_lock = Lock()


class AliAccessToken:
    access_key_id: str
    access_token: str
    expires: datetime

    def __init__(self, access_key_id: str) -> None:
        self.access_key_id = access_key_id
        self.access_token = ''
        self.expires = datetime.now() + timedelta(days=1.4)

    @staticmethod
    def _get_access_token(access_key_id: str, access_key_secret: str) -> str:
        """
            请求阿里云Token 有效期 36小时
        """

        acs_client = AcsClient(
            access_key_id,
            access_key_secret,
            "cn-shanghai"
        )
        # 创建request，并设置参数。
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')

        response = acs_client.do_action_with_exception(request)
        jss = json.loads(response)
        if 'Token' in jss and 'Id' in jss['Token']:
            token = jss['Token']['Id']
            # print("阿里云TTS 请求到的token内容，token:"+token+":ExpireTime:"+str(jss['Token']['ExpireTime']))
            return token

    @staticmethod
    def get_access_token(access_key_id: str, secret_key: str) -> 'AliAccessToken':
        """
            请求阿里云token 保存1.4天
        """

        # loop up cache, remove expired access token
        ali_access_tokens_lock.acquire()
        now = datetime.now()
        for key in list(ali_access_tokens.keys()):
            token = ali_access_tokens[key]
            # print("检查过期 "+str({key: value for key, value in token.__dict__.items()}))
            if token.expires < now:
                # print("弹出过期token -*" + str({key: value for key, value in token.__dict__.items()}))
                ali_access_tokens.pop(key)

        if access_key_id not in ali_access_tokens:
            # if access token not in cache, request it
            token = AliAccessToken(access_key_id)
            ali_access_tokens[access_key_id] = token
            # release it to enhance performance
            # btw, _get_access_token will raise exception if failed, release lock here to avoid deadlock
            ali_access_tokens_lock.release()
            # try to get access token
            token_str = AliAccessToken._get_access_token(access_key_id, secret_key)
            token.access_token = token_str
            token.expires = now + timedelta(days=1.4)
            # print("获取新token " + str({key: value for key, value in token.__dict__.items()}))
            return token
        else:
            # if access token in cache, return it
            token = ali_access_tokens[access_key_id]
            ali_access_tokens_lock.release()
            # print("取出已有token " + str({key: value for key, value in token.__dict__.items()}))
            return token