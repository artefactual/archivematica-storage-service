"""DataTable utils

Implements the server-side processing options needed by the jQuery
DataTables v1.9 library used in the packages tables of the storage
service (in the Packages and the Location detail views).

The request and response details are documented in:
http://legacy.datatables.net/usage/server-side
"""

import os

from django.db.models import Q
from django.utils import timezone

from .models import FixityLog
from .models import Package


class PackageDataTable:
    """This class parses the parameters sent by the JS client code and
    builds a filtered and sorted list of `Package` objects.
    """

    # number of records to display on a single page when using pagination
    DEFAULT_DISPLAY_LENGTH = 10

    model = Package

    # the columns represented by these indexes can be sorted
    # through the queryset using the order_by method
    ORDER_BY_MAPPING = {
        0: "uuid",
        1: "origin_pipeline__description",
        3: "size",
        5: "replicated_package__uuid",
    }

    # these columns instead can't be sorted directly with the
    # queryset so the queryset needs to be converted into a list
    # and then sorted using helper methods
    SORT_KEY_HELPERS_MAPPING = {
        2: "sort_by_full_path_key",
        4: "sort_by_package_type_key",
        6: "sort_by_status_key",
        7: "sort_by_fixity_date_key",
        8: "sort_by_fixity_status_key",
    }

    def __init__(self, query_dict):
        search_filter = Q()
        location_uuid = query_dict.get("location-uuid")
        if location_uuid:
            search_filter = Q(current_location=location_uuid)
        self.total_records = self.model.objects.filter(search_filter).count()
        self.params = self.parse_datatable_parameters(query_dict)
        self.echo = self.params["echo"]
        if self.params["search"]:
            search = self.params["search"]
            # remove any leading slashes so we can search in relative paths
            search_as_path = search.lstrip(os.path.sep)
            search_filter &= (
                Q(uuid__icontains=search)
                | Q(description__icontains=search)
                | Q(origin_pipeline__uuid__icontains=search)
                | Q(origin_pipeline__description__icontains=search)
                | Q(current_location__relative_path__icontains=search_as_path)
                | Q(current_location__space__path__icontains=search_as_path)
                | Q(current_path__icontains=search_as_path)
                | Q(package_type__icontains=search)
                | Q(status__icontains=search)
                | Q(replicas__uuid__icontains=search)
                | Q(replicated_package__uuid__icontains=search)
            )
        queryset = self.model.objects.filter(search_filter).distinct()
        self.total_display_records = queryset.count()
        self.records = self.get_records(queryset)

    def _get_int_parameter(self, query_dict, param, default=0):
        """Get an integer parameter from the request QueryDict.

        Return `default` on failure
        """
        try:
            return int(query_dict.get(param))
        except (ValueError, TypeError):
            return default

    def sorting_column(self, query_dict):
        """Return a dictionary with the column index and sorting direction of
        the column used for sorting the table.

        The DataTable library can sort by multiple columns but this
        implementation is very simple and limited to a single column sort.
        """
        result = {}
        sorting_columns_count = self._get_int_parameter(query_dict, "iSortingCols")
        if sorting_columns_count == 1:
            sorting_column_index = self._get_int_parameter(
                query_dict, "iSortCol_0", None
            )
            if sorting_column_index is not None:
                is_sortable = (
                    query_dict.get(f"bSortable_{sorting_column_index}") == "true"
                )
                if is_sortable:
                    sort_direction = query_dict.get("sSortDir_0", "asc")
                    result = {
                        "index": sorting_column_index,
                        "direction": sort_direction,
                    }
        return result

    def parse_datatable_parameters(self, query_dict):
        return {
            # query for text based search
            "search": query_dict.get("sSearch", ""),
            # options for limiting result display
            "display_start": self._get_int_parameter(query_dict, "iDisplayStart"),
            "display_length": self._get_int_parameter(
                query_dict, "iDisplayLength", default=self.DEFAULT_DISPLAY_LENGTH
            ),
            # sorting information
            "sorting_column": self.sorting_column(query_dict),
            # parameter sent by the client that the server needs
            # to return back in order to identify each single rendering
            "echo": self._get_int_parameter(query_dict, "sEcho", default=-1),
        }

    def sort(self, queryset):
        sorting_column = self.params["sorting_column"]
        if not sorting_column or sorting_column.get("index") is None:
            return queryset
        sort_descending = sorting_column.get("direction") == "desc"
        if sorting_column["index"] in self.ORDER_BY_MAPPING:
            field = self.ORDER_BY_MAPPING[sorting_column["index"]]
            if sort_descending:
                field = f"-{field}"
            return queryset.order_by(field)
        elif sorting_column["index"] in self.SORT_KEY_HELPERS_MAPPING:
            sorting_method_name = self.SORT_KEY_HELPERS_MAPPING[sorting_column["index"]]
            sorting_method = getattr(self, sorting_method_name)
            return sorted(list(queryset), key=sorting_method, reverse=sort_descending)
        else:
            return queryset

    def get_records(self, queryset):
        result = self.sort(queryset)
        display_start = self.params["display_start"]
        display_length = self.params["display_length"]
        try:
            return result[display_start : (display_start + display_length)]
        except IndexError:
            return []

    def sort_by_full_path_key(self, package):
        return package.full_path

    def sort_by_package_type_key(self, package):
        return package.get_package_type_display()

    def sort_by_status_key(self, package):
        return package.get_status_display()

    def sort_by_fixity_date_key(self, package):
        # avoid comparing datetimes with None
        return package.latest_fixity_check_datetime or timezone.now()

    def sort_by_fixity_status_key(self, package):
        return package.latest_fixity_check_result


class FixityLogDataTable(PackageDataTable):

    model = FixityLog

    ORDER_BY_MAPPING = {
        0: "datetime_reported",
        1: "error_details",
    }

    def __init__(self, query_dict):
        search_filter = Q()
        package_uuid = query_dict.get("package-uuid")
        if package_uuid:
            search_filter = Q(package=package_uuid)
        self.total_records = self.model.objects.filter(search_filter).count()
        self.params = self.parse_datatable_parameters(query_dict)
        self.echo = self.params["echo"]
        if self.params["search"]:
            search = self.params["search"]
            search_filter &= Q(error_details__icontains=search)
        queryset = self.model.objects.filter(search_filter).distinct()
        self.total_display_records = queryset.count()
        self.records = self.get_records(queryset)
