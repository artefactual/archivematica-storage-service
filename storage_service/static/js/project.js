
$(document).ready(function() {
    $('.datatable').dataTable({
      // List of language strings from https://datatables.net/reference/option/language
      oLanguage: {
          sDecimal:        "",
          sEmptyTable:     gettext("No data available in table"),
          sInfo:           gettext("Showing _START_ to _END_ of _TOTAL_ entries"),
          sInfoEmpty:      gettext("Showing 0 to 0 of 0 entries"),
          sInfoFiltered:   gettext("(filtered from _MAX_ total entries)"),
          sInfoPostFix:    "",
          sThousands:      ",",
          sLengthMenu:     gettext("Show _MENU_ entries"),
          sLoadingRecords: gettext("Loading..."),
          sProcessing:     gettext("Processing..."),
          sSearch:         gettext("Search:"),
          sZeroRecords:    gettext("No matching records found"),
          oPaginate: {
              sFirst:      gettext("First"),
              sLast:       gettext("Last"),
              sNext:       gettext("Next"),
              sPrevious:   gettext("Previous")
          },
          oAria: {
              sSortAscending:  gettext(": activate to sort column ascending"),
              sSortDescending: gettext(": activate to sort column descending"),
          },
      }
    });
} );
