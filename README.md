# Engineering Good Static Site Recreation

Static recreation of the public Engineering Good website with the refreshed brand colors:

- Primary orange: `#FF4F00`
- Navy: `#11122B`
- Light blue: `#9FE7F5`
- Accessible orange: `#BF3700`
- Orange hover: `#8F2900`
- Body text: `#1F1F1F`
- Focus blue: `#005FCC`

The site is dependency-free at runtime and can run from any static web server. It includes:

- Custom recreated homepage
- 26 public WordPress pages
- 11 story/newsletter posts
- Stories and newsletter category archives
- Localized image assets
- `sitemap.xml` and `404.html`

## Local Preview

```sh
python3 -m http.server 5173
```

Then open `http://localhost:5173`.

## Regenerate From Live Site

```sh
python3 scripts/build_static_site.py
```

The generator reads the public Engineering Good WordPress REST API, downloads referenced media into `assets/site/`, rewrites internal links to local static routes, and preserves the custom homepage.

## Notes

This implementation uses Engineering Good public site structure, copy, and imagery/assets with permission from the requester.
