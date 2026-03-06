var textOrEmpty = function (value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
};

var escapeHtml = function (value) {
  return $("<div>").text(textOrEmpty(value)).html();
};

var linkHtml = function (href, text) {
  var $link = $("<a>").attr("href", href).text(textOrEmpty(text));
  return $link.prop("outerHTML");
};

var elementToHtml = function ($element) {
  return $("<div>").append($element).html();
};

var buildColumns = function (headers, renderers) {
  var columns = [];
  headers.each(function (i, header) {
    columns.push({
      mData: function (source) {
        return renderers[i](source);
      },
      bSortable: $(header).hasClass("sortable"),
    });
  });
  return columns;
};

var buildRequestDeleteLink = function (requestDeleteAction) {
  var $requestDeleteLink = $("<a>")
    .attr("href", "#")
    .addClass("request-delete")
    .attr("data-package-type", textOrEmpty(requestDeleteAction.package_type))
    .attr("data-package-uuid", textOrEmpty(requestDeleteAction.package_uuid))
    .attr(
      "data-package-pipeline",
      textOrEmpty(requestDeleteAction.pipeline_uuid),
    )
    .text(gettext("Request Deletion"));
  return $requestDeleteLink.prop("outerHTML");
};

var buildDirectDeleteForm = function (directDeleteAction) {
  var deleteLabel = textOrEmpty(directDeleteAction.confirm_label);
  var $form = $("<form>")
    .attr("method", "POST")
    .attr("action", directDeleteAction.action_url);
  $form.append(
    $("<input>")
      .attr("type", "hidden")
      .attr("name", "csrfmiddlewaretoken")
      .val(textOrEmpty(directDeleteAction.csrf_token)),
  );
  $form.append(
    $("<button>")
      .addClass("link")
      .attr("type", "button")
      .attr(
        "data-am-modal-target",
        "#" + textOrEmpty(directDeleteAction.modal_id),
      )
      .text(deleteLabel),
  );

  var $modal = $("<div>")
    .attr("id", textOrEmpty(directDeleteAction.modal_id))
    .addClass("confirm-modal modal hide fade")
    .attr("tabindex", "-1")
    .attr("role", "dialog")
    .attr("aria-labelledby", textOrEmpty(directDeleteAction.modal_label_id))
    .attr("aria-hidden", "true");
  var $modalHeader = $("<div>").addClass("modal-header");
  $modalHeader.append(
    $("<button>")
      .attr("type", "button")
      .addClass("close")
      .attr("data-dismiss", "modal")
      .attr("aria-hidden", "true")
      .html("&times;"),
  );
  $modalHeader.append(
    $("<h3>")
      .attr("id", textOrEmpty(directDeleteAction.modal_label_id))
      .text(textOrEmpty(directDeleteAction.modal_title)),
  );
  $modal.append($modalHeader);

  var $modalBody = $("<div>").addClass("modal-body");
  $modalBody.append($("<p>").text(textOrEmpty(directDeleteAction.prompt_text)));
  $modal.append($modalBody);

  var $modalFooter = $("<div>").addClass("modal-footer");
  $modalFooter.append(
    $("<button>")
      .addClass("btn")
      .attr("type", "button")
      .attr("data-dismiss", "modal")
      .attr("aria-hidden", "true")
      .text(textOrEmpty(directDeleteAction.close_label)),
  );
  $modalFooter.append(
    $("<button>")
      .addClass("btn btn-danger")
      .attr("type", "submit")
      .text(deleteLabel),
  );
  $modal.append($modalFooter);

  $form.append($modal);
  return elementToHtml($form);
};

var renderPackageActions = function (actions) {
  if (actions === null || actions === undefined) {
    return "";
  }

  var links = [];
  if (actions.pointer_file_href) {
    links.push(linkHtml(actions.pointer_file_href, gettext("Pointer File")));
  }
  if (actions.download_href) {
    links.push(linkHtml(actions.download_href, gettext("Download")));
  }
  if (actions.reingest_href) {
    links.push(linkHtml(actions.reingest_href, gettext("Re-ingest")));
  }
  if (actions.request_delete) {
    links.push(buildRequestDeleteLink(actions.request_delete));
  }

  var linksHtml = links.join(" | ");
  if (actions.direct_delete) {
    return linksHtml + buildDirectDeleteForm(actions.direct_delete);
  }
  return linksHtml;
};

var packageColumnRenderers = [
  function (source) {
    return escapeHtml(source.uuid);
  },
  function (source) {
    var cell = source.origin_pipeline || {};
    if (cell.href) {
      return linkHtml(cell.href, cell.text);
    }
    return escapeHtml(cell.text);
  },
  function (source) {
    var cell = source.current_location || {};
    if (cell.href) {
      return linkHtml(cell.href, cell.text);
    }
    return escapeHtml(cell.text);
  },
  function (source) {
    return escapeHtml(source.size);
  },
  function (source) {
    return escapeHtml(source.package_type);
  },
  function (source) {
    return escapeHtml(source.replica_of);
  },
  function (source) {
    var cell = source.status || {};
    var statusText = escapeHtml(cell.text);
    if (cell.update_href) {
      return (
        statusText +
        " (" +
        linkHtml(cell.update_href, gettext("Update Status")) +
        ")"
      );
    }
    return statusText;
  },
  function (source) {
    return escapeHtml(source.stored);
  },
  function (source) {
    return escapeHtml(source.fixity_date);
  },
  function (source) {
    var cell = source.fixity_status || {};
    if (cell.href) {
      return linkHtml(cell.href, cell.text);
    }
    return escapeHtml(cell.text);
  },
  function (source) {
    return renderPackageActions(source.actions);
  },
];

var fixityLogColumnRenderers = [
  function (source) {
    return escapeHtml(source.date);
  },
  function (source) {
    return escapeHtml(source.error);
  },
];

var getAjaxDataTableOptions = function (
  options,
  ajaxSource,
  headers,
  renderers,
  filter,
) {
  var result = {};
  for (var key in options) {
    result[key] = options[key];
  }
  // enable server-side processing
  result["bServerSide"] = true;
  result["bProcessing"] = true;
  result["sAjaxSource"] = ajaxSource;
  if (undefined !== filter) {
    result["fnServerParams"] = function (data) {
      data.push(filter);
    };
  }
  result["aoColumns"] = buildColumns(headers, renderers);
  return result;
};

var setPackagesDataTable = function (options) {
  var $userDataEl = $("#user-data-packages");
  var uri = $userDataEl.data("uri") || "/";
  var location = $userDataEl.data("location-uuid");
  var filter;
  if (typeof location === "string" && location.length) {
    // this will get to the request.GET query dict
    // as location-uuid=<location>
    filter = { name: "location-uuid", value: location };
  }
  $(".packages-datatable").dataTable(
    getAjaxDataTableOptions(
      options,
      uri + "packages_ajax",
      $(".packages-datatable thead th"),
      packageColumnRenderers,
      filter,
    ),
  );
};

var setFixityLogsDataTable = function (options) {
  var $userDataEl = $("#user-data-packages");
  var uri = $userDataEl.data("uri") || "/";
  var package_uuid = $userDataEl.data("package-uuid");
  var filter;
  if (typeof package_uuid === "string" && package_uuid.length) {
    // this will get to the request.GET query dict
    // as package-uuid=<location>
    filter = { name: "package-uuid", value: package_uuid };
  }
  // initially sort the table by date column, newest first
  var customOptions = {
    aaSorting: [[0, "desc"]],
  };
  for (var key in options) {
    customOptions[key] = options[key];
  }
  $(".fixity-logs-datatable").dataTable(
    getAjaxDataTableOptions(
      customOptions,
      uri + "fixity_ajax",
      $(".fixity-logs-datatable thead th"),
      fixityLogColumnRenderers,
      filter,
    ),
  );
};

var setDataTables = function () {
  var dataTableOptions = {
    // List of language strings from https://datatables.net/reference/option/language
    oLanguage: {
      sDecimal: "",
      sEmptyTable: gettext("No data available in table"),
      sInfo: gettext("Showing _START_ to _END_ of _TOTAL_ entries"),
      sInfoEmpty: gettext("Showing 0 to 0 of 0 entries"),
      sInfoFiltered: gettext("(filtered from _MAX_ total entries)"),
      sInfoPostFix: "",
      sThousands: ",",
      sLengthMenu: gettext("Show _MENU_ entries"),
      sLoadingRecords: gettext("Loading..."),
      sProcessing: gettext("Processing..."),
      sSearch: gettext("Search:"),
      sZeroRecords: gettext("No matching records found"),
      oPaginate: {
        sFirst: gettext("First"),
        sLast: gettext("Last"),
        sNext: gettext("Next"),
        sPrevious: gettext("Previous"),
      },
      oAria: {
        sSortAscending: gettext(": activate to sort column ascending"),
        sSortDescending: gettext(": activate to sort column descending"),
      },
    },
  };
  setPackagesDataTable(dataTableOptions);
  setFixityLogsDataTable(dataTableOptions);
};

$(document).ready(function () {
  setDataTables();
  $("body").on("click", "a.request-delete", function (event) {
    var self = $(event.target);
    var uuid = self.data("package-uuid");
    var pipeline = self.data("package-pipeline");
    var packageType = self.data("package-type");
    var $userDataEl = $("#user-data-packages");
    var userId = $userDataEl.data("user-id");
    var userEmail = $userDataEl.data("user-email");
    var userUsername = $userDataEl.data("user-username");
    var userAPIKey = $userDataEl.data("user-api-key");
    var uri = $userDataEl.data("uri");
    var formData = {
      event_reason:
        "Storage Service user wants to delete " +
        packageType +
        " " +
        uuid +
        ".",
      pipeline: pipeline,
      user_id: userId,
      user_email: userEmail,
    };
    $.ajax({
      type: "POST",
      url: uri + "api/v2/file/" + uuid + "/delete_aip/",
      data: JSON.stringify(formData),
      dataType: "json",
      contentType: "application/json; charset=utf-8",
      headers: { Authorization: "ApiKey " + userUsername + ":" + userAPIKey },
      success: function (data) {
        $("div#package-delete-alert").remove();
        $("h1")
          .first()
          .after(
            "<div id='package-delete-alert' class='alert alert-success'>" +
              data.message +
              "</div>",
          );
      },
      failure: function (data) {
        $("div#package-delete-alert").remove();
        $("h1")
          .first()
          .after(
            "<div id='package-delete-alert' class='alert alert-warning'>" +
              data.message +
              "</div>",
          );
      },
    });
    return false;
  });

  /***************
  CALLBACK HEADERS
  ***************/

  // Add delete link besides each callback header
  $(".callback > form input[name^=header_] + input[name^=header_]").each(
    function () {
      $(this).after(
        $('<a href="#" class="delete_header">' + gettext("Delete") + "</a>"),
      );
    },
  );

  // Append add header link after the existing headers
  $(".callback > form p:has(input[name^=header_] + input[name^=header_])")
    .last()
    .after(
      $(
        '<p><a href="#" class="add_header">' +
          gettext("Add header") +
          "</a></p>",
      ),
    );

  // Manage inputs from a set of headers
  function updateHeaderInputs(headers, increment = 0, clean = true) {
    // Do nothing if no need to increment properties or clean values
    if (increment === 0 && !clean) {
      return;
    }
    headers.find("input[name^=header_]").each(function () {
      var $input = $(this);
      // Update first digits of input id and name properties
      if (increment !== 0) {
        $.each(["id", "name"], function (index, value) {
          $input.prop(
            value,
            $input.prop(value).replace(/\d+/, function (key) {
              return parseInt(key) + increment;
            }),
          );
        });
      }
      // Remove current value
      if (clean) {
        $input.val("");
      }
    });
  }

  // Delete header link click listener
  $("body").on("click", ".callback > form a.delete_header", function (event) {
    event.preventDefault();
    var $this_header = $(this).parent();
    var $headers_count = $this_header
      .parent()
      .find(":has(input[name^=header_])").length;
    // If there is more than one header, update the ones after this to
    // decrease the id and name counter (keeping the values) and remove it.
    if ($headers_count > 1) {
      var $following_headers = $this_header.nextAll(
        ":has(input[name^=header_])",
      );
      updateHeaderInputs($following_headers, -1, false);
      // If we're deleting the first header, move the label to the next one
      var $label = $this_header.find("label").first();
      if ($label) {
        $following_headers.first().prepend($label);
      }
      $this_header.remove();
    } else {
      // Otherwise, just remove this header inputs values
      updateHeaderInputs($this_header);
    }
  });

  // Add header link click listener
  $("body").on("click", ".callback > form a.add_header", function (event) {
    event.preventDefault();
    // Clone last header
    var $last_header = $(this).parent().prev();
    var $clone = $last_header.clone();
    // Remove label if cloning the first header
    $clone.find("label").remove();
    // Increase the inputs id and name properties and remove the values
    updateHeaderInputs($clone, 1);
    // Append modified clone after last header
    $last_header.after($clone);
  });
});
