---
name: archive-reel
description: Make a 9:16 product ad that looks like 1920s silent-film found footage. Public-domain film is cut to war drums, your brand logo is printed into the film, a small distant figure can appear, and the product is revealed at the end. Use when the user says "archive reel", "silent film ad", "old movie ad", "found footage ad", or gives a product page and wants a short-form ad WITHOUT their own footage. NOT surf-reel (the user's own footage), NOT talking-head (the user on camera), NOT real-footage (photoreal AI clips), NOT faceless-video (narrated explainer).
---

# Archive reel

Sibling of `faceless-video` and `talking-head`, same folder, same jobs folder. Run commands from the
Video Studio folder with `python3 scripts/ar.py ...` (on Windows, type `python` instead of `python3`).
Film library: `archive/` (films, scans, clips, music and the job template). Needs `ffmpeg` and `ffprobe`.

## The format

About 15 seconds, roughly 11 shots, every cut on one beat grid (the default beat is 0.604 s, about 99 BPM).
- Real archive film sets the world and tells a tiny story in three or four shots.
- The brand logo is printed INTO the opening shots before the grade, like a title on the original reel.
  No slogan text over the hook.
- An optional hero figure appears two or three times, small and far away inside the real footage, never clear.
- The last walk-away dissolves into the back print, then the front, then the URL.
- Soundtrack: built war drums with projector clatter, crackle, crowd and fire. Product reveals are silent
  by default. A product shot can opt into a whoosh with `"whoosh": true`. Hold each product shot about 2.4 s.

## Rules that make it work

- Real archive film for the world. Generated figures only when small and distant. A full-frame generated
  shot reads fake, even after tone matching.
- Use the same prop in every shot so the story reads (`prop`).
- Censor profanity in on-screen text.
- Composite plates must be empty, locked-off shots. A plate with people walking through it will not work.
- Preview before render. Paid image or video generation needs the user's go and a quote first.

## Inputs

- **Product page URL.** A Shopify-style product page supplies the shop images, title, price and blurb.
- **Clean product shots on white:** front and back, saved as `product/front.jpg` and `product/back.jpg`.
  Store mockups have busy backgrounds, so use clean shots.
- **The logo on white** as a file in `product/` (for example `product/logo.webp`). The shot's `logo.src` names it.
- **The story in one line:** who the hero is and what he or she does, if there is a hero.

## Films

Use public-domain films only: published 1930 or earlier, silent copies. Avoid commercial restorations
with new scores, and never keep the source audio. Before choosing shots, scene-detect and contact-sheet
any new film:
```bash
ffmpeg -i film.mp4 -vf "scale=160:-2,select='gt(scene,0.3)',metadata=print:file=scenes.txt" -an -f null -
```
Pull a clip from a film into the library:
```bash
ffmpeg -ss <seconds> -i film.mp4 -t 3 -an -c:v libx264 -crf 14 archive/clips/<name>.mp4
```
Reuse clips already in `archive/clips/`.

## Workflow

1. **New job.**
   ```bash
   python3 scripts/ar.py new https://your-store.example/products/<handle> [--title "..."] [--word <word>]
   ```
   It creates the job folder with the shop images and blurb in `product/`, and a `job.json` from
   `archive/templates/job_template.json`. The `new` command reads a Shopify product feed. For another
   store, make the folders and `job.json` by hand from the template.
   The template includes a placeholder hero figure: replace or remove those shots and comps.
2. **Pick the world.** Choose clips from `archive/clips/`, or cut new ones from `archive/films/`.
3. **Hero figure (optional).** Make a small figure on a still in a 1920s silent-film look, using a free
   local image model or an image service. Animate it only with the user's approval and a quote. Describe
   it in `comps` (clip, plate, feet, height, haze, and a prop if any), then run
   `python3 scripts/ar.py comp <job>`. It mattes the figure with rembg, stamps the prop, matches tones,
   and writes `public/comp_<name>.mp4`. If rembg is missing, the script prints the install command.
4. **Author `job.json`.** Keys: `title`, `product`, `music` (beat), `end` (seconds and lines), `comps`,
   `shots` and `audio`. Each shot has an `id`, a `kind` (`footage`, `card`, `clip` or `still`), a `dur`,
   and optionally `src`, `in`, `focus`, `logo`, `tee`, `text`, `accent`, `hits`. `audio` is
   `{"mode": "drums"}` by default, or `{"mode": "record", "file", "start", "speed", "booms"}`.
   Every `dur` must be a multiple of the beat. `accent: "big"` goes on the hook, the card and the hero's
   entrance. Run `python3 scripts/ar.py check <job>` to catch cuts off the grid.
5. **Sheet.** `python3 scripts/ar.py sheet <job>` renders every shot (about a minute) and writes
   `work/contact_sheet.jpg`, one frame per shot, with the platform UI zones outlined. Check that the logo
   sits inside the frame, the figure is findable but not obvious, and the product is clear of the UI.
   Send the sheet to the user, then END YOUR TURN.
6. **Approval gate.** Only after the user says go: `python3 scripts/ar.py approve <job>`. Rendering is
   blocked until then. Any change to the picture (shots, comps, `end`, or anything in `public/` or
   `product/`) voids the approval. Changing `audio` or `post` does not. `--no-preview` is only for the
   user's explicit waiver of the preview for that job.
7. **Render.** `python3 scripts/ar.py render <job>` writes `out/master_silent.mp4`, `out/final.mp4` (the
   chosen soundtrack), any variant files, and `out/post.txt`. Check with `ffprobe`: 1080x1920, about 15 s,
   with audio. Pull frames around the hero shots and the end card.
8. **Soundtrack only.** `python3 scripts/ar.py score <job>` redoes the audio on the approved picture, with
   no new approval needed.
9. **Post kit.** `out/post.txt` holds the caption, link and hashtags. `python3 scripts/ar.py kit <job>`
   rewrites it. Also write `out/posts.md` with a section per platform (Instagram Reels, TikTok, YouTube
   Shorts, Facebook Reels). Each caption ends with your own sign-off or brand block, if you use one.
   Always credit the film, for example "Footage: <title> (<year>), public domain."

## Posting notes

- Paid boosts can be rejected for nudity in a back print. Organic posts are usually fine.
- Business accounts can add only commercial music in-app. The baked-in drums are always safe.
- Check the product's price, name and link against the live product page before posting.

## Troubleshooting

- **`comp` produced a plate with 0 frames.** A download dropped. It retries three times. Run it again.
- **A shot is off the beat grid.** `ar.py check` prints the cut. Change its `dur` to a whole number of beats.
- **The figure is too visible.** Reduce its `height` in the comp, and keep `feet` in the middle of the plate
  so the figure stays small and distant.
- **Logo is missing.** Check that the file named in `logo.src` sits in `product/`.
- **Text is missing.** All text is drawn as PNG overlays, so ffmpeg builds without drawtext are fine.
