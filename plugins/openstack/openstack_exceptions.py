# https://opendev.org/openstack/oslo.db/src/branch/master/oslo_db/exception.py
OSLO_DB_EXCEPTIONS = [
    "DBError",
    "DBDuplicateEntry",
    "DBConstraintError",
    "DBReferenceError",
    "DBNonExistentConstraint",
    "DBNonExistentTable",
    "DBNonExistentDatabase",
    "DBDeadlock",
    "DBInvalidUnicodeParameter",
    "DBMigrationError",
    "DBConnectionError",
    "DBDataError",
    "DBNotSupportedError",
    "InvalidSortKey",
    "ColumnError",
    "BackendNotAvailable",
    "RetryRequest",
    "NoEngineContextEstablished",
    "ContextNotRequestedError",
    "CantStartEngineError",
]

# https://opendev.org/openstack/oslo.messaging/src/branch/master/oslo_messaging/exceptions.py
OSLO_MESSAGING_EXCEPTIONS = [
    "MessagingException",
    "MessagingTimeout",
    "MessageDeliveryFailure",
    "InvalidTarget",
    "MessageUndeliverable",
]

