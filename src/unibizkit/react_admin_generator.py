from .generators.frontend import ReactAdminGenerator
from .generators.frontend.src.resources.helpers import filter_list_fields as _filter_list_fields

ReactAdminGenerator.filter_list_fields = staticmethod(_filter_list_fields)

__all__ = ["ReactAdminGenerator"]
