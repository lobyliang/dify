import uuid

from sqlalchemy import text
import sqlalchemy
from werkzeug.exceptions import NotFound,Conflict
from flask_restful import  marshal
from fields.dataset_fields import dataset_detail_fields
from extensions.ext_database import db
from models.dc_models import DictCategory, DictBinding, DictCategoryClosure
from models.dataset import Dataset


class DictService:
    @staticmethod
    def to_tree_with_dataset(data, parent_id: int ,tenant_id:str,account_id:str):
        return {
            "datasets":DictService.get_category_datasets(parent_id,tenant_id,account_id),
            "childrens":[
            {
                "id": row[0],
                "name": row[1],
                "key": row[2],
                "parent_id": row[3],
                "level": row[4],
                "datasets": DictService.get_category_datasets(row[0],tenant_id,account_id),
                "childrens": DictService.to_tree_with_dataset(data, row[0],tenant_id,account_id),
            }
            for row in data
            if row[3] == parent_id
        ]}
    @staticmethod
    def to_tree_with_bindings(data, parent_id: int = 0):
        return {
            "target_ids":[target.target_id for target in DictService.get_category_bindings(parent_id)],
            "childrens":[
            {
                "id": row[0],
                "name": row[1],
                "key": row[2],
                "parent_id": row[3],
                "level": row[4],
                "target_ids": [target.target_id for target in DictService.get_category_bindings(row[0])],
                "childrens": DictService.to_tree_with_bindings(data, row[0]),
            }
            for row in data
            if row[3] == parent_id
        ]}

    @staticmethod
    def to_tree(data, parent_id: int = 0):
        return [
            {
                "id": row[0],
                "name": row[1],
                "key": row[2],
                "parent_id": row[3],
                "level": row[4],
                "childrens": DictService.to_tree(data, row[0]),
            }
            for row in data
            if row[3] == parent_id
        ]

    @staticmethod
    def get_category_tree(category_type:str,root_id: int,tenant_id:str,account_id:str, with_bindings: bool = False) -> dict:
        query = text(
            """
        WITH RECURSIVE category_tree AS (
                SELECT id, name,key, 0::INT as parent_id, 0 as level
                FROM dict_categories
                WHERE id = :root_id

                UNION ALL

                SELECT c.id, c.name,c.key, h.parent_id, ct.level + 1
                FROM dict_categories c
                JOIN dict_category_closure h ON c.id = h.child_id
                JOIN category_tree ct ON ct.id = h.parent_id
            )
            SELECT * FROM category_tree;
        """
        )

        result = db.session.execute(query, {"root_id": root_id}).fetchall()

        if with_bindings:
            if category_type == 'DataSet':
                return DictService.to_tree_with_dataset(result,root_id,tenant_id,account_id)
            else:
                return DictService.to_tree_with_bindings(result,root_id)
        else:
            return DictService.to_tree(result,root_id)

    @staticmethod
    def get_category_all_type_count(tenant_id: str) -> int:
        try:
            count = (
                db.session.query(DictCategory)
                .outerjoin(
                    DictCategoryClosure, DictCategory.id == DictCategoryClosure.child_id
                )
                .filter(
                    DictCategory.tenant_id == tenant_id,
                    DictCategoryClosure.parent_id == 0,
                )
                .count()
            )
        except Exception as e:
            raise e
        return count

    @staticmethod
    def get_category_all_types(tenant_id: str) -> list[DictCategory]:
        try:
            roots = (
                db.session.query(DictCategory)
                .outerjoin(
                    DictCategoryClosure, DictCategory.id == DictCategoryClosure.child_id
                )
                .filter(
                    DictCategory.tenant_id == tenant_id,
                    DictCategoryClosure.parent_id == 0,
                )
                .all()
            )
        except Exception as e:
            raise e
        return roots

    @staticmethod
    def get_category_childs(category_id: int) -> list[DictCategory]:
        try:
            # categories = (
            #     db.session.query(DictCategory,DictCategoryClosure).outerjoin(DictCategory.id == DictCategoryClosure.child_id)\
            #     .filter(DictCategoryClosure.parent_id == category_id)
            #     .all()
            # )
            categories = (
                db.session.query(DictCategory).outerjoin(DictCategoryClosure,DictCategory.id == DictCategoryClosure.child_id)\
                .filter(DictCategoryClosure.parent_id == category_id)
                .all()
            )
        except Exception as e:
            raise e
        return categories
    
    @staticmethod
    def get_category_by_id(category_id: int) -> DictCategory:
        try:
            category = (
                db.session.query(DictCategory)
                .filter(DictCategory.id == category_id)
                .one_or_none()
            )
        except Exception as e:
            raise e
        return category
    @staticmethod
    def get_category_root(tenant_id: str, type: str) -> DictCategory:
        try:
            category = (
                db.session.query(DictCategory).join(DictCategoryClosure,DictCategoryClosure.child_id == DictCategory.id)
                .filter(DictCategory.tenant_id == tenant_id, DictCategory.type == type, DictCategoryClosure.parent_id == 0)
                .one_or_none()
            )
        except Exception as e:
            raise e
        if not category:
            return None
        return category
    @staticmethod
    def get_category_by_key(tenant_id: str, key: str) -> DictCategory:
        try:
            category = (
                db.session.query(DictCategory)
                .filter(DictCategory.tenant_id == tenant_id, DictCategory.key == key)
                .one_or_none()
            )
        except Exception as e:
            raise e
        if not category:
            return None
        return category

    @staticmethod
    def move_category_binding(binding_ids:list[int],category_id:int,account_id:str) -> list[DictBinding]:
        try:
            ret = []
            bindings = (
                db.session.query(DictBinding)
                .filter(DictBinding.id.in_(binding_ids))
                .all()
            )
            for binding in bindings:
                db.session.delete(binding)
                newbinding = DictBinding(category_id=category_id, target_id=binding.target_id,target_type=binding.target_type,created_by=account_id)                
                db.session.add(newbinding)
                ret.append(newbinding)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e
        return ret

    @staticmethod
    def get_category_binding(bingding_ids:list[int]) -> list[DictBinding]:
        try:
            bindings = (
                db.session.query(DictBinding)
                .filter(DictBinding.id.in_(bingding_ids))
                .all()
            )
        except Exception as e:
            raise e
        return bindings
    
    @staticmethod
    def get_root_datasets(tenant_id: str,account_id:str) -> list[Dataset]:
        try:
            type = "DataSet"
            bindings = db.session.query(DictBinding).outerjoin(DictCategory, DictBinding.category_id == DictCategory.id).filter(DictCategory.tenant_id == tenant_id, DictCategory.type == type).all()
            binding_ids = [binding.target_id for binding in bindings]
            my_datasets = db.session.query(Dataset).filter(Dataset.tenant_id==tenant_id,Dataset.permission=="only_me",Dataset.created_by==account_id,Dataset.id.notin_(binding_ids)).all()
            team_dataset = db.session.query(Dataset).filter(Dataset.tenant_id==tenant_id,Dataset.permission=="all_team_members",Dataset.id.notin_(binding_ids)).all()
            datasets = my_datasets + team_dataset
        except Exception as e:
            raise e
        return datasets

    @staticmethod
    def get_category_datasets(category_id:int,tenant_id: str,account_id:str) -> list[Dataset]:
        try:
            datasets = []
            type = "DataSet"
            bindings = db.session.query(DictBinding).outerjoin(DictCategory, DictBinding.category_id == DictCategory.id).filter(DictCategory.id==category_id,DictCategory.tenant_id == tenant_id, DictCategory.type == type).all()
            for binding in bindings:
                dataset = db.session.query(Dataset).filter(Dataset.tenant_id==tenant_id,Dataset.permission=="only_me",Dataset.created_by==account_id,Dataset.id==binding.target_id).one_or_none()
                if dataset is None:
                    dataset = db.session.query(Dataset).filter(Dataset.tenant_id==tenant_id,Dataset.permission=="all_team_members",Dataset.id==binding.target_id).one_or_none()
                if dataset is None:
                    continue

                ds_dict = marshal(dataset,dataset_detail_fields)
                ds_dict["binding_id"] = binding.target_id
                datasets.append(ds_dict)
            dict_closure= db.session.query(DictCategoryClosure).filter(DictCategoryClosure.child_id==category_id).one_or_none()
            if dict_closure is not None and dict_closure.parent_id == 0:
                bindings = db.session.query(DictBinding).outerjoin(DictCategory, DictBinding.category_id == DictCategory.id).filter(DictCategory.tenant_id == tenant_id, DictCategory.type == type).distinct(DictBinding.target_id).all()
                binding_ids = [binding.target_id for binding in bindings]
                my_datasets = db.session.query(Dataset).filter(Dataset.tenant_id==tenant_id,Dataset.permission=="only_me",Dataset.created_by==account_id,Dataset.id.notin_(binding_ids)).all()
                team_dataset = db.session.query(Dataset).filter(Dataset.tenant_id==tenant_id,Dataset.permission=="all_team_members",Dataset.id.notin_(binding_ids)).all()
                for dataset in my_datasets + team_dataset:
                    ds_dict = marshal(dataset,dataset_detail_fields)
                    ds_dict["binding_id"] = None
                    datasets.append(ds_dict)
            
        except Exception as e:
            raise e
        return datasets        
    @staticmethod
    def get_category_bindings(category_id: int) -> list[DictBinding]:
        try:
            bindings = (
                db.session.query(DictBinding)
                .filter(DictBinding.category_id == category_id)
                .all()
            )
        except Exception as e:
            raise e
        return bindings

    @staticmethod
    def update_category(category_id: int, name: str, key: str) -> DictCategory:
        try:
            category = DictService.get_category_by_id(category_id)
            if category is None:
                raise NotFound("Category not found")
            category.name = name
            category.key = key
            db.session.commit()
        except Exception as e:
            raise e
        return category

    @staticmethod
    def delete_closure(category_id: int, parent_id: int):
        try:
            closure = (
                db.session.query(DictCategoryClosure)
                .filter(
                    DictCategoryClosure.child_id == category_id,
                    DictCategoryClosure.parent_id == parent_id,
                )
                .one_or_none()
            )
            if closure:
                db.session.delete(closure)
                db.session.commit()
        except Exception as e:
            raise e
        
    @staticmethod
    def move_category(
        category_id: int, old_parent_id: int, new_parent_id: int
    ) -> DictCategory:
        try:
            category = DictService.get_category_by_id(category_id)
            if category is None:
                raise NotFound("Category not found")
            old_closure = (
                db.session.query(DictCategoryClosure)
                .filter(
                    DictCategoryClosure.child_id == category_id,
                    DictCategoryClosure.parent_id == old_parent_id,
                )
                .one_or_none()
            )
            if old_closure:
                db.session.delete(old_closure)
            new_closure = DictCategoryClosure(
                category_id=category_id, parent_id=new_parent_id
            )
            db.session.add(new_closure)
            db.session.commit()
        except Exception as e:
            raise e
        return category

    @staticmethod
    def add_category(
        tenant_id: str, name: str, key: str,type:str, parent_id: int = None,account_id:uuid=None
    ) -> DictCategory:
        try:
            category = DictCategory(
                tenant_id=tenant_id,
                name=name,
                key=key,
                type=type,
                # parent_id=parent_id if parent_id else None,
                # created_by=str(account_id) if account_id else None,
            )
            db.session.add(category)
            db.session.commit()
            
            closure = DictCategoryClosure(
                child_id=category.id, parent_id=parent_id if parent_id else 0
            )
            db.session.add(closure)
            db.session.commit()
        except sqlalchemy.exc.IntegrityError as e1:
            raise Conflict("Category already exists")
        except Exception as e:
            raise e
        return category

    @staticmethod
    def add_category_binding(
        category_id: int, target_id: str,target_type:str, account_id: uuid = None
    ) -> DictBinding:
        try:
            if DictService.get_category_by_id(category_id) is None:
                raise NotFound("Category not found")
            binding = DictBinding(category_id=category_id, target_id=target_id)
            if target_type: 
                binding.target_type = target_type
            if account_id:
                account_id = str(account_id)
                binding.created_by = account_id

            db.session.add(binding)
            db.session.commit()
        except Exception as e:
            raise e
        return binding

    @staticmethod
    def delete_category(category_id: int) -> None:
        try:
            category = DictService.get_category_by_id(category_id)
            if category is None:
                raise NotFound("Category not found")
            db.session.delete(category)
            db.session.query(DictCategoryClosure).filter(
                DictCategoryClosure.child_id == category_id
            ).delete()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def unbinding_category_object(binding_id:int,category_id: int, target_id: str) -> None:
        try:
            amount = 0
            bind_objs = None
            if binding_id:
                bind_obj = db.session.query(DictBinding).filter(DictBinding.id == binding_id).one_or_none()
            elif category_id and target_id:
                bind_obj = (
                    db.session.query(DictBinding)
                    .filter(
                        DictBinding.category_id == category_id,
                        DictBinding.target_id == target_id,
                    )
                    .one_or_none()
                )
            elif category_id:
                bind_objs = (
                    db.session.query(DictBinding)
                    .filter(DictBinding.category_id == category_id)
                    .all()
                )
            elif target_id:
                bind_objs = (
                    db.session.query(DictBinding)
                    .filter(DictBinding.target_id == target_id)
                    .all()
                )
            if not bind_obj and not bind_objs:
                raise NotFound("bind_obj not found")
            if bind_obj:
                db.session.delete(bind_obj)
                amount = 1
            if bind_objs:
                amount = len(bind_objs)
                for bind_obj in bind_objs:
                    db.session.delete(bind_obj)
            db.session.commit()
        except Exception as e:
            raise e
        return amount
