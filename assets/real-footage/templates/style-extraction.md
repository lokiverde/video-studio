---
name: style-extraction
use: "Turns a still that worked, plus its prompt, into a reusable camera style file for styles/."
---

# Style extraction

Hand this to any LLM with the image and the prompt that produced it. Save the answer as
`assets/real-footage/styles/<name>.md` and show it to Tony before using it on a job.

```text
Here is an image and the prompt that produced it. Extract the CAMERA STYLE only: device, lens, viewpoint, framing flaws, light behavior, artifacts and resolution guidance. Remove every subject detail.

Return a reusable style file in this exact shape:
- Front matter between two lines of three hyphens, one key per line, in this order: name, device, lens, viewpoint, framing_flaws, light, artifacts, resolution_note, avoid, camera_sentence, details_sentence.
- name is short, lowercase, words joined by hyphens.
- framing_flaws, artifacts and avoid are lists written [a, b, c], and no item contains a comma.
- camera_sentence and details_sentence are patterns in double quotes, using square-bracket slots that name the other fields, such as [device], [lens], [viewpoint], [framing flaw], [light], [artifacts], plus [textures] for the subject's own surfaces.
- After the front matter, one example prompt in a fenced text block that applies the style to a new, unrelated subject. Camera sentence first. No real people, brands, logos, readable text, real money, weapons or injuries.
- No em dashes anywhere.
```

Check before saving: the artifacts all belong to one device, `avoid` lists the filler
quality words that would break the look, and the file follows `assets/real-footage/README.md`.
