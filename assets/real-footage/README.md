# Real footage library

Prompt library for the `real-footage` skill. The craft guide that explains how to use it is
`docs/real-footage.md`. All wording here is original; the method's source is linked there.

```
templates/   ctlt-still, llm-helper, single-take-clip, montage, rephotograph, style-extraction,
             person-swap, talk-to-lens-clip
behaviors/   one file per camera behavior; the file name is a clip's "technique"
styles/      one file per camera style; the file name is a shot's "style"
lint.json    word lists and thresholds for fv.py rf lint; tune them here
```

## File format

Every file follows the same rules so scripts can read it without a YAML library:

- Front matter sits between two `---` lines at the top, one `key: value` per line.
- A list is written `[a, b, c]`, and no list item contains a comma or a square bracket.
- A text value that contains square brackets or a colon is wrapped in double quotes and
  contains no double quotes of its own.
- The file name without `.md` equals the `name` key.
- The usable text (the template, the camera paragraph, the example prompt) is the first
  fenced `text` block in the body.
- Anything in square brackets is a fill-in. A finished prompt has no square brackets left.
  In a style's `camera_sentence` and `details_sentence`, the lowercase bracket words name
  that style's own fields (`[framing flaw]` means one item from `framing_flaws`), except
  `[textures]`, which the scene supplies.
- `@[IMG1]`, `@[IMG2]`, `@[VID1]`, `@[AUD1]` stand in for reference tags. In a finished prompt write
  them as `@IMG1`, without brackets; the engine swaps in the model's real syntax (guide
  section 13).

Front matter keys:

| Folder | Keys |
|---|---|
| `templates/` | `name`, `use` |
| `behaviors/` | `name`, `proves`, `needs`, `not_this`, `failure_modes` |
| `styles/` | `name`, `device`, `lens`, `viewpoint`, `framing_flaws`, `light`, `artifacts`, `resolution_note`, `avoid`, `camera_sentence`, `details_sentence` |

None of the behaviors or styles has been run against a live generator yet. Tony edits and
approves styles; update a behavior's `failure_modes` from what the first runs show.
