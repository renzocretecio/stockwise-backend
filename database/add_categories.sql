-- =====================================================================
-- Seed 20 product categories
-- =====================================================================

INSERT INTO categories (id, business_id, name, description, is_active, created_at)
VALUES
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Snacks', 'Chips, crackers, and snack foods', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Dairy', 'Milk, cheese, yogurt, and dairy products', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Bakery', 'Bread, pastries, and baked goods', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Frozen Foods', 'Frozen meals, ice cream, and frozen produce', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Fresh Produce', 'Fruits and vegetables', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Meat & Poultry', 'Fresh and frozen meat products', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Seafood', 'Fresh and frozen fish and seafood', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Condiments & Sauces', 'Ketchup, soy sauce, dressings, and spreads', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Grains & Pasta', 'Rice, pasta, noodles, and cereals', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Baking Supplies', 'Flour, sugar, and baking ingredients', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Household Supplies', 'Cleaning products and household essentials', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Health & Wellness', 'Vitamins, supplements, and over-the-counter medicine', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Office Supplies', 'Stationery, paper, and office essentials', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Pet Supplies', 'Pet food and accessories', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Baby Products', 'Diapers, formula, and baby care items', true, now()),
    (gen_random_uuid(), '215f1678-61eb-4901-974f-0d22901a1020', 'Alcohol & Tobacco', 'Beer, wine, spirits, and tobacco products', true, now());