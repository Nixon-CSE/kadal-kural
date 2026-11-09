// Harbour Shift: the content and rules of the game, kept apart from its UI.
// The story orders' outcomes are pinned by tests/test_sandbox.py against the real firewall.

export type Choice = "dispatch" | "hold";
export type Verdict = "BOOKED" | "CREDIT_HOLD_BREACH" | "PENDING_CLARIFICATION";

export interface StoryOrder {
  heard: string;
  gloss: string;
  /** What the trader actually meant, revealed after the player decides. */
  truth: string;
  right: Choice;
  /** Cost if the player dispatches when they should have held. */
  lossIfDispatched: number;
  lesson: string;
  verdict: Verdict;
  /** Index into OPENING_CREDIT, or null for an unknown buyer; and the value as heard. */
  buyer: number | null;
  value: number;
}

export const STORY_ORDERS: StoryOrder[] = [
  {
    heard: "குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு",
    gloss: "Kumaran · 20 kg tiger prawn · ₹500/kg",
    truth: "Exactly what was said. ₹10,000, well inside Kumaran's credit.",
    right: "dispatch",
    lossIfDispatched: 0,
    lesson: "A clean order: book it and keep the line moving.",
    verdict: "BOOKED",
    buyer: 1,
    value: 10000,
  },
  {
    heard: "செந்திலுக்கு 40 கிலோ வஞ்சரம் 740 ரேட்டு",
    gloss: "Senthil · 40 kg vanjaram · ₹740/kg",
    truth: "Heard right, but ₹29,600 takes Senthil to ₹1,57,600 against a ₹1,50,000 limit.",
    right: "hold",
    lossIfDispatched: 7600,
    lesson: "The order was fine. The buyer's credit was not. Nobody does that sum in their head at 4 AM.",
    verdict: "CREDIT_HOLD_BREACH",
    buyer: 0,
    value: 29600,
  },
  {
    heard: "குமரனுக்கு 20 கிலோ டைகர் பிரான் 60 ரேட்டு",
    gloss: "Kumaran · 20 kg tiger prawn · ₹60/kg",
    truth: "They said 600. The ice crusher swallowed a zero: ₹60/kg is not a prawn price.",
    right: "hold",
    lossIfDispatched: 10800,
    lesson: "One misheard digit, ₹10,800 under-billed. A plausibility check would have asked again.",
    verdict: "PENDING_CLARIFICATION",
    buyer: 1,
    value: 1200,
  },
  {
    heard: "புது கடைக்கு 30 கிலோ வஞ்சரம் 500 ரேட்டு",
    gloss: "“New shop” · 30 kg vanjaram · ₹500/kg",
    truth: "There is no buyer called “new shop”. Dispatching would send ₹15,000 of fish to nobody's account.",
    right: "hold",
    lossIfDispatched: 15000,
    lesson: "Unknown buyer: never guess who it was. Ask.",
    verdict: "PENDING_CLARIFICATION",
    buyer: null,
    value: 15000,
  },
  {
    heard: "செந்திலுக்கு 10 கிலோ வஞ்சரம் 700 ரேட்டு",
    gloss: "Senthil · 10 kg vanjaram · ₹700/kg",
    truth: "A smaller order: ₹7,000 keeps Senthil at ₹1,35,000, inside the limit.",
    right: "dispatch",
    lossIfDispatched: 0,
    lesson: "Held once does not mean held forever: the right-sized order goes through.",
    verdict: "BOOKED",
    buyer: 0,
    value: 7000,
  },
];

export const OPENING_CREDIT = [
  { name: "Senthil Sea Foods", tamil: "செந்தில்", owed: 128000, limit: 150000 },
  { name: "Kumaran Stores", tamil: "குமரன்", owed: 42000, limit: 80000 },
];

export const STAKES = [
  { front: "Credit runs on trust", back: "Wholesale fish moves on credit: buyers settle later. One forgotten limit and the desk carries the loss.", stat: "₹1,50,000", statLabel: "one buyer's limit" },
  { front: "Noise eats digits", back: "Harbour, market, traffic and ice-crusher noise turn 600 into 60 and names into strangers.", stat: "85 dB", statLabel: "a busy harbour" },
  { front: "No screens on the dock", back: "Hands are wet and full. Orders are shouted, not typed; the ledger is written later from memory.", stat: "0", statLabel: "keyboards at the auction" },
  { front: "Errors are silent", back: "A wrong dispatch is not noticed at the dock. It shows up days later as a short payment.", stat: "Days", statLabel: "before anyone notices" },
];

export const CHECKPOINTS = [
  { id: "hear", title: "Hear", body: "Gnani Prisma turns the shouted Tamil into text, frame by frame, over the noise.", icon: "ear" },
  { id: "understand", title: "Understand", body: "Tamil number words and case endings are normalised; buyer, item, unit and rate are matched to the catalog.", icon: "brain" },
  { id: "gate", title: "Gate", body: "Unsure of any part, or a price that makes no sense for the item? Ask again instead of guessing.", icon: "gauge" },
  { id: "credit", title: "Credit check", body: "Add the order to the buyer's balance. Over the limit means the fish stays on the dock.", icon: "shield" },
  { id: "record", title: "Record and reply", body: "Write an append-only ledger entry and answer the trader in Tamil, in under half a second.", icon: "check" },
] as const;

export type CheckpointId = (typeof CHECKPOINTS)[number]["id"];

/** The checkpoint at which the firewall settles each story verdict. */
export const VERDICT_STOP: Record<Verdict, CheckpointId> = {
  BOOKED: "record",
  CREDIT_HOLD_BREACH: "credit",
  PENDING_CLARIFICATION: "gate",
};

export const AFTER = [
  { title: "Ledger", body: "Every decision, append-only, with what was heard. Undo adds a reversing entry.", to: "/ledger", icon: "book" },
  { title: "UPI QR", body: "Booked orders carry a payment link the buyer can scan on the spot.", to: "/ledger", icon: "qr" },
  { title: "Buyers", body: "Live credit dials and a what-if check before quoting a big order.", to: "/buyers", icon: "users" },
  { title: "Phone line", body: "Away from the desk? The same firewall answers a phone call.", to: "/phone", icon: "phone" },
] as const;

/* ---------- progression ---------- */

export const RANKS = [
  { name: "Deckhand", min: 0 },
  { name: "Dispatcher", min: 300 },
  { name: "Harbour Hero", min: 800 },
];

export const BADGES = {
  first_shift: { title: "First shift", body: "Finished the 4 AM shift by hand." },
  stakes: { title: "Knows the stakes", body: "Flipped every card." },
  builder: { title: "Firewall builder", body: "Put all five checkpoints in order." },
  flawless_build: { title: "Flawless build", body: "Built the firewall without a wrong move." },
  witness: { title: "Saw it work", body: "Watched the firewall run the same shift." },
  hero: { title: "Harbour hero", body: "Finished the story." },
  streak5: { title: "On a roll", body: "Five right predictions in a row." },
  streak10: { title: "Reads the firewall", body: "Ten in a row." },
  rush: { title: "Rush-hour regular", body: "Scored 10 in rush hour." },
} as const;

export type BadgeId = keyof typeof BADGES;

/* ---------- challenge orders ---------- */

const BUYERS = [
  { word: "குமரனுக்கு", name: "Kumaran", canonical: "Kumaran Stores" },
  { word: "செந்திலுக்கு", name: "Senthil", canonical: "Senthil Sea Foods" },
];
const ITEMS = [
  { word: "டைகர் பிரான்", name: "tiger prawn", lo: 300, hi: 1500 },
  { word: "வஞ்சரம்", name: "vanjaram", lo: 400, hi: 1600 },
];

export interface ChallengeOrder {
  id: number;
  text: string;
  gloss: string;
  /** Canonical buyer name when the buyer is real, else null. */
  buyer: string | null;
  value: number;
  band: [number, number];
  rate: number;
}

let orderSeq = 0;

const pick = <T,>(xs: readonly T[]) => xs[Math.floor(Math.random() * xs.length)];
const between = (lo: number, hi: number, step = 10) => Math.round((lo + Math.random() * (hi - lo)) / step) * step;

/** A random spoken order. Some are clean, some carry a trap the firewall should catch. */
export function nextChallengeOrder(): ChallengeOrder {
  const buyer = pick(BUYERS);
  const item = pick(ITEMS);
  const roll = Math.random();
  let qty = pick([5, 10, 15, 20, 25, 30]);
  let rate = between(item.lo + 100, Math.min(item.hi, 900));
  let buyerWord = buyer.word;
  let buyerName = buyer.name;
  let canonical: string | null = buyer.canonical;
  if (roll < 0.18) rate = pick([40, 50, 60, 80]); // a dropped digit
  else if (roll < 0.3) { buyerWord = pick(["புது கடைக்கு", "அண்ணனுக்கு"]); buyerName = buyerWord === "புது கடைக்கு" ? "“new shop”" : "“brother”"; canonical = null; }
  else if (roll < 0.55) qty = pick([60, 80, 100, 120]); // big enough to test credit
  return {
    id: ++orderSeq,
    text: `${buyerWord} ${qty} கிலோ ${item.word} ${rate} ரேட்டு`,
    gloss: `${buyerName} · ${qty} kg ${item.name} · ₹${rate}/kg`,
    buyer: canonical,
    value: qty * rate,
    band: [item.lo, item.hi],
    rate,
  };
}
