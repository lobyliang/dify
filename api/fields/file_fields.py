from flask_restful import fields

from libs.helper import TimestampField

upload_config_fields = {
    'file_size_limit': fields.Integer,
    'batch_count_limit': fields.Integer,
    'image_file_size_limit': fields.Integer,
}

file_fields = {
    'id': fields.String,
    'name': fields.String,
    'size': fields.Integer,
    'extension': fields.String,
    'mime_type': fields.String,
    'created_by': fields.String,
    'created_at': TimestampField,
}

chunck_attach_fields={
        'id': fields.String,
        'doc_seg_id': fields.String,
        'attach_type': fields.String,
        'source': fields.String,
        'storage_type':fields.String,
        'file_name': fields.String,
        'size': fields.Integer,
        'file': fields.String,
        'extension': fields.String,
        'mime_type': fields.String,
        'created_by': fields.String,
        'created_at': TimestampField,
}