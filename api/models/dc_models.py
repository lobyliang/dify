from extensions.ext_database import db
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import UUID

from models import StringUUID


class AppQuestions(db.Model):
    __tablename__ = "app_questions"
    __table_args__ = (
        db.PrimaryKeyConstraint("id", name="app_qur_pkey"),
        db.Index("app_qur_app_id_idx", "app_id"),
    )
    id = db.Column(UUID, server_default=db.text("uuid_generate_v4()"))
    tenant_id = db.Column(UUID, nullable=False)
    app_id = db.Column(UUID, nullable=False)
    questions = db.Column(db.String(4096), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP(0)")
    )
    is_virtual = db.Column(db.Boolean, nullable=False, server_default=db.text("false"))
    status = db.Column(db.String(255), nullable=False, server_default="indexing")

    def to_dict(self):
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "app_id": str(self.app_id),
            "questions": self.questions,
            "created_at": self.created_at,
            "is_virtual": self.is_virtual,
            "status": self.status,
        }


@dataclass
class AppCategory(db.Model):
    __tablename__ = "app_category"
    __table_args__ = (db.PrimaryKeyConstraint("id", name="app_category_pkey"),)
    id = db.Column(UUID, server_default=db.text("uuid_generate_v4()"))
    category = db.Column(db.String(24), nullable=False)
    name = db.Column(db.String(24), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP(0)")
    )
    is_del = db.Column(db.Boolean, nullable=False, server_default=db.text("false"))

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class DocumentSegmentsAttach(db.Model):
    __tablename__ = "document_segments_attachs"
    __table_args__ = (
        db.PrimaryKeyConstraint("id", name="document_segments_attachs_pkey"),
        db.Index("doc_seg_id_idx", "doc_seg_id"),
    )
    id = db.Column(
        StringUUID, nullable=False, server_default=db.text("uuid_generate_v4()")
    )
    doc_seg_id = db.Column(StringUUID, nullable=False)  # DocumentSegment id
    attach_type = db.Column(
        db.String(10), default=db.text("file")
    )  # cover 封面,attach附件
    source = db.Column(db.String(10), default=db.text("url"))  # file 本地文件
    storage_type = db.Column(db.String(16), nullable=False, default=db.text("local"))
    file_name = db.Column(db.String(1024), nullable=False)  # 文件后缀名
    size = db.Column(db.Integer, nullable=False, server_default=db.text("0"))
    file = db.Column(db.String(1024), nullable=False)  # ,文件UUID，或URL地址
    mime_type = db.Column(db.String(256), nullable=False)  #
    extension = db.Column(db.String(16), nullable=False)  # 文件后缀名
    created_by = db.Column(db.String(64), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP(0)")
    )
    used_times = db.Column(db.Integer, nullable=False, server_default=db.text("0"))
    # used_by = db.Column(db.String(64), nullable=True)
    # used_at = db.Column(db.DateTime, nullable=True)


# TODO 用于知识库查询的不同提示词配置，还未处理，lobyliang
# TODO 不同的知识库文件，调用AI时采用不同的提示词进行回答
# class DocumentPrompt(db.Model):
#     __tablename__ = "document_prompts"
#     __table_args__ = (db.PrimaryKeyConstraint("id", name="document_prompt_pkey"),)
#     id = db.Column(
#         StringUUID, nullable=False, server_default=db.text("uuid_generate_v4()")
#     )
#     tenant_id = db.Column(StringUUID, nullable=True)
#     prompt = db.Column(db.String(1024), nullable=False)
#     variable = db.Column(db.String(1024), nullable=False)
#     document_id = db.Column(StringUUID, nullable=False)
#     created_by = db.Column(db.String(64), nullable=False)
#     created_at = db.Column(
#         db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP(0)")
#     )
#     updated_by = db.Column(db.String(64), nullable=True)
#     updated_at = db.Column(
#         db.DateTime, nullable=True, server_default=db.text("CURRENT_TIMESTAMP(0)")
#     )


class DocKeyWords(db.Model):
    __tablename__ = "key_words"
    __table_args__ = (
        db.PrimaryKeyConstraint("id", name="key_words_pkey"),
        db.Index(
            "key_words_index_domain", "tenant_id", "key_word", "domain", unique=False
        ),
    )
    id = db.Column(
        StringUUID, nullable=False, server_default=db.text("uuid_generate_v4()")
    )
    tenant_id = db.Column(StringUUID, nullable=True)
    key_word = db.Column(db.String(64), nullable=False)
    category = db.Column(db.String(255), nullable=True)
    domain = db.Column(db.String(255), nullable=True,comment='岗位、技能、行业')
    created_by = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP(0)")
    )


class DocKeyWordsClosure(db.Model):
    __tablename__ = "key_words_closure"
    __table_args__ = (
        db.PrimaryKeyConstraint(
            "ancestor_id", "descendant_id", name="key_words_closure_pkey"
        ),
        db.Index("key_words_closure_index_tenant", "tenant_id",unique=False),
    )
    ancestor_id = db.Column(StringUUID, nullable=False, primary_key=True)
    descendant_id = db.Column(StringUUID, nullable=False, primary_key=True)
    depth = db.Column(db.Integer, nullable=False)
    tenant_id = db.Column(StringUUID, nullable=False)

class BatchDatasetHitingTestParams(db.Model):
    __tablename__ = 'dataset_batch_hiting_test_params'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='dataset_batch_hiting_test_params_pkey'),
        db.Index('dataset_batch_hiting_test_params_id_idx', 'dataset_id'),
    )
    id = db.Column(StringUUID, primary_key=True, nullable=False, server_default=db.text('uuid_generate_v4()'))
    dataset_id = db.Column(StringUUID, nullable=False)
    params = db.Column(db.JSON, nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    

class BatchDatasetHitingTest(db.Model):
    __tablename__ = 'dataset_batch_hiting_test'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='dataset_batch_hiting_test_pkey'),
        db.Index('dataset_batch_hiting_test_id_idx', 'dataset_id'),
    )

    id = db.Column(StringUUID, primary_key=True, nullable=False, server_default=db.text('uuid_generate_v4()'))
    dataset_id = db.Column(StringUUID, nullable=False)
    question = db.Column(db.String(255), nullable=False)
    ####loby####
    param_id = db.Column(StringUUID, nullable=True)
    like = db.Column(db.Integer, nullable=True, default=0)
    dislike = db.Column(db.Integer, nullable=True, default=0)
    results=db.Column(db.JSON,nullable=True,comment='seg_id,和匹配精度')
    last_results=db.Column(db.JSON,nullable=True,comment='seg_id,和匹配精度')
    ############
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, nullable=True, server_default=db.func.current_timestamp())


class DictCategory(db.Model):
    __tablename__ = "dict_categories"
    __table_args__ = (
        db.PrimaryKeyConstraint("id", name="pk_dict_category_id"),
        db.Index("idx_dict_categories", "key","type","tenant_id", unique=True),
    )
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(StringUUID, nullable=True)
    name = db.Column(db.String(255), nullable=False)
    key = db.Column(db.String(64), nullable=True)
    type= db.Column(db.String(64), nullable=False)


class DictCategoryClosure(db.Model):
    __tablename__ = "dict_category_closure"
    parent_id = db.Column(db.Integer, db.ForeignKey("dict_categories.id"), primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("dict_categories.id"), primary_key=True)


class DictBinding(db.Model):
    __tablename__ = "dict_bindings"
    __table_args__ = (
        db.PrimaryKeyConstraint("id", name="pk_dict_binding_id"),
        db.Index("tag_bind_target_id_idx", "target_id"),
        db.Index("tag_bind_tag_id_idx", "category_id"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    category_id = db.Column(db.Integer, nullable=False)
    target_id = db.Column(db.String(128), nullable=False)
    target_type = db.Column(db.String(64), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP(0)")
    )
    created_by = db.Column(StringUUID, nullable=False)
