# modal

`modal` is a frontend feature that provides Bootstrap 2 style modal behavior in
Storage Service core without depending on Bootstrap's jQuery modal plugin.

It controls show/hide state for `.modal` elements, manages backdrops, handles
`Escape` to close, and supports declarative open/close triggers
(`data-am-modal-target` / `data-am-toggle="modal"` and
`data-dismiss="modal"`).

## Usage

Load the feature in the Django template:

```django
{% block data_features %}modal{% endblock %}
```

Use standard Bootstrap-style modal markup:

```html
<a href="#example-modal" data-am-toggle="modal">Open modal</a>

<div class="modal hide fade" id="example-modal" tabindex="-1" role="dialog" aria-hidden="true">
  <div class="modal-header">
    <button type="button" class="close" data-dismiss="modal" aria-label="Close">×</button>
    <h3>Example modal</h3>
  </div>
  <div class="modal-body">
    <p>Example content.</p>
  </div>
  <div class="modal-footer">
    <button class="btn" data-dismiss="modal">Close</button>
  </div>
</div>
```

For imperative control, use the native API exposed at
`window.StorageServiceModal`:

```js
window.StorageServiceModal?.show(document.getElementById('example-modal'))
window.StorageServiceModal?.hide(document.getElementById('example-modal'))
```

## Accessibility

The feature updates `aria-hidden` when modals open and close, moves focus into
the modal on open, and restores focus to the opener on close.
