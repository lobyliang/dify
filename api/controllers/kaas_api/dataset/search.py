from flask_login import current_user
from controllers.console.setup import setup_required
from controllers.kaas_api.wraps import validate_dream_ai_token
from core.rag.retrieval.dc_retrieval.custom_dataset_retrieval import (
    CustomDataSetRetrieval,
)
from controllers.kaas_api import api
from flask_restful import Resource, reqparse

from libs.login import kaas_login_required


class RAGQueryApi(Resource):

    @setup_required
    @kaas_login_required
    @validate_dream_ai_token(funcs={'and':['kaas:public']},getExtUserId=True)
    def post(
        self,ext_user_id:str
    ):
        tenant_id = str(current_user.current_tenant_id)
        parser = reqparse.RequestParser()
        # parser.add_argument(
        #     "user_id", type=str, required=True, nullable=False, location="json"
        # )
        parser.add_argument(
            "app_id", type=str, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "retrieve_strategy",
            type=str,
            choices=["single", "multiple"],
            required=True,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "search_method",
            type=str,
            choices=[
                "keyword_search",
                "semantic_search",
                "full_text_search",
                "hybrid_search",
            ],
            required=True,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "dataset_ids", type=list, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "reorgenaize",
            type=bool,
            default=True,
            required=True,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "top_k", type=int, default=1, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "score_threshold",
            type=float,
            default=0.7,
            required=False,
            nullable=True,
            location="json",
        )
        parser.add_argument(
            "query", type=str, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "show_source", type=bool, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "attach_detail",
            type=bool,
            required=False,
            nullable=True,
            default=False,
            location="json",
        )
        args = parser.parse_args()
        # user_id = ext_user_id#args["user_id"]
        app_id = args["app_id"]
        retrieve_strategy = args["retrieve_strategy"]
        search_method = args["search_method"]
        dataset_ids = args["dataset_ids"]
        reorgenaize = args["reorgenaize"]
        query = args["query"]
        show_source = args["show_source"]
        tok_k = args["top_k"]
        score_threshold = args["score_threshold"]
        attach_detail = args["attach_detail"]
        # get dataset
        custom_dataset_retrieval = CustomDataSetRetrieval()
        return (
            custom_dataset_retrieval.retrieval(
                user_id=ext_user_id,
                app_id=app_id,
                retrieve_strategy=retrieve_strategy,
                search_method=search_method,
                dataset_ids=dataset_ids,
                reorgenazie_output=reorgenaize,
                query=query,
                invoke_from="kaas_api",
                show_retrieve_source=show_source,
                tenant_id=tenant_id,
                top_k=tok_k,
                score_threshold=score_threshold,
                hit_callback=None,
                # attach_detail=attach_detail,
            ),
            200,
        )
    
class RAGCommnetApi(Resource):
    @setup_required
    @kaas_login_required
    def post(self, query_id: str, seg_id: str, like: str):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "rate", type=float, required=True, nullable=False, location="args"
        )
        args = parser.parse_args()
        rate = args["rate"]
        CustomDataSetRetrieval.comment_rag_query(
            query_id=query_id, like=like, seg_id=seg_id, rate=rate
        )
        return {"msg": "success"}, 200

# 查询知识库
api.add_resource(RAGQueryApi, "/search/query")
# 查询结果点赞、踩
api.add_resource(
    RAGCommnetApi, "/comment/query/<string:query_id>/<string:seg_id>/<string:like>"
)