import uuid

from sqlalchemy import text
from werkzeug.exceptions import NotFound

from extensions.ext_database import db
from models.dc_models import DictCategory, DictBinding, DictCategoryClosure


class DictService:

    @staticmethod
    def to_tree_with_bindings(data, parent_id: int = None):
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "key": row["key"],
                "parentId": row["parent_id"],
                "level": row["level"],
                "objects": DictService.get_category_bindings(row["id"]),
                "children": DictService.to_tree(data, row["id"]),
            }
            for row in data
            if row["parent_id"] == parent_id
        ]

    @staticmethod
    def to_tree(data, parent_id: int = None):
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "key": row["key"],
                "parentId": row["parent_id"],
                "level": row["level"],
                "children": DictService.to_tree(data, row["id"]),
            }
            for row in data
            if row["parent_id"] == parent_id
        ]

    @staticmethod
    def get_category_tree(root_id: int, with_bindings: bool = False) -> dict:
        query = text(
            """
        WITH RECURSIVE category_tree AS (
                SELECT id, name,key, NULL::INT as parent_id, 0 as level
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
            return DictService.to_tree_with_bindings(result)
        else:
            return DictService.to_tree(result)

    @staticmethod
    def get_category_type_count(tenant_id: str) -> int:
        try:
            count = (
                db.session.query(DictCategory)
                .outerjoin(
                    DictCategoryClosure, DictCategory.id == DictCategoryClosure.child_id
                )
                .filter(
                    DictCategory.tenant_id == tenant_id,
                    DictCategoryClosure.parent_id == None,
                )
                .count()
            )
        except Exception as e:
            raise e
        return count

    @staticmethod
    def get_category_types(tenant_id: str) -> list[DictCategory]:
        try:
            roots = (
                db.session.query(DictCategory)
                .outerjoin(
                    DictCategoryClosure, DictCategory.id == DictCategoryClosure.child_id
                )
                .filter(
                    DictCategory.tenant_id == tenant_id,
                    DictCategoryClosure.parent_id == None,
                )
                .all()
            )
        except Exception as e:
            raise e
        return roots

    @staticmethod
    def get_category_childs(category_id: int) -> list[DictCategory]:
        try:
            categories = (
                db.session.query(DictCategory,DictCategoryClosure).outerjoin(DictCategory.id == DictCategoryClosure.child_id)\
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
        tenant_id: str, name: str, key: str, parent_id: int = None,account_id:uuid=None
    ) -> DictCategory:
        try:
            category = DictCategory(
                tenant_id=tenant_id,
                name=name,
                key=key,
                parent_id=parent_id if parent_id else None,
                created_by=str(account_id) if account_id else None,
            )
            db.session.add(category)
            db.session.commit()
            if parent_id:
                closure = DictCategoryClosure(
                    category_id=category.id, parent_id=parent_id
                )
                db.session.add(closure)
            db.session.commit()
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
