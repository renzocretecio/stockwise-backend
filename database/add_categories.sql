INSERT INTO categories (
    business_id,
    name,
    description
)
VALUES
(
    '215f1678-61eb-4901-974f-0d22901a1020',
    'Beverages',
    'Drinks and beverage products'
),
(
    '215f1678-61eb-4901-974f-0d22901a1020',
    'Canned Goods',
    'Canned food products'
),
(
    '215f1678-61eb-4901-974f-0d22901a1020',
    'Personal Care',
    'Personal care products'
),
(
    '215f1678-61eb-4901-974f-0d22901a1020',
    'Electronics',
    'Electronic products and accessories'
)
ON CONFLICT (business_id, name) DO NOTHING;