# Profile assets

Everything visual in the profile README is hosted in this repository, so the page has no
runtime dependency on third-party image servers (only shields.io badges remain external).

| Folder | Contents | How it updates |
|---|---|---|
| `assets/` | Typing banner, wave dividers, hardware stat cards, project figures | `scripts/build_assets.py` (run by hand) |
| `profile/` | GitHub stats, top languages, streak | `.github/workflows/profile-cards.yml` (daily) |

## Rebuilding `assets/`

```bash
pip install fonttools brotli uharfbuzz pillow
npm pack @fontsource/fira-code && tar xzf fontsource-fira-code-*.tgz   # -> package/files/

# clone the project repos next to each other, e.g. into ../repos
python3 scripts/build_assets.py --fonts package/files --figures ../repos
```

To change a number on a hardware card or a line of the typing banner, edit the `DATA`
section at the top of `build_assets.py` and re-run. Keep every number traceable to the
project repository it came from.

Each image has a dark and a light variant and is embedded with `<picture>` +
`prefers-color-scheme`, so both GitHub themes render correctly.
