$(document).ready(function() {
  var uri = $("#user-data-packages").data("uri") || "/";
  var dataTableOptions = {
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
  };
  // separate options for packages table
  var packagesDataTableOptions = {};
  for (var k in dataTableOptions) {
    packagesDataTableOptions[k] = dataTableOptions[k];
  }
  // enable server-side processing
  packagesDataTableOptions["bServerSide"] = true;
  packagesDataTableOptions["bProcessing"] = true;
  packagesDataTableOptions["sAjaxSource"] = uri + "packages_ajax";
  var columns = [];
  // for each column create a function that replaces the
  // table cell content with the HTML returned by the server
  $('.packages-datatable thead th').each(function(i, header) {
    columns.push({
      "mData": function(source, type, val) {
        var $tr = $(Object.values(source).join(""));
        return $tr.find('td').eq(i).html();
      },
      "bSortable": $(header).hasClass("sortable")
    });
  });
  packagesDataTableOptions["aoColumns"] = columns;

  $('.datatable').dataTable(dataTableOptions);
  $('.packages-datatable').dataTable(packagesDataTableOptions);

  $("body").on("click", "a.request-delete", function(event) {
    var self = $(event.target);
    var uuid = self.data('package-uuid');
    var pipeline = self.data('package-pipeline');
    var packageType = self.data('package-type');
    var $userDataEl = $("#user-data-packages");
    var userId = $userDataEl.data('user-id');
    var userEmail = $userDataEl.data('user-email');
    var userUsername = $userDataEl.data('user-username');
    var userAPIKey = $userDataEl.data('user-api-key');
    var uri = $userDataEl.data('uri');
    var formData = {
      "event_reason": "Storage Service user wants to delete " + packageType + " " + uuid + ".",
      "pipeline": pipeline,
      "user_id": userId,
      "user_email": userEmail
    };
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
          data.message + "</div>"
        );
      }
    });
    return false;
  });

  // Enable confirmation modal in certain forms. The submit button is
  // overriden so it opens the modal. The submit button inside the modal is
  // allowed to submit the form instead.
  // Used in `packages_table.html` (delete DIP functionality).
  // Currently limited to one form per page, see jQuery.each for more.
  $("body").on("click", "form.submit-confirm button[type=submit]", function(event) {
    var $button = $(event.target);
    var $form = $button.closest('form');
    var $modal = $form.find(".confirm-modal");
    if ($button.parents(".confirm-modal").length) {
      return true;
    }
    event.preventDefault();
    $modal.modal("show");
  });

  /***************
  CALLBACK HEADERS
  ***************/

  // Add delete link besides each callback header
  $(".callback > form input[name^=header_] + input[name^=header_]").each(function() {
    $(this).after($('<a href="#" class="delete_header">' + gettext("Delete") + '</a>'));
  });

  // Append add header link after the existing headers
  $(".callback > form p:has(input[name^=header_] + input[name^=header_])").last().after(
    $('<p><a href="#" class="add_header">' + gettext("Add header") + '</a></p>')
  );

  // Manage inputs from a set of headers
  function updateHeaderInputs(headers, increment=0, clean=true) {
    // Do nothing if no need to increment properties or clean values
    if (increment === 0 && !clean) {
      return;
    }
    headers.find("input[name^=header_]").each(function() {
      var $input = $(this);
      // Update first digits of input id and name properties
      if (increment !== 0) {
        $.each(["id", "name"], function(index, value) {
          $input.prop(value, $input.prop(value).replace(/\d+/, function(key) {
            return parseInt(key) + increment;
          }));
        });
      }
      // Remove current value
      if (clean) {
        $input.val("");
      }
    });
  }

  // Delete header link click listener
  $("body").on("click", ".callback > form a.delete_header", function(event) {
    event.preventDefault();
    var $this_header = $(this).parent();
    var $headers_count = $this_header.parent().find(":has(input[name^=header_])").length;
    // If there is more than one header, update the ones after this to
    // decrease the id and name counter (keeping the values) and remove it.
    if ($headers_count > 1) {
      var $following_headers = $this_header.nextAll(":has(input[name^=header_])");
      updateHeaderInputs($following_headers, -1, false)
      // If we're deleting the first header, move the label to the next one
      var $label = $this_header.find("label").first();
      if ($label) {
        $following_headers.first().prepend($label);
      }
      $this_header.remove();
    } else {
      // Otherwise, just remove this header inputs values
      updateHeaderInputs($this_header)
    }
  });

  // Add header link click listener
  $("body").on("click", ".callback > form a.add_header", function(event) {
    event.preventDefault();
    // Clone last header
    var $last_header = $(this).parent().prev();
    var $clone = $last_header.clone();
    // Remove label if cloning the first header
    $clone.find("label").remove();
    // Increase the inputs id and name properties and remove the values
    updateHeaderInputs($clone, 1)
    // Append modified clone after last header
    $last_header.after($clone);
  });
});
