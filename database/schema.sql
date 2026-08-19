BEGIN;

ALTER TABLE users
    DROP CONSTRAINT IF EXISTS fk_users_business;

ALTER TABLE users
    DROP CONSTRAINT IF EXISTS uq_users_business_email;

ALTER TABLE users
    DROP COLUMN IF EXISTS business_id;

ALTER TABLE users
    ADD CONSTRAINT uq_users_email
    UNIQUE (email);

CREATE TABLE business_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL,
    user_id UUID NOT NULL,
    role_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    invited_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_memberships_business
        FOREIGN KEY (business_id)
        REFERENCES businesses(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_memberships_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_memberships_role
        FOREIGN KEY (role_id)
        REFERENCES roles(id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_memberships_status
        CHECK (
            status IN (
                'invited',
                'active',
                'suspended',
                'removed'
            )
        ),

    CONSTRAINT uq_memberships_business_user
        UNIQUE (business_id, user_id)
);

INSERT INTO business_memberships (
    business_id,
    user_id,
    role_id,
    status
)
SELECT
    u.business_id,
    u.id,
    ur.role_id,
    CASE
        WHEN u.is_active THEN 'active'
        ELSE 'suspended'
    END
FROM users u
JOIN user_roles ur
    ON ur.user_id = u.id;

DROP TABLE user_roles;

CREATE INDEX idx_users_email
    ON users(email);

CREATE INDEX idx_memberships_user
    ON business_memberships(user_id);

CREATE INDEX idx_memberships_business
    ON business_memberships(business_id);

COMMIT;