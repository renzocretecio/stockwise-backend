"""Canonical KitaStock roles and permissions.

Permissions are global identifiers. Roles are created per business so a user
can have a different role in every business they belong to.
"""

PERMISSIONS: dict[str, str] = {
    "products.read": "View products and categories",
    "products.create": "Create products and categories",
    "products.update": "Update products and categories",
    "products.archive": "Archive products and categories",
    "products.delete": "Delete products",
    "inventory.read": "View stock balances and movements",
    "inventory.adjust": "Create stock adjustments",
    "inventory.count": "Manage physical inventory counts",
    "sales.read": "View sales and returns",
    "sales.create": "Create sales",
    "sales.return": "Create sales returns",
    "sales.void": "Void completed sales",
    "purchases.read": "View purchase orders",
    "purchases.create": "Create and update purchase orders",
    "purchases.receive": "Receive purchase orders",
    "purchases.cancel": "Cancel purchase orders",
    "suppliers.read": "View suppliers",
    "suppliers.create": "Create suppliers",
    "suppliers.update": "Update suppliers",
    "suppliers.archive": "Archive suppliers",
    "reports.read": "View dashboards, reports, and intelligence",
    "reports.export": "Export report and dashboard data",
    "reports.summarize": "Generate AI report summaries",
    "business.read": "View business settings",
    "business.update": "Update business settings",
    "members.read": "View members, invitations, and roles",
    "members.invite": "Invite and revoke member invitations",
    "members.update_role": "Change member roles and access",
    "members.remove": "Suspend or remove members",
    "billing.read": "View subscription and usage",
    "billing.manage": "Manage the business subscription",
    "notifications.manage": "Manage business notifications",
    "storefront.read": "View public store settings and customer orders",
    "storefront.manage": "Manage the public store and published products",
    "storefront.orders": "Confirm and fulfill public store orders",
}

OPERATIONAL_PERMISSIONS = {
    key
    for key in PERMISSIONS
    if not key.startswith(("billing.", "members."))
    and key not in {"business.update", "notifications.manage"}
}

SYSTEM_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": set(PERMISSIONS),
    "manager": OPERATIONAL_PERMISSIONS
    | {
        "billing.read",
        "members.read",
    },
    "cashier": {
        "products.read",
        "inventory.read",
        "sales.read",
        "sales.create",
        "sales.return",
        "storefront.read",
        "storefront.orders",
    },
    "stock clerk": {
        "products.read",
        "products.create",
        "products.update",
        "inventory.read",
        "inventory.adjust",
        "inventory.count",
        "purchases.read",
        "purchases.receive",
        "suppliers.read",
        "storefront.read",
    },
}

SYSTEM_ROLE_DESCRIPTIONS = {
    "owner": "Full access, including billing and member management",
    "manager": "Manage daily operations and view business reports",
    "cashier": "Create sales and view the stock needed for checkout",
    "stock clerk": "Receive, count, and adjust inventory",
}
