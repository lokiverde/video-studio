---
name: countdown
description: Make a countdown "reasons" video with the creator on camera. The viewer's question is the title, the top five reasons are counted from public threads, a counted comment or two and a real quote sit under each reason, a local expert answers each with a sourced number, and a call to action comes after the fourth reason. Use when the user says "countdown video", "top 5 video", "top list video", "reasons video", or "video with a quiz", or gives a question from comment threads and wants a countdown. NOT a plain talking-head wrap (use talking-head), NOT faceless-video (narrated explainer, no creator on screen), NOT archive-reel or surf-reel.
---

# Countdown video

Sibling of `talking-head`: same pipeline, same gates. Read `skills/talking-head/SKILL.md` for the block
names, the preview gate and the render rules. Run commands from the Video Studio folder. This skill
adds the research, tally, script and call-to-action steps. `python3 scripts/countdown.py` covers those;
`python3 scripts/th.py` runs the video itself.

## What it makes

A 16:9 video, and a 9:16 cut from the same job. The title is the viewer's question. The countdown runs
from #5 up to #1 (least common reason to most common). Each reason gets a counted comment or two, real
quotes with their community name, and a rebuttal from a named source with its link. After #4 the
video shows a call to action with the link on screen. The hook states real counts, such as "I read 412
comments across 9 threads", built from the threads the creator actually read.

## Setup (once)

- **Booking link:** set `COUNTDOWN_CALL_URL` in `config.env` to your own booking page. The script ships
  with a default link that is not yours. Replace it.
- **Quiz or landing page:** `research.json` must name a quiz from the `QUIZZES` dictionary in
  `scripts/countdown.py`. Add your own entry: a slug, the host it lives on, and a title. The tally refuses
  any slug it does not know. The quiz link is built as `https://<host>/<slug>`.

## Workflow

Make a pre-production folder: `jobs/countdown-<YYYYMMDD>-<word>/`. It exists before filming, and
`th.py new` creates the video job later.

1. **Pick the question.** Choose a question people argue about in public threads. Check the topic has
   enough material: a topic with under about 150 relevant comments is too thin. Pick another question.
2. **Research.** Read public threads on the question (forums, community boards, review sites, comment
   sections). Count the comments you actually read. Code each comment once, under its main reason, and
   skip off-topic comments. Some sites block automated readers. If a page refuses, ask the user to paste
   the thread text with its URL, or to read it in their own browser.
3. **Write `research.json`** in the pre-production folder:
   - `question`, `topic`, `place`, `quiz` (a key in `QUIZZES`).
   - `sources`: each with `url`, `community` and `comments_read` (a whole number you actually counted).
   - `reasons`: 3 to 7 entries (five is the usual count). Each has `id`, `label`, `count` (a whole number
     above 0), `quotes` (one to three, each with `text` up to 200 characters and a `url`, and no usernames),
     and a `rebuttal` with `stat`, `value`, `source` and `url`. An optional `surprise` line is allowed.
   Every rebuttal needs a fetched, named source. Cut any reason you cannot source.
4. **Tally.** `python3 scripts/countdown.py tally <folder>` validates the research, ranks the reasons and
   writes `countdown.json`. It lists every problem at once. Fix them all, then read the table and the
   title warnings. The title is the viewer's question, one CAPS word, and the year.
5. **Packaging.** Show the user the title, a 2 to 4 word thumbnail line, and the one object or number that
   carries the story. Get a yes before filming.
6. **Script.** `python3 scripts/countdown.py script <folder> [--out <path>] [--date MMDDYYYY]` writes the
   read-aloud skeleton. Without `--out` it goes to a fixed folder, so pass your own path. Fill every bracket
   in the creator's voice. Then:
   - Spell out numbers and URLs the way they are said ("one point four percent", "quiz dot example dot com
     slash beach"). Teleprompters stall on digits. Exact figures stay as digits in the on-screen text.
   - Round money in speech ("just over a hundred thousand dollars") and keep it exact on screen.
   - The source line says what was done: "I read N comments across M threads". Never "I posted", "I
     surveyed" or "I polled".
   - The call to action sits after reason #4.
7. **Prompter (optional).** Write `prompter.txt` from the script body: one phrase per line, about 55
   characters at most, headings as cues, a blank line between paragraphs. Load it into any teleprompter app.
   Do not start the pipeline until the creator says the take is done.
8. **Job.** `python3 scripts/th.py new <video.mp4> --title "..." --word <word>`, then
   `python3 scripts/th.py enhance <job>` (voice cleanup, can run in the background). Copy the tally in:
   `cp <folder>/countdown.json jobs/<job>/`.
9. **Sections.** `python3 scripts/countdown.py sections <job>` plans the sections and prints warnings. Read
   them, then run `python3 scripts/countdown.py sections <job> --apply`. It writes the beat sections, the end
   card and the on-screen call-to-action bar. It refuses when a "number N" line is missing from the transcript.
10. **Refine `job.json` by hand.** Adjust `framing`, `punches`, `captionFixes`, `chapter` labels and headlines.
    Expect PACING warnings in two places: the hook (the creator is alone on screen, so add a headline section
    or a cutaway) and any reason beat longer than 7 seconds (add a 3 to 5 second cutaway on the phrase it
    illustrates). Quotes stay verbatim.
11. **Check and sheet.** `python3 scripts/th.py check <job>` (fix every PACING and cue error), then
    `python3 scripts/th.py sheet <job>`. Read both contact sheets yourself, fix what you can see, then send
    the user both sheets and END YOUR TURN. This is a hard gate.
12. **After go.** `python3 scripts/th.py approve <job>`, then `python3 scripts/th.py render <job>` (run it in
    the background), then `ffprobe` both files. Add a music bed only if the user picks one:
    `python3 scripts/th.py music <job> <track>`.
    - Editing the YouTube text, the Shorts list or the thumbnail after approval does not void approval.
    - Editing sections, the counter, the end card, lower thirds or cues does. That needs a fresh sheet and a new go.
13. **Shorts (optional).** Cut two or three self-contained reasons, each 20 to 55 seconds:
    `python3 scripts/th_shorts.py sheet <job>`, then `approve <job>`, then `cut <job>`. Same gate.
14. **Thumbnails (optional).** Add a `thumbnail` block to `job.json` with `lines` and a `face` pose time.
    Run `python3 scripts/yt_thumb.py --job <job>` and read `out/thumb_variants/phone_sizes.jpg`. Test three
    versions in YouTube Studio's Test & compare (desktop only): A with the face, B the same layout without
    the face, and C plain.
15. **Links, in this order.**
    1. `python3 scripts/countdown.py quizlink <job>` writes the call and quiz links into the description,
       the Shorts list and the pinned comment.
    2. `python3 scripts/th.py kit <job>` rewrites `out/youtube.md` from scratch.
    3. `python3 scripts/countdown.py quizlink <job>` again, so the pinned comment is added to the new file.
       Skipping this drops the pinned comment.
    4. Once a companion article is live: `python3 scripts/fv.py bloglink <job> <url>`.
16. **Publish kit (optional).** Copy the script into `out/script.md`, and write a companion article
    (`out/blog.md`) if the user wants one.

## Rules

- Stay on the subject. Do not claim who lives somewhere, and do not steer by protected traits or school
  ratings. Check the rules for your own field before you publish.
- Never quote a username. Strip `u/name` from anything you quote. The tally refuses them.
- Quotes are verbatim, under about 25 words, with a URL each.
- Counts come from `sources[].comments_read`. Do not round them up or invent a survey.
- No em dashes in scripts, titles or descriptions.
- A count is a count of what was read. Say "most of the comments I read", not "most people".

## Troubleshooting

- **`tally` says unknown quiz:** add that slug to `QUIZZES` in `scripts/countdown.py`, or fix the slug in `research.json`.
- **`tally` says comments_read totals 0:** count the comments you actually read and record them.
- **`sections` refuses:** a "number N" line is missing from the script. Restore it.
- **PACING warnings:** add a headline section or a cutaway over the flagged stretch.
- **The title warning:** rewrite the question with one CAPS word and the year.
