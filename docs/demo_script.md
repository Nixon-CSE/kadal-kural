# Demo script and submission pack

For the Gnani **Great Indian AI Internship Challenge**. Submissions close **10 Nov 2026, 11:59 PM IST**.

Every spoken order below was run through the real firewall on 9 Nov, from freshly reset balances. The results shown are what the desk returns.

---

## 0. What the brief asks for, and where it is

| Requirement (gnani.ai/internship) | Status |
|---|---|
| Working app on at least one Gnani model or API | ✅ **Prisma v2.5** streaming STT and **Timbre v2.5** streaming TTS, live over `wss://api.vachana.ai` |
| Demo video, public | ⬜ Record from this script: a 60 s cut and a full cut |
| Written explanation | ✅ Section 4 below |
| List of Gnani models and APIs used | ✅ Section 4 below |
| Title, problem, target users, each member's contribution | ✅ Section 4 below (fill in the contribution line) |
| Public post on LinkedIn and/or X, tagging Gnani AI, with #GreatIndianAIInternshipChallenge and #GnaniAI, **live before you submit** | ⬜ Section 5 below |
| Synthetic data only (no real phone numbers or IDs) | ✅ Buyers, numbers, rates and UPI ID are all made up; the buyer "Call" button was removed |
| Agent Builder | ⚠️ The brief says it is **out of scope**. Show the phone line only as a bonus, and never as the Gnani usage being judged |

**Awards this entry fits:**
- **Mixed Vibes:** Tanglish orders, Tamil number words
- **Real Deal:** fish-market credit, a real cash-flow problem
- **Noise Canceller:** 8 kHz telephone-band audio, four noise profiles
- **Main Character:** Tamil
- **Demo Day Drop:** the 60-second cut

**The shortlist is decided by verified engagement on your post.** The post is not paperwork: it is the first gate. Post as early as you can.

---

## 1. Before you record (10 minutes)

1. Start the server with the live key: `make run`. The header should show two green dots, one for speech and one for the phone line.
2. Press ⌘K → **Reset balances**. Senthil should show **₹22,000 left** and Kumaran **₹38,000 left**.
3. Use Chrome at 110% zoom. Hide the bookmarks bar. Turn on Do Not Disturb. Close other tabs.
4. Open the Gnani dashboard and check you have credits left.
5. **Record system audio as well as your mic.** The Tamil reply from Timbre is the proof that Gnani is speaking. macOS ⌘⇧5 cannot record system audio; use OBS (Desktop Audio plus Mic) or Loom.
6. **Noise track:** `harbour_market_noise_90s.wav` (path in the chat). It is synthetic harbour, market and ice-crusher noise from `benchmark/noise_profiles.py`. AirDrop it to your phone and play it from the phone speaker about a metre from the laptop, at conversation volume.
7. Do one dry run of the whole script, then press Reset balances again before the real take.
8. Speak each order **in one breath**, at normal speed. Wait for the reply before the next order.

---

## 2. The 60-second cut (Demo Day Drop, and the video for your post)

The aim is one idea that lands: **the fish never leaves the dock on a misheard number or a bad debt.** Use big captions, because most people watch with the sound off.

| Time | Screen | You say (or play) | Caption |
|---|---|---|---|
| 0:00–0:04 | Home page hero. Noise track already playing | *(noise only)* | **4 AM, Kasimedu harbour. Orders are shouted, in Tamil, over engines.** |
| 0:04–0:10 | Click **Open the desk** | VO: "One misheard rate, or one buyer pushed past their credit, and the fish is gone before anyone notices." | **One wrong number = lakhs lost** |
| 0:10–0:22 | Press Space and speak. A Booked card appears; the Tamil reply plays | **குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு** | **Gnani Prisma hears Tanglish through the noise → Booked ₹10,000 → Timbre answers in Tamil** |
| 0:22–0:34 | Speak. A red **Credit hold** card appears | **செந்திலுக்கு 50 கிலோ எக்ஸ்போர்ட் வஞ்சரம் 800 ரேட்டு** | **₹40,000 order, ₹22,000 credit left → held. Not dispatched.** |
| 0:34–0:42 | Speak. The trader corrects it; Booked | **செந்திலுக்கு 25 கிலோ மட்டும் போடு** | **The trader fixes it by voice → ₹20,000 booked** |
| 0:42–0:50 | Speak. An amber **Ask again** card appears | **குமரனுக்கு 20 கிலோ டைகர் பிரான் 60 ரேட்டு** | **₹60/kg isn't a prawn price → it asks. It never guesses.** |
| 0:50–0:56 | Scroll to the ledger. Click the booked row; the UPI QR opens | VO: "Every decision is a ledger line, and booked orders come with a UPI link." | **0 of 560 noisy trades booked wrongly** |
| 0:56–1:00 | End card: logo and URL | VO: "Kadal Kural. Built on Gnani Prisma and Timbre." | **Kadal Kural · Gnani Prisma + Timbre · #GnaniAI** |

Cut the silence between orders hard in editing. Keep every reply audible.

---

## 3. The full cut (about 2:45, for the submission)

### Scene 1: the problem (0:00–0:25)
- **Screen:** Play → **Story mode**, chapter 1 (the 4 AM shift, where you take orders against the noise). Play about 10 seconds of it.
- **VO:** "At Chennai's Kasimedu harbour, wholesale fish is sold on credit, by voice, in Tamil and Tanglish, at four in the morning. The dispatcher has to hear the buyer, the fish, the quantity and the rate over engine noise, and remember who already owes too much. A misheard 470 instead of 740, or one buyer pushed past their limit, and the loss is real money."

### Scene 2: what it is (0:25–0:40)
- **Screen:** the home page, scrolling slowly from the hero to "How an order is checked".
- **VO:** "Kadal Kural is a voice credit desk. Gnani Prisma turns speech into text, a deterministic engine checks it, and Gnani Timbre speaks the answer back in Tamil. No AI model ever does the arithmetic."

### Scene 3: the live desk with noise playing (0:40–1:40)
Start the noise track. Speak each order in turn:

| # | Say | Result on screen | VO line |
|---|---|---|---|
| 1 | குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு | **Booked ₹10,000.** Kumaran's balance goes up. Tamil reply | "Within credit, so it's booked, and Timbre confirms it in Tamil." |
| 2 | செந்திலுக்கு 50 கிலோ எக்ஸ்போர்ட் வஞ்சரம் 800 ரேட்டு | **Credit hold:** ₹40,000, ₹18,000 over the limit | "Forty thousand, but Senthil only has twenty-two thousand left. Held before dispatch." |
| 3 | செந்திலுக்கு 25 கிலோ மட்டும் போடு | **Booked, corrected:** ₹20,000 | "The trader just says 'make it 25'. The held order is booked at the smaller size." |
| 4 | குமரனுக்கு 20 கிலோ டைகர் பிரான் 60 ரேட்டு | **Ask again** | "Sixty rupees a kilo isn't a real prawn price, so it asks instead of guessing." |
| 5 | Say order 1 again, and **talk over the reply** while Timbre is speaking | The voice stops at once | "Talk over it and it stops in about 50 milliseconds, like a person would." |
| 6 | கடைசி ஆர்டர் கேன்சல் | **Undone:** the last booking is struck through | "Voice undo. Nothing is deleted; it adds a reversing line." |

If any order comes back as Ask again because of the noise, **keep it in.** Say "it wasn't sure, so it asked", then repeat the order. That is the product working.

### Scene 4: ledger, buyers and payment (1:40–2:00)
- **Screen:** Ledger page. Show the struck-through undo line. Click a booked entry: the drawer opens with the **UPI QR**. Then Buyers: the credit dials, and the what-if check.
- **VO:** "Every decision is an append-only ledger line. You can export it, and every booked order carries a UPI payment link for the exact amount."

### Scene 5: proof under noise (2:00–2:20)
- **Screen:** Insights → the noise benchmark table.
- **VO:** "We tested it on 405 recorded transcripts with harbour, market, traffic and ice-crusher noise at 10 and 5 dB. Zero of 560 noisy trades were booked wrongly. Anything unclear was held or asked again. The noise is synthetic, and the report says so."

### Scene 6: phone line, as a bonus (2:20–2:32)
- **Screen:** the Phone line page, then a phone on speaker placing an order. Optionally, show the ledger row appearing.
- **Caption:** **Bonus: the same firewall behind a phone call (Gnani Agent Builder).**
- **VO:** "It also works behind a phone line, and the same rules decide." Keep this short. Agent Builder is out of scope for judging, and its speech recognition is not Prisma, so do not claim Prisma here.

### Scene 7: everywhere, and the close (2:32–2:45)
- **Screen:** Chrome device toolbar (⌘⇧M), iPhone size: the desk with the bottom tab bar, then the ledger cards.
- **VO:** "It runs on a phone, a tablet or a laptop. Kadal Kural, கடல் குரல், the voice of the sea. Built on Gnani Prisma and Timbre."
- **End card:** repo URL and #GreatIndianAIInternshipChallenge #GnaniAI.

---

## 4. Submission form text

**Title:** Kadal Kural (கடல் குரல்): a Tamil voice credit desk for fish markets

**Problem:** At wholesale fish harbours like Kasimedu in Chennai, orders worth lakhs are placed by voice, in Tamil and Tanglish, over engine and market noise, and mostly on credit. A misheard rate or quantity, or a buyer pushed past their credit limit, turns into a loss once the fish has been dispatched. Nobody double-checks at 4 AM.

**Target users:** Wholesale fish dispatchers and commission agents at Indian harbours and mandis. The same pattern fits any trade where orders are spoken and given on credit, such as vegetable mandis and kirana distributors.

**What it does:** A trader speaks an order. **Gnani Prisma** (streaming STT, 8 kHz telephone-band audio) transcribes it. A deterministic engine then:
- normalises Tamil number words and case endings
- matches the buyer, item, quantity and rate
- asks again when it is unsure or the price is implausible
- holds any order that would take the buyer past their credit limit

**Gnani Timbre** (streaming TTS) speaks the decision back in Tamil. The trader can correct an order or undo it by voice, and can interrupt the reply (barge-in). Every decision is an append-only ledger line, and booked orders get a UPI payment link. No AI model does the arithmetic.

**Measured** (scripts and raw data in the repo, `benchmark/REPORT.md`):
- 0 of 560 noisy trades booked wrongly without a hold (four synthetic noise profiles, at 10 and 5 dB SNR)
- 95.7% of rates read correctly
- 392 ms from the trader's last word to the first spoken reply (P50)
- 52 ms barge-in stop (P50 of 24 live trials)

**Gnani models and APIs used:**
- **Prisma v2.5:** streaming speech-to-text over WebSocket (`wss://api.vachana.ai/stt/v3/stream`), Tamil and Tanglish, 8 kHz.
- **Timbre v2.5:** streaming text-to-speech over WebSocket (`wss://api.vachana.ai/api/v1/tts`), Tamil replies.
- *(Bonus, outside the judged APIs: a Gnani Agent Builder phone agent forwards each caller turn to the same firewall.)*

**Contribution:** *(fill in, for example: "Solo build: architecture, Tamil normaliser, credit engine, Gnani streaming clients, benchmark, web app.")*

**Links:** the repo (https://github.com/Nixon-CSE/kadal-kural), the video, and your post.

---

## 5. The public post (LinkedIn and X)

Upload the 60-second video **natively**. Don't post a YouTube link, because native video gets far more reach. Post on **both** platforms, as early as you can, and reply to every comment.

**LinkedIn:**
> At 4 AM in Chennai's Kasimedu harbour, fish worth lakhs is sold on credit, by voice, in Tamil, over engine noise. One misheard rate or one buyer pushed past their limit, and the money is gone.
>
> I built **Kadal Kural (கடல் குரல்)**, a voice credit desk that checks every spoken order before the fish leaves the dock:
> 🎙️ **Gnani AI Prisma** hears Tamil and Tanglish orders through harbour noise
> 🧮 a deterministic engine books it, holds it if it breaks the credit limit, or asks again if it's unsure (no AI does the maths)
> 🔊 **Gnani AI Timbre** answers back in Tamil, and you can interrupt it
>
> Tested on 560 noisy trades: 0 booked wrongly.
>
> Built for the Great Indian AI Internship Challenge by @Gnani AI.
> Code: https://github.com/Nixon-CSE/kadal-kural
>
> #GreatIndianAIInternshipChallenge #GnaniAI #Tamil #VoiceAI #BuildForBharat

**X:**
> Fish worth lakhs is sold on credit, by voice, in Tamil, over harbour noise. One misheard number = real loss.
>
> Kadal Kural checks every spoken order before dispatch, using @GnaniAI Prisma (STT) and Timbre (TTS). 0 of 560 noisy trades booked wrong. 🐟🎙️
>
> #GreatIndianAIInternshipChallenge #GnaniAI

Tag the real Gnani AI page. On LinkedIn, type @ and pick it from the list. Confirm the X handle before posting. Do not buy engagement or use engagement-swap groups: the rules disqualify both, and genuine shares from classmates and teachers are fine.
