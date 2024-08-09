from flask_restful import fields

from libs.helper import TimestampField
# hiting_result_item_fields = {
#     ""
# }

#                     ret[segment.id] = {} 
#                     ret[segment.id]["score"] = record["score"]
#                     ret[segment.id]["hit_count"] = record["hit_count"]
#                     ret[segment.id]["position"] = record["position"]
batch_hiting_test_filelds = {
    # 'data': fields.List(fields.Nested(document_status_fields))
    "id": fields.String,
    "dataset_id": fields.String,
    "question": fields.String,
    "param_id": fields.String,
    "like": fields.Integer,
    "dislike": fields.Integer,
    "results": fields.Raw,
    "last_results": fields.Raw,
    "created_by": fields.String,
    "created_at": TimestampField,
    "updated_at": TimestampField
}