---
name: listing-video
description: Make a property tour video from a listing's photos and its listing sheet PDF. Delivers four cuts: branded and unbranded, each in 16:9 and 9:16. Pop style (map or city footage, depth motion, kinetic type, a contact placard). Brand, colours, fonts and music come from a brand file under brands/. Use when the user says "listing video", "property video", "tour video", "video for this listing", or hands over a listing sheet PDF plus a folder of listing photos. NOT faceless-video (narrated explainer), NOT surf-reel or archive-reel.
---

# Listing video

Sibling of `faceless-video`, `surf-reel` and `archive-reel`, same folder, same jobs folder.
Run commands from the Video Studio folder with `python3 scripts/lv.py ...` (on Windows, type
`python` instead of `python3`). Brand file: `brands/<name>.json`. The example brand is
`brands/examplerealty.json`: copy it and edit it for your own brokerage.

## Inputs

- **Listing sheet PDF:** the listing's full sheet from your MLS or brokerage (facts and description).
  The script reads address, price, beds, baths, square footage, the description and any price change.
- **Photo folder:** high-resolution photos, processed and colour-corrected if you can. Name files
  with the room, such as `03 kitchen IMG_1234.jpg` (a room code 0 to 8, then the room word):
  0 exterior, 1 living, 2 dining, 3 kitchen, 4 hallway, 5 stairs, 6 bedroom, 7 bathroom, 8 other.
  Plain room words in the name also work.
- **Optional:** the listing URL (goes in `post.md` only) and a city or topic word for the job folder.

Nothing else is needed. The music and layout come from the brand file.

## Tone rules

- Music only, no narration. No shake, flash, or caption slams. Calm, not hype.
- Use the brand's colours only.
- Room labels are plain ("Kitchen", "Primary Suite"). Callouts come from the listing description,
  38 characters at most, with no hype words ("stunning", "dream home").
- Follow your MLS and local rules for listing media. The unbranded cuts carry no contact info.
- No em dashes in post text.

## Workflow

1. **Make the job.**
   ```bash
   python3 scripts/lv.py make --photos "<photo folder>" --mls "<listing sheet>.pdf" --url "<listing url>" --word <city> --brand examplerealty
   ```
   It prints the facts and any `CONFIRM:` lines. Fix a value by editing `listing.json` (`sqft`,
   `address`, `kicker` such as "Just Listed").
2. **Pick the photos.** Read the numbered contact sheets `work/inventory_N.jpg`, then write `picks.json`:
   - `landscape`: about 24 to 26 photos. The first is the opening: the best front exterior in daylight.
     Then a couple more exteriors, the interior in walking order, patios next to the room they belong to,
     garage and laundry late, a wide exterior to close.
   - `portrait`: about 12, the strongest rooms. Favour wide rooms, they pan best.
   - Each entry is a file name, or `{"photo", "label", "callout", "focus", "move", "beats", "transition"}`.
     The first photo of each room gets its label automatically. `"label": ""` hides it. `focus`
     (0 to 1) moves the crop. `beats` holds one shot longer.
   - Skip near-duplicates, dark or tilted frames, bins, utility meters and anything blocking the house.
   - Set `"music"` to one of the beds in the brand file, and `"style": "pop"` plus `"city"` for pop style.
3. **Sheets.** `python3 scripts/lv.py sheet --job <job> [--music <bed>]` writes
   `work/contact_sheet.jpg` (16:9) and `work/contact_sheet_9x16.jpg`, plus the unbranded end cards in
   `work/preview/`. Look at both yourself first: text is legible, labels sit on the right rooms, and
   nothing important sits in the shaded band of the portrait layout. Then show the user both sheets,
   the durations, the music and the CONFIRM items.
4. **Changes.** `python3 scripts/lv.py swap --job <job> --cut landscape --index 5 --photo "<file>"`,
   or edit `picks.json` and run `sheet` again. Every change needs a fresh sheet shown to the user.
5. **Approval gate.** Rendering refuses until the job is approved. After the user says go:
   `python3 scripts/lv.py approve --job <job>`. Never approve on the user's behalf. A change to the
   picture after approval needs a fresh sheet and a new approval.
6. **Render.** `python3 scripts/lv.py finish --job <job>` (about 7 minutes for all four). It writes
   `out/final_16x9.mp4` and `out/final_9x16.mp4` (branded), `out/mls_16x9.mp4` and `out/mls_9x16.mp4`
   (unbranded), and `out/post.md`, then uploads them to your CDN under `listings/<job>/`.
   - `--no-upload` keeps everything local.
   - `--only portrait` redoes one aspect. `--variants mls` redoes one set.
   - `--no-preview` is only for the user's explicit waiver of the approval gate.
7. **Check and deliver.** Run `ffprobe` on the four files and pull a few frames. Send the user the
   files or links. `python3 scripts/lv.py links --job <job>` rewrites `post.md` and re-uploads it
   after a change.
8. **Thumbnail (optional, branded 16:9 only).** Add a `thumbnail.json` to the job folder with `bg`
   (the best exterior photo) and `lines` (2 to 4 words, the city or price on line 1). Run
   `python3 scripts/yt_thumb.py --job <job>` and read `out/thumb_variants/phone_sizes.jpg`. Never put
   contact details on the unbranded cut or its art.

## Pop style

- Map: coast-to-pin shot with distance tags. Then a city montage (your own clips, labelled with
  distances), the hero exterior with a depth move, the typed address and a count-up price, then the
  tour with depth moves and hard cuts on the beat, and the closing card.
- Tour picks can set `beats` (2 for quick detail shots, blank for automatic timing), `transition: "whip"`
  at floor changes, `move` (`dolly`, `orbit_r`, `orbit_l`, `rise`; portrait `pan_r`, `pan_l`) and `focus`.
- Depth uses a small MiDaS model at `assets/models/midas-v21-small.onnx`. If it is missing, the script
  prints the download command. Depth only moves the camera; it never invents pixels. Never run AI
  image-to-video on listing photos, because it can alter rooms.
- Map data: each city needs cached OpenStreetMap data at `assets/cities/<slug>/cache/osm.json`, fetched
  with an Overpass query. The script says so if it is missing. Distances are straight-line and rounded
  up. Keep the OpenStreetMap attribution the map prints.
- City library: `assets/cities/<slug>/city.json` lists points of interest, distance tags, clips with
  in and out points, and the montage order. `media/` holds your own footage. With no footage, leave the
  montage empty and list `map_tour` stops per aspect: the map glides to each stop and types its name
  and distance.
- Price reductions: when the listing sheet shows a price change, the kicker reads NEW PRICE and the old
  price shows struck through above the new one.

## Brand file

`brands/<name>.json` holds: colours, font files on your machine, logo and team photo paths, the placard
(headline, contacts with name and title, phone, a license line if your market needs one, website,
office, fine print), music beds (BPM and first-beat offset), the default bed, cut sizes and timings,
the loudness target (LUFS, default -14), and pop timings.

To add a music bed: generate a 95-second instrumental, save it as `assets/music/<name>.mp3`, measure it,
and add the entry to the brand file:
```bash
python3 -c "import sys; sys.path.insert(0,'scripts'); import lv_beats; print(lv_beats.analyze(__import__('pathlib').Path('assets/music/<name>.mp3'), <bpm hint>))"
```

## Troubleshooting

- `make` says the photo folder has fewer than six photos: point `--photos` at the full-resolution folder.
- A label covers a feature: set `"label": ""` on that pick, or move the crop with `focus`.
- A room label is wrong: rename the file with the room code, or set `label` on the pick.
- Fonts fall back to a default: point the brand's font paths at installed files.
- A cut runs long or short: change `beats` on a few picks, or adjust the timings in the brand file.
