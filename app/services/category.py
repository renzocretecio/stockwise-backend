from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    @staticmethod
    def create_category(business_id: str, payload: CategoryCreate, db: Session) -> dict:
        """Create a new category"""
        try:
            existing = db.execute(
                select(Category).where(
                    Category.business_id == business_id,
                    Category.name == payload.name,
                    Category.is_active == True,
                )
            ).scalar_one_or_none()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Category '{payload.name}' already exists",
                )

            category = Category(
                business_id=business_id,
                name=payload.name,
                description=payload.description,
                is_active=True,
            )

            db.add(category)
            db.commit()
            db.refresh(category)

            return CategoryService._format_category_response(category)

        except HTTPException:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category creation failed: Database constraint violation",
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Category creation failed: {str(e)}",
            )

    @staticmethod
    def get_categories(
            business_id: str,
            db: Session,
            page: int = 1,
            page_size: int = 10,
            search: str | None = None,
            paginate: bool = True,
        ) -> tuple[list, int]:
        """
        Get categories for a business.
        
        If paginate=True (default), returns a page of results + total count.
        If paginate=False, returns ALL matching categories (ignores page/page_size).
        """
        query = select(Category).where(
            Category.business_id == business_id,
            Category.is_active == True
        )

        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                Category.name.ilike(search_term)
            )

        query = query.order_by(Category.name)

        if not paginate:
            categories = db.execute(query).scalars().all()
            return categories, len(categories)

        count_query = select(func.count()).select_from(query.subquery())
        total = db.execute(count_query).scalar_one()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        categories = db.execute(query).scalars().all()

        return categories, total

    @staticmethod
    def get_category(business_id: str, category_id: str, db: Session) -> dict:
        """Get a single category"""
        category = db.execute(
            select(Category).where(
                Category.business_id == business_id,
                Category.id == category_id,
            )
        ).scalar_one_or_none()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        return CategoryService._format_category_response(category)

    @staticmethod
    def update_category(
        business_id: str, category_id: str, payload: CategoryUpdate, db: Session
    ) -> dict:
        """Update a category"""
        category = db.execute(
            select(Category).where(
                Category.business_id == business_id,
                Category.id == category_id,
            )
        ).scalar_one_or_none()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        update_data = payload.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] != category.name:
            existing = db.execute(
                select(Category).where(
                    Category.business_id == business_id,
                    Category.name == update_data["name"],
                    Category.is_active == True,
                    Category.id != category_id,
                )
            ).scalar_one_or_none()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Category '{update_data['name']}' already exists",
                )

        for field, value in update_data.items():
            setattr(category, field, value)

        db.add(category)
        db.commit()
        db.refresh(category)

        return CategoryService._format_category_response(category)

    @staticmethod
    def soft_delete_category(business_id: str, category_id: str, db: Session) -> dict:
        """Soft delete a category"""
        category = db.execute(
            select(Category).where(
                Category.business_id == business_id,
                Category.id == category_id,
            )
        ).scalar_one_or_none()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        category.is_active = False
        db.add(category)
        db.commit()

        return {"success": True, "message": "Category deleted"}

    @staticmethod
    def _format_category_response(category: Category) -> dict:
        """Format category response"""
        return {
            "id": str(category.id),
            "business_id": str(category.business_id),
            "name": category.name,
            "description": category.description,
            "is_active": category.is_active,
        }