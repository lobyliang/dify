from flask import current_app
from flask_restful import request
import requests
class DreamAIService():
    baseUrl = None
    _CHECK_PERMISSION_URL = "/system/user/checkPermission"
    _GET_USER_INFO_URL = "/system/user/getInfo"

    @staticmethod
    def get_user_info(token:str):
        if DreamAIService.baseUrl is None:
            DreamAIService.baseUrl = current_app.config.get("DREAM_AI_BASE_URL")
        token = request.headers.get('Authorization')
        headers = {
            'Authorization': token
        }
        return requests.get(f"{DreamAIService.baseUrl}{DreamAIService._GET_USER_INFO_URL}", headers=headers).json()
    
    @staticmethod
    def check_permission(perms:dict)->bool:
        if DreamAIService.baseUrl is None:
            DreamAIService.baseUrl = current_app.config.get("DREAM_AI_SERVICE_URL")
        token = request.headers.get('Authorization')
        Clientid = request.headers.get('Clientid')
        headers = {
            'Authorization': token,
            'Clientid': Clientid
        }


        ret = False
        if 'and' in perms:
            and_cond = perms['and']
            if and_cond:
                for cond in and_cond:
                    result = requests.get(f"{DreamAIService.baseUrl}{DreamAIService._CHECK_PERMISSION_URL}?perms={cond}", headers=headers).json()
                    if "data" in result and result["data"]==False:
                        return False
                ret = True
        if 'or' in perms:
            or_cond = perms['or']
            if or_cond:
                for cond in or_cond:
                    result = requests.get(f"{DreamAIService.baseUrl}{DreamAIService._CHECK_PERMISSION_URL}?perms={cond}", headers=headers).json()
                    if "data" in result and result["data"]==True:
                        ret = True
                        break
        return ret
    
    

