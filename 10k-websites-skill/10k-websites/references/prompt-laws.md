# The Hero-Video Laws and Prompt Construction

Design every shot by these laws BEFORE generating. They predict which concepts land first-try and which burn credits. Each one came from a real build that either succeeded because of it or failed without it.

## The twelve laws

1. **The motion agrees with the scroll.** Scrolling down must read as going down, opening up, or arriving: a pour, a descent, a teardown, an approach. Ask of every concept: "when the visitor scrolls down, does this motion feel like down?" A subject that flies UP while the visitor scrolls down fights the page and always loses.

2. **One subject, one continuous motion, no cuts.** A single subject travels through a single journey. Do not ask AI video to turn one thing into a different thing: transformations between two subjects are the hardest shot in AI video and burn money. If the user insists on one, hide the swap inside a flash or cloud moment, keep one unbroken trajectory (same heading, same position, same speed on both sides of the swap), and expect retries.

3. **Lock the path, free the body.** The trajectory stays rigid, but the subject on it must stay alive: natural movement, ripple, small adjustments. The scene needs life too: drifting steam, streaking cloud, shifting light. Never stabilize a shot by freezing the subject. A frozen subject on a clean path reads as dead footage.

4. **Plan the ending first.** The final frame is where the page comes to rest, so write it into the prompt explicitly as a composed, satisfying arrival: the cup settled on the counter, the product assembled, the destination reached. An awkward ending makes an awkward website. If the ending is a product showcase, compose it with generous margin above and below the whole product: the site's header sits over the top of the frame, and cover-cropping eats the edges on wider or shorter screens. A product with its top cut off reads as an accident; squeezed against the nav it reads as busy. The alternative that dodges the problem entirely: a full-bleed texture ending with nothing croppable is text-safe on every screen. Verify by viewing the ending frame with the header mocked over it, at a wide window and a short one, before approving.

5. **Choose forgiving subjects.** Fluids, mist, steam, light, fabric, and distant silhouettes render beautifully. Anything whose exact anatomy every viewer knows up close (controllers, keyboards, hands, familiar animals in detail) will show its errors instantly. Keep risky detail distant, simple, and moving.

6. **Prefer a vertical motion axis.** A straight up-and-down journey matches the scroll axis one to one, so the reveal moves with the page in both directions. Not mandatory, but when two concepts are equal, take the vertical one.

7. **Compose for the layout.** Decide during concept design where the action sits in frame, and leave intentional negative space for the page's captions and story to live in. The action lane stays clear; the words flank it.

8. **Sell the boundary crossings.** When the camera passes through a surface (into water, through mist, past glass), write the physical lens moment into the prompt: a splash, droplets on the lens, a beat of blur. A clean pass through a boundary reads as fake; the mess is the realism.

9. **If the hero features a product, brand it or frame it close.** A generic unbranded object at distance reads as a placeholder. Either apply the brand mark via image editing before animating, or write the ending to land close enough that the object's design carries it.

10. **Text over footage earns its legibility.** Live video behind type is a moving background you do not control frame to frame. So every text band gets a legibility system: a local scrim (a soft dark gradient behind the words) that deepens only while that band is active, a real text shadow, and a contrast check against the WORST frame of that band, never the average. Place each band in the calmest region of its frames. If a line cannot be read at a glance over the busiest moment of its band, it fails. The working system, with code and the audit, is in `scrub-pipeline.md`.

11. **Pace text in scroll distance, not seconds.** A scroll site is read in flicks, not played at 24 frames per second. Give every caption beat a long fully-visible plateau (most of its band, enough to survive several normal scroll flicks) with short eased ramps at the edges, so a reader never sees text pop in and vanish between two flicks and never has to stop dead to catch a line. Test the beat map by flick-scrolling like a real visitor, not by slow dragging. The exact numbers and the flick test are in `scrub-pipeline.md`.

12. **The standing guards:** write "no text, no logos, no lettering anywhere" into every image and video prompt. Decline the generator's preset suggestions when you have a designed shot. And never build the site around footage the user has not approved: silent scaffolding during a render wait is fine, but nothing gets shown or finished until the video passes its gate.

## Prompt construction

### Start frame template (image, 16:9, 2k, about 2 credits)

Compose the image as frame one of the motion: the subject positioned so the journey can begin.

```
[SUBJECT] at [POSITION IN FRAME], composed as the first moment of a motion
that will [ONE-SENTENCE JOURNEY]. [LIGHTING: source, direction, mood].
[PALETTE: the three to five brand colors described as materials and light,
not hex codes]. [ATMOSPHERE: the ambient life the scene carries]. Intentional
negative space at [WHERE THE CAPTIONS WILL LIVE]. Cinematic, photorealistic,
16:9. No text, no logos, no lettering anywhere.
```

**The negative-space phrasing trap: never name empty space as darkness or emptiness.** When you reserve room for captions, describe the scene as one continuous world filling the frame edge to edge, with the calm region as part of that world: soft shadow, receding depth, a plain surface. Ask for "generous empty darkness left and right" and the model paints literal black side panels, which costs a re-roll. Edge-to-edge phrasing lands first try.

The same trap has a symmetry case. When the composition needs a centered subject, "centered" alone is not enough. Say the subject bisects the frame, dead center, the same distance from the left edge as from the right. Describe both halves as one identical treatment, and explicitly ban objects, machine parts, and bright highlights on either side. A real build took three attempts before this phrasing landed the shot.

If the user supplied a real product photo, that photo can be the start frame instead. Inspect it for resolution and composition first, and confirm the negative space works for the layout.

When the subject is a real person (the owner, the chef, the maker), their photo rides in as a reference image instead of a start frame: generate the start frame with a model that takes character references, restate their recognizable details in the prompt (hair, glasses, clothing), and inspect the result for likeness the same way you inspect for trademarks. Likeness is a brand-coherence detail; a near-miss face fails the whole site. And one hard rule before any face is generated: only use a photo of the user themselves or of a person who has agreed to appear on the site. If the photo is of anyone else, stop and ask before generating.

### Video template (image-to-video, 1080p, 6 seconds, standard mode, no audio; about 54 credits on the top-priced model, far less on a mid-priced one)

```
One continuous shot, no cuts. [SUBJECT] [VERB OF THE JOURNEY: pours, descends,
approaches, assembles] from [START STATE] to [END STATE] along [THE EXPLICIT
TRAJECTORY: straight down the center of frame, a slow forward push, etc].
The [SUBJECT] stays alive throughout: [SMALL NATURAL MOTION: ripple, sway,
micro-adjustments]. The scene stays alive: [AMBIENT LIFE: drifting steam,
shifting light, streaking cloud]. [IF A BOUNDARY IS CROSSED: the physical
lens moment, e.g. a splash and droplets on the lens with a beat of blur].
The shot ends at rest: [THE COMPOSED FINAL FRAME, fully described: what sits
where, what the light does, why it feels arrived]. No text or lettering
anywhere.
```

Generate at 1080p, not 4K. The web version gets re-encoded and compressed anyway, and 4K only multiplies the cost.

## The chaining recipe (Tier 2: a 15 to 20 second scroll journey)

One long journey built from 6-second segments that join invisibly:

1. Generate segment 1 from the start frame. Run the full inspection and ⛔ VIDEO GATE on it alone.
2. Extract the final frame of the approved segment as a full-quality PNG with ffmpeg (exact command in `ffmpeg-recipes.md`; review-grade jpgs are not good enough to chain from).
3. Upload that PNG to Higgsfield. This is the bridge from a local file to a `start_image`, and it has three steps: call `media_upload`, which returns a presigned PUT URL (a temporary upload address). Then PUT the raw PNG bytes to that URL, for example `curl -X PUT --upload-file final.png "<presigned-url>"`. Then call `media_confirm` to register the upload. The confirmed media id is what you pass as `start_image` for the next segment's image-to-video call.
4. Write the next segment's prompt so the motion CONTINUES: same heading, same speed, same lighting, picking up exactly where the previous segment rested. The join is invisible only if the motion vector never breaks. Special case that comes up often: when a segment ends in a near-empty or near-black frame (say, a single point of light), the next segment's prompt must explicitly describe what grows out of that frame. Do that and the join disappears.
5. Gate each segment separately. A rejected segment is a cheap single re-roll, not a redo of the whole journey.
6. Join the approved segments into one file with the single-encode concat in `ffmpeg-recipes.md`: feed the RAW segments into one filter and encode exactly once with the scrub settings. One encode means the joins cannot mismatch. The fallback, when raws are unavailable, is to encode every segment with IDENTICAL settings and join with the concat demuxer; identical parameters are what keep that path invisible at the joins, and mismatched ones glitch at every join.
7. The joined file is the one scrub video the page uses. The page never knows it was segments.

Only the final segment needs the composed resting ending (law 4). Middle segments should end mid-motion so the next one can continue it.

**The seam law: texture identity does not carry over.** Each generation re-imagines fine texture from its start frame. Position carries over; the exact weave, grain, or skin does not. So a rest-to-rest join on hyper-specific texture shows as a visible cut even when the motion vector is perfect. Storyboard every seam to land inside motion, or inside a moment that motivates a texture refresh: a sweep across the lens, a blur beat, a moment of darkness, a shift of light. Never butt two rest states together on specific texture. If a chain is already generated and a seam shows anyway, the rescue is the crossfade join in `ffmpeg-recipes.md`.

**Which worlds chain reliably:** abstract worlds (pure light, particles, atmosphere) are the chaining reliability champions. With no anatomy for a continuation prompt to get wrong, a three-segment chain can land first-try on every segment. When a Tier 2 concept is on the fence, this is a strong reason to go abstract.

## Declining presets

The generator sometimes pattern-matches your prompt and offers a house preset instead of generating your shot. Decline it and retry with your literal prompt. Your designed shot obeys the laws and composes for your layout; a preset does neither.

## Cost preflighting

Before ANY generation, check the exact price of the exact call you plan with `get_cost: true`. It is free. Tell the user each price in plain words before it moves: the starting frame's price before the frame ("The starting image costs about 2 credits, making it now"), then the video model menu with real prices once the frame is approved, before any video credits move. The cheap step first, the big decision second, every number real.

**The video model is a real choice, and the user makes it.** The connector offers several video models, and the price spread on identical parameters (same duration, same resolution, same mode) has measured about five to one between the top-priced model and a mid-priced one. Both ends are genuinely top tier as of this writing: independent leaderboards rank the proven default at the very top for overall quality and prompt fidelity, and the mid-priced alternative among the best for physics and cinematic motion. So preflight the SAME planned shot across the top two or three video models. Discover the current lineup with the connector's model catalog; `get_cost` is free on every one. Then present the real numbers with the honest tradeoff: the proven default is what these laws were tuned on and buys the highest ceiling; the mid-priced model is legitimate and turns a small or trial balance from one shot into many, which changes the video gate from frightening to a normal creative decision. Their money, their choice, made before anything is spent.

At the proven defaults a hero image costs about 2 credits and a hero video about 54, which is the top of the video range, and a free trial covers roughly one hero pipeline plus one retry, more with a cheaper video model. For a chained journey, preflight the whole chain and present the full total up front, per segment.
