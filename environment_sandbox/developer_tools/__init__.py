"""Source-checkout-only developer tooling infrastructure."""

__all__ = ["DeveloperToolsController"]


def __getattr__(name: str):
    # Keep non-UI services (including startup object overrides) usable without
    # eagerly importing pygame and constructing the entire tools UI.
    if name == "DeveloperToolsController":
        from .controller import DeveloperToolsController
        return DeveloperToolsController
    raise AttributeError(name)
