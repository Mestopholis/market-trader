from uuid import uuid4


def new_domain_id(prefix: str) -> str:
    if not prefix or "_" in prefix:
        raise ValueError("prefix must be non-empty and must not contain underscores")
    return f"{prefix}_{uuid4().hex}"
