from sqlmodel import Session, select
from app.models import Product, Supplier, StockBalance, Category
from decimal import Decimal
from fastapi import HTTPException, status
from app.schemas.product import ProductCreate
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

class ProductService:
    @staticmethod
    def create_product(business_id: str, payload: ProductCreate, db: Session) -> dict:
        """
        Create a new product with stock balance using strict foreign key validation.
        
        Args:
            business_id: Business ID
            payload: ProductCreate schema (expects payload.category_id)
            db: Database session
            
        Returns:
            Product data dict
            
        Raises:
            HTTPException: If validation fails
        """
        try:
            # 1. Validate SKU uniqueness within the business scope
            if payload.sku:
                existing_sku = db.execute(
                    select(Product).where(
                        Product.business_id == business_id,
                        Product.sku == payload.sku
                    )
                ).scalar_one_or_none()
                
                if existing_sku:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"SKU '{payload.sku}' already exists in this business"
                    )
            
            # 2. Validate barcode uniqueness within the business scope
            if payload.barcode:
                existing_barcode = db.execute(
                    select(Product).where(
                        Product.business_id == business_id,
                        Product.barcode == payload.barcode
                    )
                ).scalar_one_or_none()
                
                if existing_barcode:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Barcode '{payload.barcode}' already exists in this business"
                    )
            
            # 3. Validate supplier exists and belongs to this business
            if payload.supplier_id:
                supplier = db.execute(
                    select(Supplier).where(
                        Supplier.id == payload.supplier_id,
                        Supplier.business_id == business_id
                    )
                ).scalar_one_or_none()
                
                if not supplier:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Supplier not found"
                    )

            # 4. Explicit Category ID Validation (Industry Standard Refactor)
            if payload.category_id:
                category = db.execute(
                    select(Category).where(
                        Category.id == payload.category_id,
                        Category.business_id == business_id,
                        Category.is_active == True,
                    )
                ).scalar_one_or_none()

                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Category not found or is inactive"
                    )
            
            # 5. Validate business pricing integrity rules
            if payload.selling_price < payload.cost_price:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selling price must be greater than or equal to cost price"
                )
            
            # 6. Create product entity
            product = Product(
                business_id=business_id,
                supplier_id=payload.supplier_id,
                category_id=payload.category_id,
                sku=payload.sku,
                barcode=payload.barcode,
                name=payload.name,
                description=payload.description,
                normalized_name=payload.name.lower().strip(),
                brand=payload.brand,
                unit=payload.unit,
                cost_price=payload.cost_price,
                selling_price=payload.selling_price,
                reorder_point=payload.reorder_point,
                safety_stock=payload.safety_stock,
                lead_time_days=payload.lead_time_days,
                is_perishable=payload.is_perishable,
                is_active=True,
            )
            
            db.add(product)
            db.flush()
            
            # 7. Create companion stock balance entity tracking
            stock_balance = StockBalance(
                business_id=business_id,
                product_id=product.id,
                quantity=Decimal("0"),
                reserved_quantity=Decimal("0"),
                average_cost=payload.cost_price,
            )
            
            db.add(stock_balance)
            db.commit()
            
            # Eager load relationships explicitly for the final response serializer
            from sqlalchemy.orm import joinedload
            db.refresh(
                product, 
                attribute_names=["supplier", "category", "stock_balance"]
            )
            
            return ProductService._format_product_response(product, product.stock_balance)
        
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product creation failed: Database constraint violation"
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Product creation failed: {str(e)}"
            )
    
    @staticmethod
    def get_products(
        business_id: str,
        db: Session,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        category: str | None = None,
        stock_status: str | None = None,
    ) -> list:
        """Get all active products for a business"""
        query = (
            select(Product)
            .outerjoin(StockBalance, StockBalance.product_id == Product.id)
            .where(
                Product.business_id == business_id,
                Product.is_active == True,
            )
            .options(joinedload(Product.category))
        )

        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                (Product.normalized_name.ilike(search_term))
                | (Product.sku.ilike(search_term))
                | (Product.barcode.ilike(search_term))
            )

        if category:
            query = query.join(Category, Category.id == Product.category_id).where(
                func.lower(Category.name) == category.strip().lower()
            )

        available_quantity = func.coalesce(StockBalance.quantity, 0)
        if stock_status == "out_of_stock":
            query = query.where(available_quantity <= 0)
        elif stock_status == "low_stock":
            query = query.where(
                and_(
                    available_quantity > 0,
                    available_quantity <= Product.reorder_point,
                )
            )
        elif stock_status == "in_stock":
            query = query.where(available_quantity > Product.reorder_point)

        # Get total count (before pagination)
        count_query = select(func.count()).select_from(query.subquery())
        total = db.execute(count_query).scalar_one()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Product.name).offset(offset).limit(page_size)

        products = db.execute(query).scalars().all()

        product_ids = [p.id for p in products]
        stock_balances = db.execute(
            select(StockBalance).where(StockBalance.product_id.in_(product_ids))
        ).scalars().all()
        stock_by_product = {sb.product_id: sb for sb in stock_balances}

        return [
            ProductService._format_product_response(p, stock_by_product.get(p.id))
            for p in products
        ], total
    
    @staticmethod
    def get_product(business_id: str, product_id: str, db: Session) -> dict:
        """Get a single product"""
        product = db.execute(
            select(Product).where(
                Product.business_id == business_id,
                Product.id == product_id,
                Product.is_active == True
            )
        ).scalar_one_or_none()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        return ProductService._format_product_response(product)

    @staticmethod
    def update_product(business_id: str, product_id: str, payload: dict, db: Session) -> dict:
        """Update a product"""
        # Use joinedload to fetch relationships and stock_balance upfront safely
        from sqlalchemy.orm import joinedload
        
        product = db.execute(
            select(Product)
            .options(
                joinedload(Product.stock_balance),
                joinedload(Product.supplier),
                joinedload(Product.category)
            )
            .where(
                Product.business_id == business_id,
                Product.id == product_id
            )
        ).scalar_one_or_none()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        allowed_fields = {
            "name", "sku", "barcode", "category_id", "brand", "description",
            "unit", "cost_price", "selling_price",
            "reorder_point", "safety_stock", "lead_time_days", "is_perishable"
        }
        
        for field, value in payload.items():
            if field in allowed_fields and value is not None:
                if field == "name":
                    product.normalized_name = value.lower().strip()
                setattr(product, field, value)
        
        db.add(product)
        db.commit()
        db.refresh(product)

        return ProductService._format_product_response(product, product.stock_balance)

    @staticmethod
    def soft_delete_product(business_id: str, product_id: str, db: Session) -> dict:
        """Soft delete a product"""
        product = db.execute(
            select(Product).where(
                Product.business_id == business_id,
                Product.id == product_id
            )
        ).scalar_one_or_none()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        product.is_active = False
        db.add(product)
        db.commit()
        
        return {"success": True, "message": "Product deleted"}

    @staticmethod
    def get_product_overall_status(business_id: str, db:Session) -> list:
        """Get counts of total, in-stock, low-stock, and out-of-stock products"""
        rows = db.execute(
            select(StockBalance, Product)
            .join(Product, Product.id == StockBalance.product_id)
            .where(
                Product.business_id == business_id,
                Product.is_active == True,
            )
        ).all()

        total_products = len(rows)
        in_stock_count = 0
        low_stock_count = 0
        out_of_stock_count = 0

        for stock_balance, product in rows:
            if stock_balance.quantity <= 0:
                out_of_stock_count += 1
            elif stock_balance.quantity <= product.reorder_point:
                low_stock_count += 1
            else:
                in_stock_count += 1

        return {
            "total_products": total_products,
            "in_stock": in_stock_count,
            "low_stock": low_stock_count,
            "out_of_stock": out_of_stock_count,
        }

    @staticmethod
    def _format_product_response(product: Product, stock_balance: StockBalance | None = None) -> dict:
        """Format product response with all columns"""
        quantity = float(stock_balance.quantity) if stock_balance else 0.0

        if quantity <= 0:
            stock_status = "out_of_stock"
        elif quantity <= float(product.reorder_point):
            stock_status = "low_stock"
        else:
            stock_status = "in_stock"

        return {
            "id": str(product.id),
            "business_id": str(product.business_id),
            "supplier_id": str(product.supplier_id) if product.supplier_id else None,
            "supplier_name": product.supplier.name if product.supplier else None,
            "category_id": str(product.category_id) if product.category_id else None,
            "category_name": product.category.name if product.category else None,
            "sku": product.sku,
            "barcode": product.barcode,
            "name": product.name,
            "normalized_name": product.normalized_name,
            "description": product.description,
            "brand": product.brand,
            "unit": product.unit,
            "cost_price": float(product.cost_price),
            "selling_price": float(product.selling_price),
            "reorder_point": float(product.reorder_point),
            "safety_stock": float(product.safety_stock),
            "lead_time_days": product.lead_time_days,
            "is_perishable": product.is_perishable,
            "is_active": product.is_active,
            "margin_percent": round(
                ((product.selling_price - product.cost_price) / product.cost_price * 100)
                if product.cost_price > 0 else 0,
                2
            ),
            "quantity": quantity,                # ← NEW
            "stock_status": stock_status,        # ← NEW
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
        }
