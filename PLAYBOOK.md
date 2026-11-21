# Hard-won rules

Lessons from making faceless and template videos with this toolkit. Each rule is a habit that saved a re-render. Read this before your first render, and again when a shot comes back wrong.

## Image prompts

- **Lead with the action, then the character, then the style.** Image models weight the early words most. Start with the count and framing: "solo shot of exactly one cartoon stick figure, alone, ...". Wide frames make models duplicate characters, so say "only one person in frame".
- **Never restate a character's look in a shot prompt.** When the tool injects a character description (triggered by the reference phrase "the main character"), your own copy makes the model see the description twice. The result is giant detached heads and doubled figures. Describe the action and the setting, and let the injection do the rest. Supporting cast with no injected description gets an inline description.
- **Describe what is there, not what is missing.** Negations are unreliable: "no seals, no flags, no people" can return all three. Describe the bare, empty surface instead.
- **Put a no-text line in every style suffix.** Use "no text, no letters, no words, no numbers, no logos". Any writing surface invites fake words: documents, signs, labels, calendars, screens, speech bubbles. Prefer props with no writing surface, such as an hourglass, coins, keys, envelopes, blank frames, or wax seals. If a document is essential, add the no-text line to that shot and expect a reroll.
- **Text belongs in captions.** Stills stay text-free. The tool draws captions on top, so the words are always spelled correctly.
- **When two rerolls of one idea fail, change the idea.** A prompt for a handshake kept summoning businessmen. "Standing beside a stack of coins" came back clean on the first try.
- **Judge characters at full size.** A thumbnail shows identity and hides anatomy: detached necks, extra hands, objects merged into faces. Review hero frames one per row at 780 pixels or wider.
- **Measure sharpness before you trust a batch.** Washed-out frames look fine on a contact sheet. Blur each frame slightly and compare it with the original. Flat vector art scored about 2 or higher when clean and 0.2 to 0.6 when washed out, so a threshold near 1.5 is a starting point. Calibrate it on your own style, then reroll anything under it.
- **Use the slow model for hero frames.** Distilled fast models are cheap but break anatomy often: about 3 in 10 hero frames had structural faults in testing. Use the higher-quality model for hero frames and the fast one for scenery and props. Use the scheduler the model's documentation names. A mismatched scheduler washed out more than half the seeds in testing.
- **A repeated seed is a cache hit, not a new render.** ComfyUI returns the stored image when the prompt, seed, and size match. Change the seed, or restart the server, before you compare settings.
- **Keep the frame size fixed within a job.** A seed does not reproduce its composition at another resolution. A size change mid-job makes rerolls drift from the approved set.
- **Do not buy back adherence with guidance or reference strength.** Higher guidance drops props. Lower reference strength shreds the figure. Fix a missing prop with a reroll or a prompt rewrite.
- **Render the vertical cut natively.** Cropping the middle of a landscape frame cuts off a figure placed left or right of center. A new vertical pass is a new set of images, so review it on its own sheet. Fix single frames with a fresh seed at the vertical size.
- **The reference sheet is the character.** A reference model reproduces its flaws faithfully. A missing neck once caused floating heads across a whole batch. Open the reference at full resolution and fix it before you change prompts or training. To shrink a head without losing the character, ban the features explicitly ("blank white face, no ears, no nose, no skin tone"). Shrinking alone brings back normal human features.
- **Automatic QC screens for gross breakage only.** A vision check catches missing limbs and floating heads. It misses a head that is merely too big. Read its report, then look at every hero frame yourself.

## Character consistency and LoRA training

- **Caption only what varies.** In LoRA captions, name the pose and the background, never the character's traits. Traits named in captions get absorbed by those words, and the trigger word learns nothing.
- **Cull the training set by eye, at full size.** Models drift skin tone and hair on many renders. Check every training image before training starts.
- **Make the least stable trait large and identical in every image.** Hair colour drifted in a set where the hair was inconsistent.
- **Test a LoRA against no LoRA before you trust it.** Run the same prompts and seeds at strength 0 and at full strength. Use at least ten pairs across two seeds, because one lucky seed once made a weak LoRA look good. Deploy only a LoRA that wins side by side.
- **Train only under a memory cap.** An uncapped run once used all the memory on a machine, killed its services, and needed a hard restart. Run training through a service unit that sets a memory limit (systemd `MemoryMax`), never by hand.

## Staging and writing

- **Scene 1 is the hook. The last scene pays it off.** Open on the problem, the number, or the surprise. Never open on a greeting or setup.
- **One shot per sentence, a cut every two to three and a half seconds.** The picture should act out the sentence. A character standing beside a backdrop for eight seconds reads as a slideshow.
- **Change framing between cuts.** Alternate wide, medium, and close shots so consecutive cuts read as edits, not one picture held.
- **Match the expression to the beat.** Figure poses default to smiling. Set the mood per scene: worried or neutral for problems, happy only for real good news.
- **Spend motion on a few scenes.** A video-model clip takes about a minute to render. Use it for the hook and the payoff. Pan a still everywhere else.
- **A graphic needs a point.** A stat comparison, a list, or one punch line works when the number or the words are the point. A run of graphics with no pictures reads like a slide deck.
- **Say the labels out loud, in order.** Graphics that cue off the narration appear when their words are spoken.
- **Check facts before you render.** A supplied script renders word for word, so its errors ship. Check numbers, dates, and legal claims against the current primary source. Summaries of an earlier draft are the usual cause of a wrong claim.
- **Never put a countdown into narration or a title.** "11 days left" goes stale the day the video is published. Name the date instead.
- **Keep the narration short and plain.** One to three spoken sentences per scene, one idea each. Write it the way a person talks.

## Voice and audio

- **Text-to-speech can skip, add, or repeat words.** Transcribe every read, compare it with the script, and retake the scenes that differ. Listen to a flagged scene before you call it broken, because the transcriber can mishear a clean read.
- **Never speed a cloned voice up after it is read.** Speed-ups above about 5 percent make it sound robotic. Trim pauses instead.
- **Do not add dynamic loudness normalization to a voice.** It lifts room echo. A straight gain to a target, then a peak limiter, keeps the room quiet.
- **Target -16 LUFS for narrated videos.** Keep true peak under -1 dBTP. Listeners in testing found -19 too quiet and -15 a little loud, so -16 is the starting point. Check every final with a loudness and peak check.
- **Check the final mix, not only the voice.** Quiet stretches under speech and a hot peak both ship if nobody measures them.
- **Keep music about 18 percent under narration.** Loop the bed for the length of the video. A bed that is too loud hides the voice.
- **Use sound effects sparingly.** A hit between every scene reads as cheap. Use one on the hook, a reveal, or the call to action.
- **Trim long pauses in a recorded voice-over.** A pause over about a third of a second inside a scene makes a read feel slow. Keep half of each pause on each side so breaths stay natural.
- **Apply a microphone EQ only to the microphone it was made for.** Skip it for any other mic.

## Preview and approval

- **Review before you render the final.** Show both contact sheets, landscape and vertical, before any finished render. Any edit after approval voids it: regenerate, show the sheets again, and approve again.
- **Waive the review only for one job, and only when the user asks.** A waiver never carries over to the next job.
- **Nothing publishes on its own.** Staged output goes to the user. Posting, emailing, or uploading to a public channel happens only on the user's explicit go.
- **Keep the two cuts telling one story.** When you reroll a scene in one cut, reroll the same scene in the other.
- **Write post-publication links to a side file.** A video ID written into the scene file after approval voids the approval. Keep links in their own file.
- **Check the output before you report it.** Pull a frame from the middle and one from the end of each mp4, and look at them. Check that captions are spelled correctly and timed to the words.
- **Test thumbnails three ways.** Make one with a face, the same one without it, and a plain one. Let the viewer data decide between them.

## Build and render safety

- **Bundle the caption font with the project.** A system font changes the wrap width and the box size, so the same caption looks different on another machine. Pin the text layout engine too.
- **Draw captions as images if your ffmpeg has no text filter.** Some ffmpeg builds lack the text and subtitle filters. Render captions with an image library and overlay them.
- **Keep the computer awake during renders.** A sleeping computer stops a render partway, and the failure can look like a timeout. On macOS, run `caffeinate -i` for the length of the job. On Windows, set the power plan to never sleep while plugged in. Stay on AC power.
- **Run long jobs detached.** `python3 scripts/bg_run.py --name <label> -- <command>` keeps a render running when the session or connection drops, and writes a status file to `jobs/_bg/`. Read that file before you assume the job finished.
- **Check the media server before a run.** Call its `/health` endpoint first. If it fails, report it and wait.
- **Do not restart a shared model service mid-run.** A large model can take ten minutes or more to load again. Other jobs may depend on it.
- **Keep keys out of version control.** `config.env` belongs in `.gitignore`. Keys live only there, and only the example file goes into a repository.
