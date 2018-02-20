
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

    $("a.request-delete").click(function() {
        var self = $(this);
        var uuid = self.data('package-uuid');
        var pipeline = self.data('package-pipeline');
        var $userDataEl = $("#user-data-packages");
        var userId = $userDataEl.data('user-id');
        var userEmail = $userDataEl.data('user-email');
        var userUsername = $userDataEl.data('user-username');
        var userAPIKey = $userDataEl.data('user-api-key');
        var uri = $userDataEl.data('uri');
        var formData = {
            "event_reason": "Storage Service user wants to delete AIP " + uuid + ".",
            "pipeline": pipeline,
            "user_id": userId,
            "user_email": userEmail};
        $.ajax({
            type: "POST",
            url: uri + "api/v2/file/" + uuid + '/delete_aip/',
            data: JSON.stringify(formData),
            dataType: "json",
            contentType: "application/json; charset=utf-8",
            headers: {"Authorization": "ApiKey " + userUsername + ":" + userAPIKey},
            success: function(data) {
                $("div#package-delete-alert").remove();
                $("h1").first().after(
                    "<div id='package-delete-alert' class='alert alert-success'>" +
                    data.message + "</div>");
            },
            failure: function(errMsg) {
                $("div#package-delete-alert").remove();
                $("h1").first().after(
                    "<div id='package-delete-alert' class='alert alert-warning'>" +
                    data.message + "</div>");
            }
        });
        return false;
    });
});
