# Knowledge base sync

Pulls public help-center articles into Markdown and uploads only new or changed files to an OpenAI vector store. One run, then the process exits.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env   # set OPENAI_API_KEY or API_KEY
```

## Run

```bash
python main.py
docker build -t kb-sync-agent .
docker run --rm -e API_KEY=sk-... kb-sync-agent
```

`API_KEY` and `OPENAI_API_KEY` are the same setting. The container runs `main.py` once and exits 0.

## What the job does

1. Read articles from the Zendesk help-center API (at least 30) and save `<slug>.md`. Nav and scripts are dropped. Headings, links, and code stay. Each file starts with `Article URL:`.
2. Compare SHA-256 of the file and Zendesk `updated_at` with the last run. Counts printed: added, updated, skipped.
3. Upload the delta with the OpenAI vector-store file-batch API. Files already in the store with the same `content_hash` attribute are not sent again, including from a clean container.
4. Ask "How do I add a YouTube video?" with the file_search tool and the system prompt from the brief.

Chunking is static: 800 tokens, 100 overlap, set on each uploaded file. A short how-to fits in one chunk. The overlap keeps a step that lands on a boundary.

First successful upload: **35 files, 138 chunks**.

A later run on a machine that already has state prints added 0, updated 0, skipped 35. A fresh machine has no state file, so the same articles show up as added. The upload still skips them when the store already has the same content hash. The public run did that: added 35, embedded 0, 35 files left in the store.

## Daily job

GitHub Actions runs `python main.py` every day at 00:00 UTC.

Log from the first public run: https://github.com/ducnmm/kb-sync-agent/actions/runs/36230221409

## Sample answer

![OptiBot answer to "How do I add a YouTube video?"](docs/sanity-youtube.png)

The reply cites `https://support.optisigns.com/hc/en-us/articles/360051014713-How-to-Use-YouTube-with-OptiSigns`. The prompt asks for at most 5 bullets. This answer is 5 steps, with the name and URL nested under step 4.
