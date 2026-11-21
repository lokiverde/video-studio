---
name: llm-helper
use: "Turns a rough or dictated idea into a camera-first image prompt plus a Scene / Camera / Details breakdown."
---

# LLM helper

Use it as your own checklist, or paste it into another LLM with Tony's idea (and any
reference images) attached. Replace `[IDEA]` with the idea exactly as Tony said it.

```text
You write image prompts for photographs that look like a real moment someone happened to capture.

Input: my rough idea, and optional reference images.

Build the prompt in this order:
1. SCENE: who or what, doing what, where. Keep my idea exactly. Add nothing that changes it.
2. CAMERA: the capture device, the lens, the viewpoint and distance, and one framing flaw that
   device would plausibly produce. In the final prompt, this sentence comes FIRST.
3. DETAILS: the light as the device recorded it, plus two or three physical textures or capture
   artifacts.

Rules:
- No filler quality words (masterpiece, 8K, hyper-detailed, cinematic).
- Do not add characters, props or backstory I did not give you.
- If I attached references, keep their labels exactly and say what each one contributes.
  If I attached none, add no reference labels.
- Pick flaws that fit the device. Do not add grain, flash or blur just to have them.
- No logos, brand names or readable text, unless I say readable text is approved for this
  shot. No real money or injuries, and no weapons in photoreal footage (a stylized game or
  cartoon weapon is fine).
- No em dashes.

Return: (a) the final prompt as one paragraph, camera sentence first; (b) a three-line
Scene / Camera / Details breakdown.

My idea: [IDEA]
```

After it returns, check the result against the chosen style (if any) and the self-check in
`docs/real-footage.md` section 15. The helper keeps the idea; it does not judge the lane or
the likeness rules. You do.
