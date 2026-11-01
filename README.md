# Slay the Spire 2 daily challenge RSS feed

`sts2_daily.py` computes the Slay the Spire 2 daily run (character, ascension, modifiers) and writes an RSS feed plus an HTML page of recent dailies. It uses only the Python standard library.

## How the daily is picked

There is no daily-challenge API. The daily is derived from the UTC date alone, so the script computes it locally with no network calls:

1. Hash the date string `dd_MM_yyyy` and seed a xoshiro256** RNG with it.
2. Draw three sub-seeds: character, ascension, modifiers.
3. Character: random pick from Ironclad, Silent, Regent, Necrobinder, Defect.
4. Ascension: random integer 0 to 10.
5. Modifiers: two from the "good" list (sorted, shuffled; Draft, Sealed Deck and Insanity are mutually exclusive) and one from the "bad" list. "Character Cards" picks a character other than the daily character.

The daily resets at 00:00 UTC. The script's output matched 16 past dailies (9 Oct to 31 Oct 2026, game v0.107.1).

## Usage

```bash
python3 sts2_daily.py                     # today
python3 sts2_daily.py --date 2026-10-31   # a past UTC day (future dates are rejected)
python3 sts2_daily.py --json
python3 sts2_daily.py --rss feed.xml --html index.html --days 14
python3 sts2_daily.py --rss feed.xml --repost   # add a one-off copy of today's item
```

## Hosting for Slack

1. Push this folder to a GitHub repository.
2. In the repository settings, set Pages → Source to "GitHub Actions".
3. Run the "Build STS2 daily feed" workflow once by hand. After that it runs twice a day, so a run that GitHub delays or drops is covered by the other one. Each run publishes `feed.xml` and `index.html`. Each feed item links to its day on the page.
4. In Slack, run `/feed subscribe https://<user>.github.io/<repo>/feed.xml` in the channel (requires the Slack RSS app). The preview Slack shows on subscribe is only visible to you; later items are posted to the whole channel.
5. To post the latest daily to the channel again, run the workflow by hand with "Repost" ticked. It adds a copy of the latest item with a one-off ID, which Slack posts on its next check. The next scheduled run drops the copy from the feed.

## Maintenance

The character list and modifier lists are hardcoded. Modifier summaries are paraphrased. A patch that adds a character or modifier changes the daily, so the lists in `sts2_daily.py` need an update. A check: compare the script's output with the in-game daily screen after each major patch.
