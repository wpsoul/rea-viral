# Way in: one post

The user gives one link to a post or a video. The run answers, in the **Post report**: **why this one worked against
its own creator's usual**, and its mirror, what in it sits under that usual (the format's repeats that did not lift,
the words its creator's weaker posts share); its format's recipe; its words taken apart beside the creator's usual;
and whether the creator repeats the format and whether it lifts each time. Small and cheap: about 25 to 40 reads,
usually free.

The run folder is `rea-viral/post-<network>-<post_id>/`. It is an account folder (`account.json` and `posts.csv`: the
post plus its creator's recent posts) with `post.json` naming the post:

```json
{"schema": "rea-viral/post@1", "post_id": "abc123", "url": "https://www.youtube.com/shorts/abc123", "given_as": "the link the user pasted"}
```

## Steps

1. **No setup question** when the link is all you need: the network and the creator come from the link. Ask only for
   what the link does not say (a spend ceiling when a paid reader is the only way).
2. **Read the post and its creator's recent posts**: the latest 25 to 40, and the post itself when it is older. Its
   creator's usual needs **9 settled posts or more** from the 60 days before the post on (the post is compared with
   the median of the creator's other recent posts, 8 or more; older posts read are left out); say how many in the
   hand-over. On YouTube with `yt-dlp`:

   ```
   python3 SKILL_DIR/scripts/readers/ytdlp_reader.py posts <run> "https://www.youtube.com/@<handle>/shorts" --max 30
   ```

   If the post is not among them, read it too (one more row in `posts.csv`). Then `validate.py <run>`.
3. **Watch it** (the deep read, `deep-read.md`): `video_probe.py <run> <post_id> --fetch`, look at `first.jpg` and
   `shots.jpg`, fill `videos/<post_id>/notes.json`. Watch one or two of the creator's ordinary posts too, so "why it
   worked" is tested against posts where it did not.
4. **Mark its format**: in `formats.json`, one format holding the post and every other post of the creator with the
   same container (hook, structure, look, length), from the covers sheet (`covers_sheet.py <run> --sort ratio`) and
   what you watched. When the creator never repeats it, the format holds the post alone.
5. **The numbers**:

   ```
   python3 SKILL_DIR/scripts/post_probe.py <run>
   ```

   It writes `post_probe.json`: the post's ratio against its creator's usual (or its ratio so far when it is under 7
   days old, a floor; or views per follower when too few of the creator's posts were read, the weaker basis), its
   rank among the creator's posts, its words beside the creator's usual (what it opens with, its shape, its ask,
   against how often the creator does the same), whether the creator repeats the format and whether it is above the
   usual each time, and the recipe skeleton `formats/<id>.md` to fill from the deep read.
6. **Your reading**: `findings.json` with `headline` (why this one worked, in one or two sentences), `mechanisms`
   (each reason with its label: what you saw in the video is SEEN with the post id, the numbers are MEASURED from
   `post_probe.json#...`, the rest INFERRED with its basis), `writing` for its words, `did_not_work` and `not_read`.
   With one post a cause is never proven: "the post that worked has X, and the creator's posts without X sit at Y" is
   the most a claim can say.

   **What did not work** mirrors why it worked. The page lays out what was measured: the post itself when it sits
   under its creator's usual (`post_probe.json#post.ratio`), the format's repeats under the usual
   (`post_probe.json#repeats`), and the words this post has or lacks where the creator's posts with them do worse
   (`post_probe.json#words.flags.<id>`; under 6 posts on a side, a lead). `did_not_work` is your reading of it: for
   example, the repeat of the format that did not lift and what you saw in it (SEEN), never why from that one post.
7. **The hand-over**: `build_report.py <run>` writes the Post report (a short `report.html`, one file: the post, why
   it worked, what did not, its words beside the creator's usual, the repeats, the recipe, the ways to make it),
   `POST.md`, and the planner files (`report_record.json`; `brief.json`, the report's short view; `radar_rows.json`
   with the post's own format, keyed by the post itself, when its format is marked). Tell the user in three lines: how far it beat its creator's usual (and
   from how many posts), the one reason you can stand behind, and whether the creator repeats it (and whether the
   repeats lift). With a planner connector, save the report and the format there (SKILL.md, "Handing the report to a
   planner").

## The offer (one question, asked once)

When the report went to a planner, the message opens with what was saved:
"Saved to Pulse: the report (Reports) and 1 format (Format Radar)".

> Want me to: (a) make this format as a video with your own content (Basic, Standard: GreenLight Motion or
> HyperFrames, or Advanced); (b) draft posts with its hook for your account; (c) read @<creator>'s whole account, or
> (d) the whole niche around it?

(a) only when the recipe has beats from the watched video. (c) copies this folder to `rea-viral/<network>-<handle>/`
without `post.json` (a folder with `post.json` is always built as a post page) and goes on with `account-run.md`,
reading the rest of the window into it. (d) starts `niche.md` with this creator as a seed account.
