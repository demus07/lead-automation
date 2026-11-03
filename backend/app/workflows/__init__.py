_loaded = False


def load_workflows() -> None:
    """Import workflow modules so they register with the engine."""
    global _loaded
    if _loaded:
        return
    from app.workflows import definitions  # noqa: F401

    _loaded = True
