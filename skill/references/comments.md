# The comment section as a tactic

Read the comments of the deep-read posts (the outliers, ordinary posts and flops), top comments first, with replies
when your reader gives them. 50-100 a post is enough. Write `comments.csv` (`data-shape.md`), set
`account.json` `comments_read` (`replies_read` true or false), then run `comment_tactics.py <run>`.

## What the script counts (comments.json, MEASURED)

| Key | Counts |
|---|---|
| `creator_comment` | Posts where the creator wrote their own top-level comment; whether it came first and within 10 minutes (exact times only); pinned |
| `pinned` | Posts with a pinned comment, and whether the creator or the audience wrote it |
| `hearted` | Audience comments the creator hearted |
| `comment_a_word` | Captions (and creator comments) that ask for a word ("Comment GUIDE and I'll send it"), and posts where one word is 20%+ of the comments (`echo`) |
| `replies_by_creator` | The share of audience top-level comments the creator answered, and the median minutes to the answer (exact times only) |
| `follow_comments` | Comments of new followers ("just followed", "found you through…", "subscribed"), per post, with the comments |
| `questions`, `objections` | The audience's questions (a "?") and objections (doubt words), ranked by likes. Found by pattern: read them; many are jokes |
| `top_comments` | The three most liked top-level comments of each post |
| `times_exact` | How many comments have exact times. When the source says "2 days ago", nothing is measured in minutes |

"Unknown" is written as `null` with a note (for example: replies were not read, the creator's comments are not
marked). Do not turn an unknown into a zero.

## What you read and write

- **The creator's first comment:** what it does (a credit, a question to start the thread, a link, the word to
  comment). Quote it.
- **The ask:** a "comment a word" mechanic, and whether the audience follows it (the echo share).
- **Replies:** how often and how fast the creator answers, and to what: the first comments, questions, critics.
- **New followers:** what they say brought them. Their own words are the strongest SEEN evidence for "this post
  brought followers"; still never a count.
- **Questions and objections in the audience's own words:** they become the user's next posts. Quote them.

Write each tactic as a claim in `findings.json` `comment_tactics`: MEASURED with `from: "comments.json#<key>"` for a
count, SEEN with `posts` and `quote` for a comment. `validate.py` checks that each quote is really in a comment or
caption of the cited posts.
