import urllib.parse
from dataclasses import dataclass
import requests

@dataclass
class OAuthUserInfo:
    id: str
    name: str
    email: str


class OAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self):
        raise NotImplementedError()

    def get_access_token(self, code: str):
        raise NotImplementedError()

    def get_raw_user_info(self, token: str):
        raise NotImplementedError()

    def get_user_info(self, token: str) -> OAuthUserInfo:
        raw_info = self.get_raw_user_info(token)
        return self._transform_user_info(raw_info)

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        raise NotImplementedError()


class GitHubOAuth(OAuth):
    _AUTH_URL = 'https://github.com/login/oauth/authorize'
    _TOKEN_URL = 'https://github.com/login/oauth/access_token'
    _USER_INFO_URL = 'https://api.github.com/user'
    _EMAIL_INFO_URL = 'https://api.github.com/user/emails'

    def get_authorization_url(self):
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': 'user:email'  # Request only basic user information
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def get_access_token(self, code: str):
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        headers = {'Accept': 'application/json'}
        response = requests.post(self._TOKEN_URL, data=data, headers=headers)

        response_json = response.json()
        access_token = response_json.get('access_token')

        if not access_token:
            raise ValueError(f"Error in GitHub OAuth: {response_json}")

        return access_token

    def get_raw_user_info(self, token: str):
        headers = {'Authorization': f"token {token}"}
        response = requests.get(self._USER_INFO_URL, headers=headers)
        response.raise_for_status()
        user_info = response.json()

        email_response = requests.get(self._EMAIL_INFO_URL, headers=headers)
        email_info = email_response.json()
        primary_email = next((email for email in email_info if email['primary'] == True), None)

        return {**user_info, 'email': primary_email['email']}

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        email = raw_info.get('email')
        if not email:
            email = f"{raw_info['id']}+{raw_info['login']}@users.noreply.github.com"
        return OAuthUserInfo(
            id=str(raw_info['id']),
            name=raw_info['name'],
            email=email
        )


class GoogleOAuth(OAuth):
    _AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
    _TOKEN_URL = 'https://oauth2.googleapis.com/token'
    _USER_INFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'

    def get_authorization_url(self):
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': 'openid email'
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def get_access_token(self, code: str):
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
        }
        headers = {'Accept': 'application/json'}
        response = requests.post(self._TOKEN_URL, data=data, headers=headers)

        response_json = response.json()
        access_token = response_json.get('access_token')

        if not access_token:
            raise ValueError(f"Error in Google OAuth: {response_json}")

        return access_token

    def get_raw_user_info(self, token: str):
        headers = {'Authorization': f"Bearer {token}"}
        response = requests.get(self._USER_INFO_URL, headers=headers)
        response.raise_for_status()
        return response.json()

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        return OAuthUserInfo(
            id=str(raw_info['sub']),
            name=None,
            email=raw_info['email']
        )


# class WeChatAppOAuth(OAuth):
#     # _AUTH_URL = 'https://open.weixin.qq.com/connect/qrconnect'
#     _AUTH_URL = 'https://api.weixin.qq.com/cgi-bin/token'
#     # _TOKEN_URL = 'https://api.weixin.qq.com/sns/oauth2/access_token'
#     _TOKEN_URL = 'https://api.weixin.qq.com/sns/jscode2session'
#     _USER_INFO_URL = 'https://api.weixin.qq.com/sns/userinfo'


#     def get_authorization_url(self):
#         # params = {
#         #     'appid': self.client_id,
#         #     'response_type': 'code',
#         #     'redirect_uri': self.redirect_uri,
#         #     'scope': 'snsapi_login',
#         #     'state': 'STATE'
#         # }
#         params = {
#             'appid': self.client_id,
#             'secret': self.client_secret,
#             'grant_type': 'client_credential'
#         }
#         return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"
    
#     def get_access_token(self, code: str):
#         data = {
#             'appid': self.client_id,
#             'secret': self.client_secret,
#             'js_code': code,
#             'grant_type': 'authorization_code'
#         }
#         headers = {'Accept': 'application/json'}
#         # response = requests.post(self._TOKEN_URL, data=data, headers=headers)
#         response = requests.get(self._TOKEN_URL, params=data, headers=headers)
#         response_json = response.json()

#         if 'errcode' in response_json:
#             raise ValueError(f"Error in WeChat OAuth: {response_json}")
#         return response_json#.get('access_token')
    
#     def get_raw_user_info(self, tokenDict):
#         token = tokenDict['access_token']
#         openid = tokenDict['openid']
#         headers = {'Authorization': f"Bearer {token}"}
#         response = requests.get(self._USER_INFO_URL, headers=headers)
#         response.raise_for_status()
#         return response.json()
    
#     def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
#         return OAuthUserInfo(
#             id=str(raw_info['openid']),
#             name=str(raw_info['nickname']),
#             email=raw_info['openid']
#         )
    


# class WeChatWebOAuth(OAuth):

#     _AUTH_URL = 'https://open.weixin.qq.com/connect/oauth2/authorize'
#     _TOKEN_URL = 'https://api.weixin.qq.com/sns/oauth2/access_token'
#     _USER_INFO_URL = 'https://api.weixin.qq.com/cgi-bin/user/info'


#     def get_authorization_url(self):
#         # params = {
#         #     'appid': self.client_id,
#         #     'response_type': 'code',
#         #     'redirect_uri': self.redirect_uri,
#         #     'scope': 'snsapi_login',
#         #     'state': 'STATE'
#         # }
#         params = {
#             'appid': self.client_id,
#             'secret': self.client_secret,
#             'redirect_uri': self.redirect_uri,
#             'scope': 'snsapi_base',
#             'response_type': 'code'
#         }
#         return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}#wechat_redirect"
    
#     def get_access_token(self, code: str):
#         data = {
#             'appid': self.client_id,
#             'secret': self.client_secret,
#             'code': code,
#             'grant_type': 'authorization_code'
#         }
#         headers = {'Accept': 'application/json'}
#         # response = requests.post(self._TOKEN_URL, data=data, headers=headers)
#         response = requests.get(self._TOKEN_URL, params=data, headers=headers)
#         response_json = response.json()
        
#         if 'errcode' in response_json:
#             raise ValueError(f"Error in WeChat OAuth: {response_json}")
        
#         redis_client.setex(f'wechat_token/{response_json.get("access_token")}', response_json.get('expires_in'), json.dumps(response_json))
#         return response_json.get('access_token')
    
#     def get_raw_user_info(self, token: str):
#         # headers = {'Authorization': f"Bearer {token}"}
#         loginInfos = redis_client.get(f'wechat_token/{token}')
#         if not loginInfos:
#             raise ValueError(f"Error in WeChat OAuth: {loginInfos}")
#         loginInfos = json.loads(loginInfos)
#         if not loginInfos or 'openid' not in loginInfos:
#             raise ValueError(f"Error in WeChat OAuth: {loginInfos}")
#         openid = loginInfos.get('openid')
#         params={
#             'access_token': token,
#             'openid': openid
#         }
#         response = requests.get(self._USER_INFO_URL,params=params)  #headers=headers)
#         response.raise_for_status()
#         return response.json()
    
# #     {   
# #   "openid": "OPENID",
# #   "nickname": NICKNAME,
# #   "sex": 1,
# #   "province":"PROVINCE",
# #   "city":"CITY",
# #   "country":"COUNTRY",
# #   "headimgurl":"https://thirdwx.qlogo.cn/mmopen/g3MonUZtNHkdmzicIlibx6iaFqAc56vxLSUfpb6n5WKSYVY0ChQKkiaJSgQ1dZuTOgvLLrhJbERQQ4eMsv84eavHiaiceqxibJxCfHe/46",
# #   "privilege":[ "PRIVILEGE1" "PRIVILEGE2"     ],
# #   "unionid": "o6_bmasdasdsad6_2sgVt7hMZOPfL"
# # }

# # {
# #     "subscribe": 1, 
# #     "openid": "o6_bmjrPTlm6_2sgVt7hMZOPfL2M", 
# #     "language": "zh_CN", 
# #     "subscribe_time": 1382694957,
# #     "unionid": " o6_bmasdasdsad6_2sgVt7hMZOPfL",
# #     "remark": "",
# #     "groupid": 0,
# #     "tagid_list":[128,2],
# #     "subscribe_scene": "ADD_SCENE_QR_CODE",
# #     "qr_scene": 98765,
# #     "qr_scene_str": ""
# # }
    
#     def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
#         if not raw_info:
#             raise ValueError(f"Error in WeChat OAuth: {raw_info}")
#         email_domain = current_app.config['DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN']
#         email = f"{raw_info['nickname']}@{email_domain}"
#         return OAuthUserInfo(
#             id=str(raw_info['openid']),
#             name=str(raw_info['nickname']),
#             email=email
#         )
    

# class WeChatOpenOAuth(OAuth):

#     _AUTH_URL = 'https://open.weixin.qq.com/connect/qrconnect'
#     _TOKEN_URL = 'https://api.weixin.qq.com/sns/oauth2/access_token'
#     _USER_INFO_URL = 'https://api.weixin.qq.com/sns/userinfo'

#     def get_authorization_url(self):
#         params = {
#             'appid': self.client_id,
#             'response_type': 'code',
#             'redirect_uri': self.redirect_uri,
#             'scope': 'snsapi_userinfo',#'snsapi_login',
#             # 'state': 'STATE'
#         }
#         return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}#wechat_redirect"
    
#     def get_access_token(self, code: str):
#         data = {
#             'appid': self.client_id,
#             'secret': self.client_secret,
#             'code': code,
#             'grant_type': 'authorization_code'
#         }
#         headers = {'Accept': 'application/json'}
#         # response = requests.post(self._TOKEN_URL, data=data, headers=headers)
#         response = requests.get(self._TOKEN_URL, params=data, headers=headers)
#         response_json = response.json()
        
#         if 'errcode' in response_json:
#             raise ValueError(f"Error in WeChat OAuth: {response_json}")
        
#         redis_client.setex(f'wechat_open_token/{response_json.get("access_token")}', response_json.get('expires_in'), json.dumps(response_json))
#         return response_json.get('access_token')
    
#     def get_raw_user_info(self, token: str):
#         # headers = {'Authorization': f"Bearer {token}"}
#         loginInfos = redis_client.get(f'wechat_open_token/{token}')
#         if not loginInfos:
#             raise ValueError(f"Error in WeChat OAuth: {loginInfos}")
#         loginInfos = json.loads(loginInfos)
#         if not loginInfos or 'openid' not in loginInfos:
#             raise ValueError(f"Error in WeChat OAuth: {loginInfos}")
#         openid = loginInfos.get('openid')
#         params={
#             'access_token': token,
#             'openid': openid,
#             'lang': 'zh_CN'
#         }
#         response = requests.get(self._USER_INFO_URL,params=params)  #headers=headers)
#         response.raise_for_status()
#         return response.json()
# # {
# #     "openid": "OPENID",
# #     "nickname": "NICKNAME",
# #     "sex": 1,
# #     "province": "PROVINCE",
# #     "city": "CITY",
# #     "country": "COUNTRY",
# #     "headimgurl": "http://thirdwx.qlogo.cn/mmopen/g3MonUZtNHkzico..."
# # }    
    
#     def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
#         if not raw_info:
#             raise ValueError(f"Error in WeChat OAuth: {raw_info}")
#         email_domain = current_app.config['DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN']
#         email = f"{raw_info['nickname']}@{email_domain}"
#         return OAuthUserInfo(
#             id=str(raw_info['openid']),
#             name=str(raw_info['nickname']),
#             email=email
#         )    
    

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
