import urllib.parse
from extensions.ext_redis import redis_client
import requests
import json
from flask import current_app

from libs.oauth import OAuth, OAuthUserInfo
from services.dc_wechat_app_account_service import WeChatAppAccountService
from services.dc_wechat_tenant_info_service import WeChatAppType, WechatTenantInfoService


class WeChatMiniAppOAuth(OAuth):
    # _AUTH_URL = 'https://open.weixin.qq.com/connect/qrconnect'
    # _AUTH_URL = 'https://api.weixin.qq.com/cgi-bin/token'
    # _TOKEN_URL = 'https://api.weixin.qq.com/sns/oauth2/access_token'
    _API_TOKEN_URL = 'https://api.weixin.qq.com/cgi-bin/token'
    _TOKEN_URL = 'https://api.weixin.qq.com/sns/jscode2session'
    _USER_INFO_URL = 'https://api.weixin.qq.com/sns/userinfo'
    _GET_PHONE_NO_URL = 'https://api.weixin.qq.com/wxa/business/getuserphonenumber'
    # client_id=current_app.config.get('WECHAT_APP_ID')
    # client_secret=current_app.config.get('WECHAT_APP_SECRET')

    # def get_authorization_url(self):
    #     # params = {
    #     #     'appid': self.client_id,
    #     #     'response_type': 'code',
    #     #     'redirect_uri': self.redirect_uri,
    #     #     'scope': 'snsapi_login',
    #     #     'state': 'STATE'
    #     # }
    #     params = {
    #         'appid': self.client_id,
    #         'secret': self.client_secret,
    #         'grant_type': 'client_credential'
    #     }
    #     return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    @staticmethod
    def get_api_token(tenant_id:str,wechat_app_id:str):
        access_token = redis_client.get(f'wechat_app_token_{wechat_app_id}')
        if access_token:
            return access_token.decode()
        wechat_app_secret = WechatTenantInfoService.get_wechat_tenant_info(tenant_id,wechat_app_id,"app")
        if wechat_app_secret is None:
            raise ValueError("微信小程序未注册")
        data = {
            'grant_type': 'client_credential',
            'appid':wechat_app_secret.get("app_id"),  #current_app.config.get('WECHAT_APP_ID'),
            'secret':wechat_app_secret.get("app_secret") #current_app.config.get('WECHAT_APP_SECRET')
        }
        headers = {'Accept': 'application/json'}
        response = requests.get(WeChatMiniAppOAuth._API_TOKEN_URL, params=data, headers=headers)
        response_json = response.json()
        if 'errcode' in response_json:
            raise ValueError()
        access_token = response_json.get('access_token')
        expires_in = response_json.get('expires_in')
        redis_client.setex(f'wechat_app_token_{wechat_app_id}', expires_in, access_token)
        return access_token

    @staticmethod
    def get_access_token(tenant_id:str,wechat_app_id:str,code: str):
        wechat_app_secret = WechatTenantInfoService.get_wechat_tenant_info(tenant_id,wechat_app_id,WeChatAppType.WECHAT_MINI_APP)
        if wechat_app_secret is None:
            raise ValueError("微信小程序未注册")
        data = {
            'appid':wechat_app_secret.get("app_id"),  #current_app.config.get('WECHAT_APP_ID'),
            'secret':wechat_app_secret.get("app_secret"), #current_app.config.get('WECHAT_APP_SECRET'),
            'js_code': code,
            'grant_type': 'authorization_code'
        }
        headers = {'Accept': 'application/json'}
        # response = requests.post(self._TOKEN_URL, data=data, headers=headers)
        response = requests.get(WeChatMiniAppOAuth._TOKEN_URL, params=data, headers=headers)
        response_json = response.json()

        if 'errcode' in response_json:
            raise ValueError(f"Error in WeChat OAuth: {response_json}")
        return response_json#.get('access_token')
    
    # @staticmethod
    # def get_raw_user_info(tokenDict):
    #     token = WeChatMiniAppOAuth.get_api_token()
    #     openid = tokenDict.get('openid',None)
    #     session_key = tokenDict.get('session_key',None)
    #     unionid = tokenDict.get('unionid',None)
    #     headers = {'Authorization': f"Bearer {token}"}
    #     response = requests.get(WeChatMiniAppOAuth._USER_INFO_URL, headers=headers)
    #     response.raise_for_status()
    #     return response.json()
    
    @staticmethod
    def _transform_user_info( raw_info: dict) -> OAuthUserInfo:
        return OAuthUserInfo(
            id=str(raw_info['openid']),
            name=str(raw_info['nickname']),
            email=raw_info['openid']
        )
    
#     "phone_info": {
#         "phoneNumber":"xxxxxx",
#         "purePhoneNumber": "xxxxxx",
#         "countryCode": 86,
#         "watermark": {
#             "timestamp": 1637744274,
#             "appid": "xxxx"
#         }
#     }
# } 

    @staticmethod
    def get_phon_no(tenant_id:str,wechat_app_id:str,phone_code:str,openid:str):
        access_token = WeChatMiniAppOAuth.get_api_token(tenant_id,wechat_app_id)
        params = {
            'access_token': access_token
            # 'openid': openid,
            # 'code': phone_code
        }
        data = {
            'code': phone_code
        }
        # url = f"{WeChatAppOAuth._GET_PHONE_NO_URL}?access_token={access_token}"
        response = requests.post(WeChatMiniAppOAuth._GET_PHONE_NO_URL,json=data,params=params)
        response_json = response.json()
        if  response_json.get('errcode',1) != 0:
            raise ValueError(f"Error in WeChat OAuth: {response_json.get('errmsg')}")
        return response_json.get('phone_info')
    


    


class WeChatWebOAuth(OAuth):

    _AUTH_URL = 'https://open.weixin.qq.com/connect/oauth2/authorize'
    _TOKEN_URL = 'https://api.weixin.qq.com/sns/oauth2/access_token'
    _USER_INFO_URL = 'https://api.weixin.qq.com/cgi-bin/user/info'


    def get_authorization_url(self):
        # params = {
        #     'appid': self.client_id,
        #     'response_type': 'code',
        #     'redirect_uri': self.redirect_uri,
        #     'scope': 'snsapi_login',
        #     'state': 'STATE'
        # }
        params = {
            'appid': self.client_id,
            'secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'scope': 'snsapi_base',
            'response_type': 'code'
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}#wechat_redirect"
    
    def get_access_token(self, code: str):
        data = {
            'appid': self.client_id,
            'secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code'
        }
        headers = {'Accept': 'application/json'}
        # response = requests.post(self._TOKEN_URL, data=data, headers=headers)
        response = requests.get(self._TOKEN_URL, params=data, headers=headers)
        response_json = response.json()
        
        if 'errcode' in response_json:
            raise ValueError(f"Error in WeChat OAuth: {response_json}")
        
        redis_client.setex(f'wechat_token/{response_json.get("access_token")}', response_json.get('expires_in'), json.dumps(response_json))
        return response_json.get('access_token')
    
    def get_raw_user_info(self, token: str):
        # headers = {'Authorization': f"Bearer {token}"}
        loginInfos = redis_client.get(f'wechat_token/{token}')
        if not loginInfos:
            raise ValueError(f"Error in WeChat OAuth: {loginInfos}")
        loginInfos = json.loads(loginInfos)
        if not loginInfos or 'openid' not in loginInfos:
            raise ValueError(f"Error in WeChat OAuth: {loginInfos}")
        openid = loginInfos.get('openid')
        params={
            'access_token': token,
            'openid': openid
        }
        response = requests.get(self._USER_INFO_URL,params=params)  #headers=headers)
        response.raise_for_status()
        return response.json()
    
#     {   
#   "openid": "OPENID",
#   "nickname": NICKNAME,
#   "sex": 1,
#   "province":"PROVINCE",
#   "city":"CITY",
#   "country":"COUNTRY",
#   "headimgurl":"https://thirdwx.qlogo.cn/mmopen/g3MonUZtNHkdmzicIlibx6iaFqAc56vxLSUfpb6n5WKSYVY0ChQKkiaJSgQ1dZuTOgvLLrhJbERQQ4eMsv84eavHiaiceqxibJxCfHe/46",
#   "privilege":[ "PRIVILEGE1" "PRIVILEGE2"     ],
#   "unionid": "o6_bmasdasdsad6_2sgVt7hMZOPfL"
# }

# {
#     "subscribe": 1, 
#     "openid": "o6_bmjrPTlm6_2sgVt7hMZOPfL2M", 
#     "language": "zh_CN", 
#     "subscribe_time": 1382694957,
#     "unionid": " o6_bmasdasdsad6_2sgVt7hMZOPfL",
#     "remark": "",
#     "groupid": 0,
#     "tagid_list":[128,2],
#     "subscribe_scene": "ADD_SCENE_QR_CODE",
#     "qr_scene": 98765,
#     "qr_scene_str": ""
# }
    
    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        if not raw_info:
            raise ValueError(f"Error in WeChat OAuth: {raw_info}")
        email_domain = current_app.config['DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN']
        email = f"{raw_info['nickname']}@{email_domain}"
        return OAuthUserInfo(
            id=str(raw_info['openid']),
            name=str(raw_info['nickname']),
            email=email
        )
    

class WeChatOpenOAuth(OAuth):

    _AUTH_URL = 'https://open.weixin.qq.com/connect/qrconnect'
    _TOKEN_URL = 'https://api.weixin.qq.com/sns/oauth2/access_token'
    _USER_INFO_URL = 'https://api.weixin.qq.com/sns/userinfo'

    def get_authorization_url(self):
        params = {
            'appid': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': 'snsapi_userinfo',#'snsapi_login',
            # 'state': 'STATE'
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}#wechat_redirect"
    
    def get_access_token(self, code: str):
        data = {
            'appid': self.client_id,
            'secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code'
        }
        headers = {'Accept': 'application/json'}
        # response = requests.post(self._TOKEN_URL, data=data, headers=headers)
        response = requests.get(self._TOKEN_URL, params=data, headers=headers)
        response_json = response.json()
        
        if 'errcode' in response_json:
            raise ValueError(f"Error in WeChat OAuth: {response_json}")
        
        redis_client.setex(f'wechat_open_token/{response_json.get("access_token")}', response_json.get('expires_in'), json.dumps(response_json))
        return response_json.get('access_token')
    
    def get_raw_user_info(self, token: str):
        # headers = {'Authorization': f"Bearer {token}"}
        loginInfos = redis_client.get(f'wechat_open_token/{token}')
        if not loginInfos:
            raise ValueError(f"Error in WeChat OAuth: {loginInfos}")
        loginInfos = json.loads(loginInfos)
        if not loginInfos or 'openid' not in loginInfos:
            raise ValueError(f"Error in WeChat OAuth: {loginInfos}")
        openid = loginInfos.get('openid')
        params={
            'access_token': token,
            'openid': openid,
            'lang': 'zh_CN'
        }
        response = requests.get(self._USER_INFO_URL,params=params)  #headers=headers)
        response.raise_for_status()
        return response.json()
# {
#     "openid": "OPENID",
#     "nickname": "NICKNAME",
#     "sex": 1,
#     "province": "PROVINCE",
#     "city": "CITY",
#     "country": "COUNTRY",
#     "headimgurl": "http://thirdwx.qlogo.cn/mmopen/g3MonUZtNHkzico..."
# }    
    
    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        if not raw_info:
            raise ValueError(f"Error in WeChat OAuth: {raw_info}")
        email_domain = current_app.config['DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN']
        email = f"{raw_info['nickname']}@{email_domain}"
        return OAuthUserInfo(
            id=str(raw_info['openid']),
            name=str(raw_info['nickname']),
            email=email
        )    
# # https://developers.weixin.qq.com/doc/offiaccount/OA_Web_Apps/Wechat_webpage_authorization.html
#     def login():
#         code = request.json.get('code')
#         if not code:
#             return jsonify({'error': 'Missing code'}), 400

#         # 向微信服务器请求openId和sessionKey
#         url = f"https://api.weixin.qq.com/sns/jscode2session?appid={WECHAT_APPID}&secret={WECHAT_APPSECRET}&js_code={code}&grant_type=authorization_code"
#         response = requests.get(url)
#         data = response.json()
#         if 'errcode' in data:
#             return jsonify({'error': data['errmsg']}), 400

#         openid = data['openid']            
#         session_key = data['session_key']

#         # 这里可以处理用户信息，如保存到数据库
#         # 示例：生成用户信息
#         user_info = {
#             'openid': openid,
#             'session_key': session_key,
#             # 其他用户信息
#         }

#         # 返回用户信息
#         return jsonify({'userInfo': user_info})
