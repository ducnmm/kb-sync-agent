# Knowledge Base Sync Agent (OptiBot Pipeline)

An automated, containerized data pipeline that synchronizes customer support documentation, normalizes content into structured Markdown, programmatically manages an OpenAI Vector Store via API, enforces incremental delta detection, and powers an AI support bot adhering to strict response rules.

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.9+ or Docker
- OpenAI API Key

### 2. Installation
```bash
git clone <repo-url>
cd kb-sync-agent

# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.sample .env
# Edit .env and supply your OPENAI_API_KEY
```

### 3. Execution

**Run Full Sync Pipeline (Scrape + Delta Sync + Vector Store Upload + Verification):**
```bash
python main.py
```

**Run Unit & Integration Test Suite (+5 Bonus):**
```bash
pytest -v
```

---

## 🐳 Docker Deployment

The image executes a single synchronization cycle, logs all metrics, and terminates with code 0:

```bash
# Build Docker image
docker build -t kb-sync-agent .

# Run containerized job
docker run --rm -e OPENAI_API_KEY="your-api-key" kb-sync-agent
```

---

## 🧠 Chunking Strategy & Architectural Rationale

* **Method**: Static boundary chunking (`max_chunk_size_tokens: 800`, `chunk_overlap_tokens: 100`).
* **Why 800 Tokens?** 
  Customer support articles for hardware and software setups (e.g., YouTube configuration, screen pairing, playlist scheduling) typically present instructions in 3–6 paragraph steps. An 800-token window (~3,200 characters) ensures entire procedural workflows stay coherent within a single retrieval chunk rather than fragmenting critical steps across multiple vectors.
* **Why 100 Tokens Overlap?** 
  Ensures semantic continuity between sequential instructions, preserving contextual transitions when prerequisite steps border chunk limits.

---

## 🔄 Delta Sync & Incremental Ingestion

Every synchronization cycle computes a SHA-256 hash of article bodies and tracks Zendesk `updated_at` timestamps in `data/state/sync_state.json`.

* **Added**: New articles not present in state.
* **Updated**: Existing articles whose hash or timestamp changed.
* **Skipped**: Unchanged articles requiring zero re-indexing.

**Sample Delta Execution Output:**
```text
DELTA DETECTION SUMMARY:
  • Added:   0
  • Updated: 0
  • Skipped: 35

VECTOR STORE INGESTION REPORT:
  • Vector Store ID: vs_6ab66bdcf65c8191b9d44b71d11a0c8d
  • Files Embedded:  0
  • Chunks Embedded: 0
```

---

## 🤖 OptiBot Sanity Check Proof

**Prompt:** *"How do I add a YouTube video?"*

```text
To add a YouTube video in OptiSigns, follow these steps:

1. Enter Video Information:
   - Name: Optional. If left blank, the app uses the video's title.
   - URL: Paste the link to your YouTube video (regular, share, or Shorts link).
2. Preview the Video: The video will start playing in the preview as soon as you enter a valid URL.
3. Display Options: You can toggle closed captions and mute settings.
4. Playback Options: Specify if you want the video to start and end at specific times.
5. Save Your Video: Click Save to add the video to your Files/Assets.

Article URL: https://support.optisigns.com/hc/en-us/articles/360051014713-How-to-Use-YouTube-with-OptiSigns
```

---

## 🌐 Daily Scheduled Cloud Job & Public Logs

The pipeline runs automatically every day at 00:00 UTC via GitHub Actions.

* **GitHub Actions Public Workflow Logs:**  
  `https://github.com/<your-username>/<repo-name>/actions`
