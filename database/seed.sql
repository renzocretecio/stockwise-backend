BEGIN;

-- =========================================================
-- Fixed IDs for repeatable local development data
-- =========================================================

-- Business
INSERT INTO businesses (
    id, name, slug, email, phone, address, currency_code, timezone
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Stockwise Demo Store',
    'stockwise-demo',
    'demo@stockwise.local',
    '+63 900 000 0000',
    'San Pedro, Laguna, Philippines',
    'PHP',
    'Asia/Manila'
)
ON CONFLICT (id) DO NOTHING;

-- Users
-- Replace password_hash with a real Argon2 hash before testing login.
INSERT INTO users (
    id, email, password_hash, first_name, last_name
) VALUES
(
    '00000000-0000-0000-0000-000000000101',
    'owner@stockwise.local',
    'demo-password-hash',
    'Demo',
    'Owner'
),
(
    '00000000-0000-0000-0000-000000000102',
    'clerk@stockwise.local',
    'demo-password-hash',
    'Demo',
    'Clerk'
)
ON CONFLICT (id) DO NOTHING;

-- Global roles
INSERT INTO roles (id, name, description, is_system_role)
VALUES
(
    '00000000-0000-0000-0000-000000000201',
    'owner',
    'Full access to the business',
    TRUE
),
(
    '00000000-0000-0000-0000-000000000202',
    'manager',
    'Inventory, sales, purchases, suppliers, and reports',
    TRUE
),
(
    '00000000-0000-0000-0000-000000000203',
    'clerk',
    'Sales and limited inventory access',
    TRUE
)
ON CONFLICT (id) DO NOTHING;

-- User memberships
INSERT INTO business_memberships (
    id, business_id, user_id, role_id, status, joined_at
) VALUES
(
    '00000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000101',
    '00000000-0000-0000-0000-000000000201',
    'active',
    NOW()
),
(
    '00000000-0000-0000-0000-000000000302',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000102',
    '00000000-0000-0000-0000-000000000203',
    'active',
    NOW()
)
ON CONFLICT (id) DO NOTHING;

-- =========================================================
-- Suppliers
-- =========================================================

INSERT INTO suppliers (
    id, business_id, name, contact_person, email, phone, lead_time_days
) VALUES
(
    '00000000-0000-0000-0000-000000000401',
    '00000000-0000-0000-0000-000000000001',
    'Laguna Wholesale Supply',
    'Ana Santos',
    'orders@lagunawholesale.local',
    '+63 917 111 1111',
    3
),
(
    '00000000-0000-0000-0000-000000000402',
    '00000000-0000-0000-0000-000000000001',
    'Metro General Trading',
    'Mark Reyes',
    'sales@metrotrading.local',
    '+63 917 222 2222',
    7
)
ON CONFLICT (id) DO NOTHING;

-- =========================================================
-- Products
-- =========================================================

INSERT INTO products (
    id,
    business_id,
    supplier_id,
    sku,
    barcode,
    name,
    normalized_name,
    description,
    category,
    brand,
    unit,
    cost_price,
    selling_price,
    reorder_point,
    safety_stock,
    lead_time_days,
    is_perishable
) VALUES
(
    '00000000-0000-0000-0000-000000000501',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000401',
    'BEV-WATER-500',
    '480000000001',
    'Bottled Water 500ml',
    'bottled water 500ml',
    '500ml bottled drinking water',
    'Beverages',
    'Generic',
    'bottle',
    8.00,
    12.00,
    30,
    10,
    3,
    FALSE
),
(
    '00000000-0000-0000-0000-000000000502',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000401',
    'BEV-COKE-1500',
    '480000000002',
    'Coca-Cola 1.5L',
    'coca cola 1 5l',
    'Carbonated soft drink',
    'Beverages',
    'Coca-Cola',
    'bottle',
    48.50,
    65.00,
    20,
    8,
    3,
    FALSE
),
(
    '00000000-0000-0000-0000-000000000503',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000402',
    'FOOD-TUNA-155',
    '480000000003',
    'Century Tuna 155g',
    'century tuna 155g',
    'Canned tuna',
    'Canned Goods',
    'Century',
    'can',
    32.00,
    45.00,
    15,
    5,
    7,
    TRUE
),
(
    '00000000-0000-0000-0000-000000000504',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000402',
    'FOOD-COFFEE-250',
    '480000000004',
    'Organic Coffee Beans 250g',
    'organic coffee beans 250g',
    'Roasted coffee beans',
    'Beverages',
    'Local Roaster',
    'pack',
    180.00,
    250.00,
    10,
    3,
    7,
    TRUE
),
(
    '00000000-0000-0000-0000-000000000505',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000401',
    'CARE-SOAP-90',
    '480000000005',
    'Bath Soap 90g',
    'bath soap 90g',
    'Personal care soap',
    'Personal Care',
    'Sample Brand',
    'bar',
    22.00,
    32.00,
    12,
    4,
    3,
    FALSE
),
(
    '00000000-0000-0000-0000-000000000506',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000402',
    'ELEC-EARBUDS-01',
    '480000000006',
    'Wireless Earbuds',
    'wireless earbuds',
    'Bluetooth wireless earbuds',
    'Electronics',
    'Sample Tech',
    'piece',
    350.00,
    599.00,
    8,
    2,
    7,
    FALSE
),
(
    '00000000-0000-0000-0000-000000000507',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000402',
    'ELEC-CASE-01',
    '480000000007',
    'Phone Case',
    'phone case',
    'Universal phone case',
    'Electronics',
    'Generic',
    'piece',
    40.00,
    99.00,
    10,
    2,
    7,
    FALSE
)
ON CONFLICT (id) DO NOTHING;

-- =========================================================
-- Initial stock balances
-- =========================================================

INSERT INTO stock_balances (
    id,
    business_id,
    product_id,
    quantity,
    reserved_quantity,
    average_cost
) VALUES
(
    '00000000-0000-0000-0000-000000000601',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000501',
    18,
    0,
    8.00
),
(
    '00000000-0000-0000-0000-000000000602',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000502',
    14,
    0,
    48.50
),
(
    '00000000-0000-0000-0000-000000000603',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000503',
    8,
    0,
    32.00
),
(
    '00000000-0000-0000-0000-000000000604',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000504',
    42,
    0,
    180.00
),
(
    '00000000-0000-0000-0000-000000000605',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000505',
    35,
    0,
    22.00
),
(
    '00000000-0000-0000-0000-000000000606',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000506',
    4,
    0,
    350.00
),
(
    '00000000-0000-0000-0000-000000000607',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000507',
    200,
    0,
    40.00
)
ON CONFLICT (business_id, product_id) DO UPDATE SET
    quantity = EXCLUDED.quantity,
    average_cost = EXCLUDED.average_cost,
    updated_at = NOW();

-- =========================================================
-- Stock movement history
-- =========================================================

INSERT INTO stock_movements (
    id, business_id, product_id, movement_type, quantity,
    unit_cost, reason, notes, created_by, created_at
) VALUES
('00000000-0000-0000-0000-000000000701', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000501', 'purchase', 100, 8.00, 'initial_stock', 'Initial demo stock', '00000000-0000-0000-0000-000000000101', NOW() - INTERVAL '20 days'),
('00000000-0000-0000-0000-000000000702', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000501', 'sale', -82, 8.00, 'sale', 'Demo sales history', '00000000-0000-0000-0000-000000000102', NOW() - INTERVAL '1 day'),
('00000000-0000-0000-0000-000000000703', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000502', 'purchase', 40, 48.50, 'initial_stock', 'Initial demo stock', '00000000-0000-0000-0000-000000000101', NOW() - INTERVAL '20 days'),
('00000000-0000-0000-0000-000000000704', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000502', 'sale', -26, 48.50, 'sale', 'Demo sales history', '00000000-0000-0000-0000-000000000102', NOW() - INTERVAL '1 day'),
('00000000-0000-0000-0000-000000000705', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000503', 'purchase', 20, 32.00, 'initial_stock', 'Initial demo stock', '00000000-0000-0000-0000-000000000101', NOW() - INTERVAL '20 days'),
('00000000-0000-0000-0000-000000000706', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000503', 'sale', -12, 32.00, 'sale', 'Demo sales history', '00000000-0000-0000-0000-000000000102', NOW() - INTERVAL '1 day'),
('00000000-0000-0000-0000-000000000707', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000504', 'purchase', 50, 180.00, 'initial_stock', 'Initial demo stock', '00000000-0000-0000-0000-000000000101', NOW() - INTERVAL '90 days'),
('00000000-0000-0000-0000-000000000708', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000504', 'sale', -8, 180.00, 'sale', 'Slow moving product', '00000000-0000-0000-0000-000000000102', NOW() - INTERVAL '45 days'),
('00000000-0000-0000-0000-000000000709', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000506', 'purchase', 10, 350.00, 'initial_stock', 'Initial demo stock', '00000000-0000-0000-0000-000000000101', NOW() - INTERVAL '10 days'),
('00000000-0000-0000-0000-000000000710', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000506', 'sale', -6, 350.00, 'sale', 'Fast moving product', '00000000-0000-0000-0000-000000000102', NOW() - INTERVAL '1 day')
ON CONFLICT (id) DO NOTHING;

-- =========================================================
-- Physical inventory count with discrepancy
-- =========================================================

INSERT INTO inventory_counts (
    id, business_id, status, count_date, notes, created_by, finalized_by, finalized_at
) VALUES (
    '00000000-0000-0000-0000-000000000801',
    '00000000-0000-0000-0000-000000000001',
    'finalized',
    CURRENT_DATE,
    'Demo physical count with one unusual variance',
    '00000000-0000-0000-0000-000000000101',
    '00000000-0000-0000-0000-000000000101',
    NOW()
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO inventory_count_items (
    id, inventory_count_id, product_id, expected_quantity,
    counted_quantity, notes, counted_at
) VALUES
(
    '00000000-0000-0000-0000-000000000901',
    '00000000-0000-0000-0000-000000000801',
    '00000000-0000-0000-0000-000000000501',
    18, 18, 'Count matches expected quantity', NOW()
),
(
    '00000000-0000-0000-0000-000000000902',
    '00000000-0000-0000-0000-000000000801',
    '00000000-0000-0000-0000-000000000504',
    42, 30, 'Unusual variance for review', NOW()
)
ON CONFLICT (id) DO NOTHING;

-- =========================================================
-- Audit log
-- =========================================================

INSERT INTO audit_logs (
    business_id, user_id, action, entity_type, entity_id, new_values
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000101',
    'demo.seeded',
    'business',
    '00000000-0000-0000-0000-000000000001',
    '{"source": "seed.sql", "environment": "development"}'::jsonb
);

COMMIT;