#!/usr/bin/env python3
"""Fill the remaining blank rows in a consolidated Pass 3 review TSV.

By default reads review_all_filled_pass3.tsv from the current directory and
writes review_all_filled_pass4.tsv beside it. Existing non-empty translations
are preserved; the embedded Pass 4 translations are assigned to blank rows in
file order. This is a historical, dataset-specific batch, not a general
Japanese-to-English translator.
"""
import argparse
import csv
from pathlib import Path
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input", nargs="?", default="review_all_filled_pass3.tsv",
        help="consolidated Pass 3 review TSV (default: %(default)s)",
    )
    parser.add_argument(
        "output", nargs="?", default="review_all_filled_pass4.tsv",
        help="output TSV (default: %(default)s)",
    )
    return parser.parse_args()


translations = [
"Ah... h-hey, don't copy me!",
"Huh? Suzuka... special?",
"Kinugawa leaves me behind and runs toward the dorm.",
"The internet's full of messages and DMs from guys whose ulterior motives are painfully obvious.",
"Ahh, d-don't... treat me like a dog... fhaaahhh!",
"No, not like this—ahh, dressed like a dog who'd be happy to obey absolutely... nghaahhh!",
"What is this...? What the hell is this?!",
"....................Please.",
"I do understand why everyone's anxious with Ayako gone.",
"So that's the last of it...",
"...Ms. Kotobuki?",
"See? That's where you hold back.",
"Mm.",
"What, was that you begging just now? If you're gonna use sex appeal, put some effort into it!",
"Go kick butt this afternoon, too!",
"I'm... from the dorm run by Hoshikuzu Spica... Sensei?",
"Mmmph, the dorm mom is soooo waaarm!",
"Huh...?",
"Gatchispo!",
"Gatchispo!",
"As the dorm mother, I have to protect everyone from all her smooth talk and trickery.",
"Anyway, the first step is important in anything you do.",
"Yip!",
"Yip!",
"Munch, munch... She definitely said 'fight' just now.",
"Well, they entered every event they could, so let's let them sleep.",
"Eat enough crepes to become a competitive eater, okay?",
"Poor thing.",
"So cheer up, big sis! If you smile, it makes me happy, too!",
"Trust me, big sis!",
"I'd really love you to come!",
"You loved your fave that much, after all. Of course I want you to come!",
"And from now on, I hope you'll eat at our cafe, too!",
"To openly say you might get a partner someday... How sincere! She's practically a saint...",
"Were you watching? I did it!",
"Ugh!",
"Miu-chaaaaaan!",
"Now look! This is who I am: Miu Kinugawa!",
"Wha—?!",
"Oh!",
"Ehehehe, tomorrow we're going out, just the two of us!",
"'The pheromone perfume everyone's talking about! Attracts men like a magnet.'",
"I see. Well, that was pretty cool, after all.",
"Right?~",
"Yes! No problem at all!",
"Especially around the chest.",
"I can't help thinking, 'In this heat?' But maybe girls would say, 'That's exactly why, actually?'",
"Oh, sorry... what is it?",
"There, there... you'll feel better, you'll feel better...",
"When I count to ten, you'll feel absolutely wonderful...",
"When I count to ten, Mommy will feel sooo much better, okay?",
"Zeeero!",
"Aw... the countdown's over.",
"As if!",
"Ah... I'm starting to feel dizzy.",
"Oh...?",
"You didn't have to go out of your way to do that!",
"Mmm...",
"Why'd you run all the way here?",
"And the real identity of the influencer was... Miu-chan!",
"Today's the perfect time, right?",
"Keep it up, and please promote it on the stream, too!",
"A collab with Mommy!",
"—!",
"Yeah...",
"There was a note in incredibly elegant handwriting that said, 'I sincerely apologize.'",
"F-byaah?!",
"Well, she seems to be having fun, so I guess it's fine.",
"Oh, looks like everyone's here.",
"I'm okay.",
"I'll be right there.",
"After exchanging the bare minimum of messages you'd expect from siblings, I left my room...",
"Thanks. You're always cheering me up, Suzuka.",
"I'm okay now. I can manage on my own.",
"I want you to do what you want to do, big brother.",
"'Don't spend all your time worrying about me. Take care of yourself, too,' she said.",
"'Being able to provide children and students with delicious, balanced meals.'",
"But why is Ms. Omi here?",
"Ms. Ayakooo!",
"I see...",
"All right. Then, if you'll excuse me—",
"Oh...",
"Ah, um, uh...",
"Have mercy on us!",
"Have mercy on us!",
"Spare us some scraps!",
"Spare us some scraps!",
"Oooh...",
"And with that, Ms. Kotobuki left the public bath—",
"After that?",
"Oh, it's you, Ms. Kotobuki. You startled me...",
"Morning. I've been waiting for you, Ms. Kotobuki.",
"So, what do you think? The pool on our next day off?",
"Y-yeah...",
"Oh, a work message.",
"Come pick me up.",
"Same place as last time.",
"...I see.",
"Ehehehe~♪",
"What do you mean by 'like this'?",
"Okaaay!",
"Huh?",
"Th-thank you very much.",
"Eheheh...♪",
"Honestly, she's such a hopelessly clingy girl. ...Which I absolutely love.",
"I thought maybe you didn't like your living situation.",
"You're finally getting to talk with your parents after so long.",
"Tug, tug.",
"One more time—",
"Myaaaaaaaaaaaaaaaaa!!",
"You were spacing out. Are you finally getting tired?",
"Grab!",
"They're completely different, and yet both are unmistakably Ms. Kotobuki.",
"What are you doing? You're supposed to be in bed!",
"Wow...",
"I'm cooling it now, so I'll bring it to you later.",
"O-oh, right.",
"She grabbed me?!",
"Oh, Ms. Kotobuki. What's up?",
"Yep, yep, coming right up!",
"Hah... hah...",
"Then...",
"There's a word 'smitten,' but for her, 'all melty' feels more accurate.",
"Hmph.",
"So, Tamachan, give me your hand.",
"I'm okay.",
"But I like this hand.",
"Mmm...",
"Tamachan! Tamachan!",
"Seeing everyone being even noisier than usual, Tama-chan lets out a little sigh.",
"There, there. Good girl.",
"So what she confessed just now was my responsibility—",
"Me too!",
"Yay!",
"Oh, you always do that...",
"Seriously.",
"Zip!",
"Zip!",
"Tremble, tremble.",
"(Aww, she's so cute...)",
"Oh, did you get an idea?",
"Anything is fine, but...",
"I think Tamachan has gotten much better at being affectionate than she used to be.",
"Huh? H-hey, Suzuka?!",
"...Huh?",
"If Suzuka hadn't been born as my little sister, I think I'd have lost to harsh reality and gone through life without any motivation.",
"Well, let's just say it was out of love...",
"I'm asking how I can keep myself in check so my little sister won't be disappointed in me.",
"I'm home!",
"Mm... *kiss*...",
"'Life with My Little Sister' — disc edition in a tall case!",
"Again?",
"The boxed edition of 'Life with My Little Sister'...!!",
"I see.",
"Mmm...",
"Huh?",
"Got it...",
"...Yeah, you're right.",
"I'm home!",
"I've never had a pet before, after all.",
"Nyaaa.",
"Nyaa.",
"Nyaa.",
"Huh?!",
"Huh?!",
"Nyaa.",
"Nyaa?",
"Nnyaah!",
"Nnyaah!",
"Nyaah!",
"Nnyaah!",
"Nyaf.",
"Nyaow...",
"See? She's saying she's fine.",
"I see.",
"Oh, right. It's not just the two of us, is it?",
"...Suzuka.",
"Nyaaa~",
"Nnyaa~",
"Munch, munch...",
"'Well?!' she asks, staring at me with an anxious, earnest look.",
"Hello!",
"Hello.",
"I bent down and casually reached to put my hand on the kitchen counter—",
"The Thousand Island Nozomi... p-please, help yourself!",
"I'm ashamed of myself...",
"Come on, you told me about it on the rooftop that day, remember?",
"Huh...?",
"Smiling at her earnestness, I check the rest of the messages.",
"Well then. See you at work later today~",
"I'm looking forward to seeing you~",
"Oh, really...? I had no idea.",
"Looking forward to seeing you~",
"Good luck studying! My boyfriend can do it, I'm sure~",
"Yeah, I heard all about how you two met and everything~",
"Hmm~ Maybe this outfit instead.",
"Maybe things could develop 'like that,' too, right?",
"Nyaha, it's warm~",
"Then let's move on to today's main event.",
"Hehe, so that's what you were thinking while you watched... Cute~",
"But honestly... Nozomi when she's getting carried away is cute, too.",
"What was that?! That was way too much!!",
"Ahh, I love him, love him, love him!",
"I've gotta make him fall for me all over again on the big day!",
"Hm? Nozomi, did you say something?",
"Yes! Make sure you think about me a lot!",
"...Mm!",
"[Incoherent flustered noises]?!",
"...A plan?",
"You've really perked up.",
"No, it's more like... she won't let me sleep...",
"Katsudon.",
"Wow, thanks, Suzuka-chan!",
"Because I'm his girlfriend!",
"That's right.",
"I'm heading out first!",
"I send an 'OK' sticker, then wait while listening to the drama.",
"Yeah, it really is something to celebrate~",
"All right! I'm going to be happy!",
"Thump!",
"'I need to make it easy for her to express whatever she's feeling, then accept those feelings properly.'",
"Nfuh!",
"Mom...",
"What if I messed it up? What then?",
"So cuuute~",
"...Yes. I promise.",
"Mmmmmm, Mikan-chaaaaaan! Mommy's hoooome!",
"Mm. I love you, Tetsuya.",
"Mm. I love you, Daddy.",
"Could you idiots read the room for once?!",
"But more than that, I'm worried about your health, Ms. Ayako!",
"I don't want to hear someone badmouthing the person I love.",
"Yes?",
"But when I spend time with you, Ms. Ayako—",
"Ms. Ayako, I'll ask you one more time.",
"...Because it's you, Ms. Ayako. That's why it's okay.",
"...!",
"...Ms. Ayako.",
"They were showing something called 'Gatekeepers of HELL: THE MOVIE'.",
"What is it~?",
"—Ms. Ayako.",
"...Ms. Ayako.",
"So I can proudly declare that the protagonist (surname) protagonist (given name) is my boyfriend.",
"...Huh?",
"Ghh...!",
"You're saying that now?! You're saying that NOW?!",
"H-hey?!",
"Don't do stuff like that so much!",
"—Ms. Okai.",
"W-wait...?!",
"I'll think about it.",
"Tch...!",
"...?!",
"Hm...? What's wrong, Tanpopo?",
"...Huh?",
"Uh...? An inn?",
"Hm...? What's wrong, Tanpopo?",
"What's up? Why'd she suddenly stop—",
"I don't even need to ask. I know she's waiting for that girl.",
]
def main():
    args = parse_args()
    src = Path(args.input)
    out = Path(args.output)
    if not src.is_file():
        print(f"ERROR: input file not found: {src}", file=sys.stderr)
        return 2

    with src.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        fields = reader.fieldnames
        if not fields or "english_draft" not in fields or "status" not in fields:
            print("ERROR: input must be a review TSV with english_draft and status columns", file=sys.stderr)
            return 2
        rows = list(reader)

    blanks = [r for r in rows if not (r.get("english_draft") or "").strip()]
    if len(blanks) != len(translations):
        print(
            f"ERROR: expected {len(translations)} blank rows for this Pass 4 translation set; "
            f"found {len(blanks)}. No output written.",
            file=sys.stderr,
        )
        return 2

    for row, english in zip(blanks, translations):
        row["english_draft"] = english
        row["status"] = "TRANSLATED (MANUAL PASS 4)"

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    remaining = sum(not (r.get("english_draft") or "").strip() for r in rows)
    print(f"Filled {len(blanks)} blank row(s); {remaining} blank row(s) remain.")
    print(f"Output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
