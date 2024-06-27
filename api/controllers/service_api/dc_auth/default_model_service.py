import logging


from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.errors.validate import CredentialsValidateFailedError
from services.model_load_balancing_service import ModelLoadBalancingService
from services.model_provider_service import ModelProviderService

class DefaultModelService: 


    @staticmethod
    def add_provider(tenant_id:str,model_config:dict):
        # parser = reqparse.RequestParser()
        # parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')
        # args = parser.parse_args()

        model_provider_service = ModelProviderService()

        try:
            model_provider_service.save_provider_credentials(
                tenant_id=tenant_id,
                provider=model_config['provider'],
                credentials=model_config['credentials']
            )
            logging.info(f"tenant:{tenant_id} add model provider {model_config['provider']}")
            return True
        except CredentialsValidateFailedError as ex:
            logging.info(f"tenant:{tenant_id} add model provider failed!\nProrvider:{model_config['provider']}\n Error:{ex}")
            # raise ValueError(str(ex))

        return False        
    @staticmethod
    # def addModel(self,user:Account, tenant_id: str, model_type: str, model: str, provider: str,
    #                       load_balancing: Optional[dict] = None,credentials:Optional[dict] = None, config_from: Optional[str] = None) -> None:    
    def add_model(tenant_id:str,model_config:dict):
        # if not TenantAccountRole.is_privileged_role(user.current_tenant.current_role):
        #     raise Forbidden()
        
        # tenant_id = user.current_tenant_id

        # parser = reqparse.RequestParser()
        # parser.add_argument('model', type=str, required=True, nullable=False, location='json')
        # parser.add_argument('model_type', type=str, required=True, nullable=False,
        #                     choices=[mt.value for mt in ModelType], location='json')
        # parser.add_argument('credentials', type=dict, required=False, nullable=True, location='json')
        # parser.add_argument('load_balancing', type=dict, required=False, nullable=True, location='json')
        # parser.add_argument('config_from', type=str, required=False, nullable=True, location='json')
        # args = parser.parse_args()

        model_load_balancing_service = ModelLoadBalancingService()

        # if (load_balancing and 'enabled' in load_balancing and load_balancing['enabled']):
        if model_config.get('load_balancing',{}).get('enabled',False):
            if 'configs' not in model_config.get('load_balancing',{}):
                raise ValueError('invalid load balancing configs')

            # save load balancing configs
            model_load_balancing_service.update_load_balancing_configs(
                tenant_id=tenant_id,
                provider=model_config['provider'],
                model=model_config['model'],
                model_type=model_config['model_type'],
                configs=model_config.get('load_balancing').get('configs')# args['load_balancing']['configs']
            )

            # enable load balancing
            model_load_balancing_service.enable_model_load_balancing(
                tenant_id=tenant_id,
                provider=model_config['provider'],
                model=model_config['model'],# args['model'],
                model_type=model_config['model_type'] #args['model_type']
            )
        else:
            # disable load balancing
            model_load_balancing_service.disable_model_load_balancing(
                tenant_id=tenant_id,
                provider=model_config['provider'],
                model=model_config['model'],# args['model'],
                model_type=model_config['model_type'] # args['model_type']
            )

            #if args.get('config_from', '') != 'predefined-model':
            if model_config['config_from'] != 'predefined-model':                
                model_provider_service = ModelProviderService()

                try:
                    model_provider_service.save_model_credentials(
                        tenant_id=tenant_id,
                        provider=model_config['provider'],
                        model=model_config['model'], #args['model'],
                        model_type=model_config['model_type'], #args['model_type'],
                        credentials=model_config['credentials'] #args['credentials']
                    )
                    logging.info(f"tenant:{tenant_id} add model :{model_config['model']}:{model_config['model_type']} ")
                    return True
                except CredentialsValidateFailedError as ex:
                    logging.warning(f"tenant:{tenant_id}: add model failed!\nmodel:{model_config['model']}:{model_config['model_type']}\nreason:{str(ex)}")
                    # raise ValueError(str(ex))

        return False
      
    @staticmethod
    def setDefaultModel(tenant_id:str,model_config:dict):
        # parser = reqparse.RequestParser()
        # parser.add_argument('model_settings', type=list, required=True, nullable=False, location='json')
        # args = parser.parse_args()

        # tenant_id = current_user.current_tenant_id

        model_provider_service = ModelProviderService()
        # model_settings = args['model_settings']
        # for model_setting in model_settings:
        if 'model_type' not in model_config or model_config['model_type'] not in [mt.value for mt in ModelType]:
            raise ValueError('invalid model type')

        if 'provider' not in model_config:
            return False

        if 'model' not in model_config:
            raise ValueError('invalid model')

        try:
            model_provider_service.update_default_model_of_model_type(
                tenant_id=tenant_id,
                model_type=model_config['model_type'],
                provider=model_config['provider'],
                model=model_config['model']
            )
            logging.info(f"tenant:{tenant_id}:model:{model_config['model']}:{model_config['model_type']} saved as default model")
            return True
        except Exception:
            logging.warning(f"{model_config['model_type']} save error")
        return False
