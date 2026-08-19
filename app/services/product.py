from sqlmodel import Session, select
from app.models import Product, Supplier, StockBalance, Category
from decimal import Decimal
from app.models.product import Product, Supplier
from fastapi import HTTPException, status
from app.schemas.product import ProductCreate
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import joinedload

class ProductService:
    @staticmethod
    def create_product(business_id: str, payload: ProductCreate, db: Session) -> dict:
        """
        Create a new product with stock balance.
        
        Args:
            business_id: Business ID
            payload: ProductCreate schema
            db: Database session
            
        Returns:
            Product data dict
            
        Raises:
            HTTPException: If validation fails
        """
        try:
            # Validate SKU uniqueness
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
            
            # Validate barcode uniqueness
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
            
            # Validate supplier exists
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

            category_id = None
            if payload.category:
                category = db.execute(
                    select(Category).where(
                        Category.business_id == business_id,
                        Category.name == payload.category,
                        Category.is_active == True,
                    )
                ).scalar_one_or_none()

                if not category:
                    category = Category(
                        business_id=business_id,
                        name=payload.category,
                        is_active=True,
                    )
                    db.add(category)
                    db.flush()

                category_id = category.id
            
            # Validate prices
            if payload.selling_price < payload.cost_price:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selling price must be greater than or equal to cost price"
                )
            
            # Create product
            product = Product(
                business_id=business_id,
                supplier_id=payload.supplier_id,
                sku=payload.sku,
                barcode=payload.barcode,
                name=payload.name,
                normalized_name=payload.name.lower().strip(),
                category_id=category_id,
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
            db.flush()  # Get the product ID
            
            # Create stock balance
            stock_balance = StockBalance(
                business_id=business_id,
                product_id=product.id,
                quantity=Decimal("0"),
                reserved_quantity=Decimal("0"),
                average_cost=payload.cost_price,
            )
            
            db.add(stock_balance)
            db.commit()
            db.refresh(product)
            
            return ProductService._format_product_response(product)
        
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
    ) -> list:
        """Get all active products for a business"""
        query = select(Product).where(
            Product.business_id == business_id,
            Product.is_active == True
        ).options(joinedload(Product.category))

        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                (Product.normalized_name.ilike(search_term))
                | (Product.sku.ilike(search_term))
                | (Product.barcode.ilike(search_term))
            )

        if category:
            query = query.where(Product.category == category)

        # Get total count (before pagination)
        count_query = select(func.count()).select_from(query.subquery())
        total = db.execute(count_query).scalar_one()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Product.name).offset(offset).limit(page_size)

        products = db.execute(query).scalars().all()

        return products, total
    
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
        
        # Update allowed fields
        allowed_fields = {
            "name", "sku", "barcode", "category", "brand",
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
        
        return ProductService._format_product_response(product)

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
    def _format_product_response(product: Product) -> dict:
        """Format product response"""
        return {
            "id": str(product.id),
            "name": product.name,
            "sku": product.sku,
            "barcode": product.barcode,
            "category": product.category.name if product.category else None,
            "brand": product.brand,
            "unit": product.unit,
            "cost_price": float(product.cost_price),
            "selling_price": float(product.selling_price),
            "reorder_point": float(product.reorder_point),
            "safety_stock": float(product.safety_stock),
            "lead_time_days": product.lead_time_days,
            "is_perishable": product.is_perishable,
            "margin_percent": round(
                ((product.selling_price - product.cost_price) / product.cost_price * 100)
                if product.cost_price > 0 else 0,
                2
            ),
        }