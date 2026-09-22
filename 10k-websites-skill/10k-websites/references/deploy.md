# Deploy: The Hostinger Flow

One command from folder to live site. The order matters because the og tags need the live URL before the zip is made.

## The honest-costs talk (give it during setup, repeat before spending; the hosting bullet waits for Phase 10)

Money talk happens BEFORE money moves, every time:

- A hero image costs about 2 credits at the proven defaults.
- A hero video costs between roughly 10 and 55 credits depending on the video model chosen; preflight for exact numbers. The connector offers several video models, and both ends of that range are genuinely top tier as of this writing. The choice, and how to present it honestly, is in the cost preflighting section of `prompt-laws.md`.
- Every generation's exact price can be checked FREE before spending with `get_cost: true`. Preflight everything: single shots, supporting stills, and whole chains; the model comparison lives in the cost preflighting section of `prompt-laws.md`. Present the total in plain words before generating.
- Start on Higgsfield's free trial. It is enough to build a first single-journey website, retry included, and a real first build has shipped on trial credits alone. A cheaper video model stretches the trial further still, from one shot into several. Upgrade to a paid plan when building more sites or going bigger, and check current plans on higgsfield.ai instead of trusting a number written here. Say all of this plainly so the user can plan.
- Hosting is separate, and this bullet is the one that waits: it belongs to Phase 10, at the moment the user says they want the site online, never to setup. Any Hostinger plan with hPanel serves a static site. The cheapest qualifying family is Hostinger's shared web hosting plans, usually a few dollars a month on a promo term and more at renewal. Check the current price on hostinger.com instead of trusting a number written here. Deploying and re-deploying cost nothing.

## Step 0: Connect the hosting (first deploy only)

The connector is added now, not during setup, because nothing before this moment needs it. If the hosting tools already respond (connected in an earlier project, or earlier in this one), skip to Step 1.

1. The user needs a hosting plan (this is the moment the honest-costs talk's hosting bullet gets said, if it has not come up yet). The signup link to share, if it has not been shared already, is https://meticsmedia.com/hostinger-ESVT, the creator's partner link with the current discount; say so plainly in one line beside it. A user who already owns a Hostinger plan never gets the signup link. When they have a plan, they usually paste the connector command from that same page (its Install Extension button, with Claude Code selected, shows the command to copy). If they just say hosting is ready, run it yourself; it is: Windows `claude mcp add hostinger -- npx.cmd -y hostinger-api-mcp`, Mac/Linux the same with `npx`. Hostinger's connector page lists one command with plain `npx` for every platform. Read a pasted command as intent and adapt it to the machine from context: on Windows that means the `npx.cmd` form. No commentary needed.
2. Right after running it, trigger the sign-in with a harmless read request, like listing their websites. On most setups the browser opens to Hostinger within a few moments: they sign in, click Allow, and authorize once. Warn them it may open a different browser than the one they normally use, and give them a clickable check-in (one option, "Signed in, check it") to click once they have. A tool call that sits waiting during this moment is the sign-in in progress, not a hang.
3. If nothing opens, or the hosting tools do not respond, one restart fixes it, and it is the only restart Phase 10 might need: "Close Claude Code completely, open it again, come back to this same chat, and say continue. Everything is saved: your site files, this whole conversation, all of it. This restart is expected, not a problem." When a local preview server was running, add one honest line: the preview link stops working during the restart, which is also expected, and the live site is about to replace it. When they return, trigger the sign-in again.
4. Confirm the read call returns real data before deploying anything.

## Step 1: Settle the address, then patch the og tags

First, where will the site live? Look before asking: list the domains on the account. If one of them clearly belongs to this brand (the name matches the site you just built), propose it by name and ask: "I can see [the domain] on your account. Want the site live there, or on a free temporary address first?" Never assume the match, even when it is obvious; the domain is theirs and the choice is theirs. A domain registered minutes ago can take a moment to appear: if the domain the user just bought is not in the list yet, wait a minute and list again before asking. If no domain on the account fits, ask whether they have one in mind or want the free temporary subdomain. A temporary subdomain is a real option, not a lesser one: it lets them see the site live today and connect a domain later.

Then patch the tags. `og:image` and `og:url` need absolute URLs. Find the `<!-- DEPLOY STEP -->` comment left during the build and patch both with the chosen live URL. On the temporary path, create the website on the hosting and generate the free subdomain first, so the address exists to patch with. Do all of this BEFORE zipping, or the shipped page carries dead preview tags.

Patch with the editor tool, never a shell one-liner. A scripted find-and-replace can read the UTF-8 file with the wrong default encoding and mangle every special character on the page. The recovery, if it happens anyway, is in `troubleshooting.md`.

## Step 2: Zip the CONTENTS, not the folder

The zip's top level must be `index.html` itself with `assets/` beside it. Zipping the project folder instead nests everything one level down and the live site shows a directory listing or a 404.

Exclude review folders, raw videos, and anything else that should not ship. If the raws were kept outside the deploy folder as instructed, the zip is just the folder's contents as-is.

Windows PowerShell example (contents, not folder):

```
Compress-Archive -Path .\index.html, .\assets -DestinationPath ..\site.zip -Force
```

Keep the zip itself out of the deploy folder too.

## Step 3: Create the website, then deploy

1. If the website does not exist on the hosting yet, create it on the address chosen in Step 1. (On the temporary path it already exists: Step 1 created it to get the subdomain before patching.) A domain registered at Hostinger points itself automatically; nothing to configure.
2. Deploy the zip with the static deploy tool.
3. Large uploads are fine: expect a deploy carrying a hero video to take a few seconds per handful of MB. Not instant, and that is normal.

## Step 4: Verify the live site yourself (before telling the user it's done)

- The page loads over HTTPS with a 200.
- The video URL itself serves (fetch it directly).
- The browser console is clean on the live URL.
- Scrub the hero on the live site: the Blob fetch should make seeking work even on hosts without Range support, but confirm it.

**A brand-new custom domain needs a settling window.** The domain pointing itself is fast, but the HTTPS certificate (the padlock) can take a few minutes to issue on a domain that has never served a site before, and occasionally longer. If the browser shows a security warning right after the first deploy, that is the certificate still being issued, not a broken site. Tell the user plainly, wait a few minutes, and re-check before declaring the site done. Temporary subdomains come with the padlock already working.

## Step 5: The speed receipts (measure, then present)

Right after live verification, measure the live site and record the numbers. These are the proof the site is fast, and the user will need them. Measure on the live URL:

- **Total page weight excluding the video.** A healthy build lands in the tens of KB.
- **Page load time.** A healthy build loads in well under a second.
- **The video's size and its arrival time behind the loading ring.** A single shot arrives in a few seconds on an ordinary connection; a chained journey takes longer. All of it while the page is already fully usable.

**How to measure, concretely.** Two plug-and-play options:

- curl timing on the live URL: `curl -s -o /dev/null -w "TTFB %{time_starttransfer}s, total %{time_total}s, %{size_download} bytes\n" https://the-live-url/` (on Windows call `curl.exe`, and `-o NUL` also works). Run it against the page and against the video URL for the sizes and times.
- Or open the live URL through the browser tool and read the navigation timing: `performance.getEntriesByType('navigation')[0].loadEventEnd` for load time, and `performance.getEntriesByType('resource')` for each file's `transferSize`.

Real measurements only. Never present an estimate as a receipt.

Present the numbers to the user together with the structural argument, because together they answer the number one objection to cinematic sites ("pretty, but probably slow, probably a bad backend"): these sites are plain static files. No framework, no build step, no server code, so there is no backend to be bad. The video streams in behind a poster and an honest progress ring, and small screens never download the heavy version at all. Record the numbers so the user can quote them to their own client.

## Step 6: The user's real-device test

Hand the user the live link and have them test the site on desktop AND their phone, on the real network, not just localhost. Ask them to check the scroll at the top and the bottom of the hero specifically, in Chrome, where choppiness shows first. Their eyes and their hardware catch what audits cannot.

## Step 7: Iterating is cheap

Change the files, re-zip, re-deploy. One command. Do not fear polish rounds; the loop costs nothing but a minute. Re-verify the live page after each deploy (a stale cache can show the old version; hard-refresh or check a changed string).
