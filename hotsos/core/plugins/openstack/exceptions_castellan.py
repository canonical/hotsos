
# sed -rn 's/^class\s+(\S+)\(.+/    "\1",/p' castellan/common/exception.py
CASTELLAN_EXCEPTIONS = [
    "RedirectException",
    "CastellanException",
    "Forbidden",
    "KeyManagerError",
    "ManagedObjectNotFoundError",
    "InvalidManagedObjectDictError",
    "UnknownManagedObjectTypeError",
    "AuthTypeInvalidError",
    "InsufficientCredentialDataError",
]
