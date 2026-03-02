# nav-collapse

`nav-collapse` provides Bootstrap 2 style navbar collapse behavior without
Bootstrap's JavaScript plugin.

## Usage

Load the feature in page-level bootstrap (SS base template loads it globally):

```django
<body data-features="nav-collapse ...">
```

Use declarative triggers and a collapse target:

```html
<button
  type="button"
  data-am-toggle="collapse"
  data-am-target="#main-navigation"
  aria-controls="main-navigation"
  aria-expanded="false"
>
  Menu
</button>

<div id="main-navigation" class="nav-collapse collapse" aria-hidden="true">
  ...
</div>
```

The feature toggles the `in` class and keeps `aria-expanded` /
`aria-hidden` in sync.
