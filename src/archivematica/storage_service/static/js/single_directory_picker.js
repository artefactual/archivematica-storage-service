function createSingleDirectoryPicker( // eslint-disable-line no-unused-vars
  path,
  textFieldCssId,
  triggerElementCssId,
  destinationCssId,
  ajaxChildDataUrl,
) {
  var SingleDirectoryPickerView = Backbone.View.extend({
    initialize: function (options) {
      this.modal_template = options.modal_template;
    },

    showSelector: function () {
      // display action selector in modal window
      $(this.modal_template).modal({ show: true });

      // make it destroy rather than hide modal
      $("#directory-select-close, #directory-select-cancel").click(function () {
        $("#directory-select-modal").remove();
        $(".modal-backdrop").remove();
      });

      // add directory selector
      var selector = new DirectoryPickerView({
        ajaxChildDataUrl: ajaxChildDataUrl,
        el: $("#explorer"),
        levelTemplate: $("#template-dir-level").html(),
        entryTemplate: $("#template-dir-entry").html(),
        actionHandlers: [
          {
            name: "Select",
            description: "Select directory",
            iconHtml: "Select",
            logic: function (result) {
              // Path with the base path stripped
              var path = result.path.replace(selector.basePath, "");

              // strip leading '/'s
              while (path[0] == "/") {
                path = path.substr(1, path.length - 1);
              }

              $("#" + textFieldCssId).val(path);
              $("#directory-select-modal").remove();
              $(".modal-backdrop").remove();
            },
          },
        ],
      });

      selector.structure = {
        name: path,
        parent: undefined,
        children: [],
      };
      selector.basePath = path;

      selector.render();
    },
  });

  var picker = new SingleDirectoryPickerView({
    el: $("#directory_picker"),
    modal_template: $("#directory-select-modal-layout").html(),
  });

  $("#" + triggerElementCssId).click(function () {
    picker.showSelector();
  });
  picker.render();
}
