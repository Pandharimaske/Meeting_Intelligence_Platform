

### **The Core Research Paper**

**Title:** *"AMMGS: An AI Driven Framework for Automatic Meeting Minutes Generation"* (2025)

* **Why this paper?** Unlike older papers that focus on just ASR or just summarization, this framework proposes the exact pipeline you are building: `Audio → Diarization → ASR → Abstractive Summarization → Key Point Extraction`.
* **Alternative/Support Paper:** *"AutoMeet: A Proof-of-Concept Study of GenAI to Automate Meetings"* (arXiv, 2025) – valuable because it discusses the *user experience* and *latency* issues of deploying this in a real engineering firm.

---

### **Implementation vs. Research Gaps**

Research papers operate in "ideal" conditions (clean audio, single speakers, offline processing). Your implementation (real-world app) faces "messy" reality.

Here is the breakdown of the **4 Major Gaps** you will face when moving from the paper to your code, and how to fix them.

#### **Gap 1: The "Who Said What" Drift (Week 1)**

* **The Paper Approach:** Most papers (like AMMGS) run ASR (Whisper) and Diarization (PyAnnotate) as parallel independent processes and then merge them by timestamp.
* **The Implementation Reality:** Timestamps *drift*. Whisper often hallucinates silence or merges short phrases. If you simply merge by timestamp, you will attribute Speaker A's sentence to Speaker B.
* **The Fix (Force Alignment):** Do not trust standard timestamp merging. You must implement **Word-Level Forced Alignment**.
* *Tool:* Use `whisperX` (which includes alignment) instead of vanilla `whisper`. It forces the text to align with the audio waveform phoneme-by-phoneme.



#### **Gap 2: The "Anaphora" Retrieval Failure (Week 2 & 3)**

* **The Paper Approach:** Papers use standard "Chunking" (breaking text into 500-character blocks) and embedding them for search.
* **The Implementation Reality:**
* *User Query:* "What was the decision on the budget?"
* *Actual Transcript Chunk:* "He said it's too high, so we rejected it."
* *The Gap:* The Vector DB cannot find this chunk because it doesn't contain the words "budget" or "decision" (it uses pronouns "he" and "it"). This is called the **Anaphora Problem**.


* **The Fix (Contextual Chunking):** You cannot just embed the chunk. You must prepend "Metadata Context" to the chunk before embedding.
* *Code Logic:* Embed `[Speaker: Alice, Topic: Q3 Budget] He said it's too high...` instead of just the raw text.



#### **Gap 3: Video Clipping Granularity (Week 3)**

* **The Paper Approach:** Papers like *CLIP-It!* perform "Video Summarization" by selecting keyframes based on visual changes.
* **The Implementation Reality:** Meeting videos (Zoom/Meet) are visually static (just talking heads). Visual change detection fails here. If you slice the video exactly at the text timestamps (e.g., 10:01 to 10:05), the audio will cut off abruptly mid-word or mid-breath.
* **The Fix (Audio Padding):** You need a "Smart Slicing" heuristic.
* *Logic:* If the relevant text segment is at `t_start` and `t_end`, your video clipper must slice `t_start - 2s` to `t_end + 2s`.



#### **Gap 4: Hallucinated Action Items (Week 2)**

* **The Paper Approach:** Papers evaluate summaries using **ROUGE scores** (word overlap with a human summary). They don't penalize "wrong attribution" heavily.
* **The Implementation Reality:** In your app, if the MoM says "Bob is responsible for deployment" but *Alice* actually said it, the system is useless. LLMs often confuse speakers in long contexts.
* **The Fix (Structured Injection):** Do not feed raw text to the LLM. Feed a structured, diarized script.
* *Prompt Engineering:* "You are an assistant. Below is a transcript. Every line starts with a SPEAKER_ID. You strictly attribute action items to the SPEAKER_ID found in the line."



---

### **Visualizing the Solution**

To help you structure Week 2 & 3 (the most complex parts), here is how the Retrieval Architecture should look to solve Gap #2 (Context).

**Next Step:**
Would you like me to generate the **`whisperX` implementation code** for Week 1 to solve the timestamp drift issue immediately?



### **Part 1: Research Paper List (2024-2025)**

I have selected papers that directly map to your specific 30-day modules.

#### **For Week 1 & 2 (Ingestion, Diarization, MoM)**

* **Primary Paper:** *“AMMGS: An AI Driven Framework for Automatic Meeting Minutes Generation”* (2025)
* **Focus:** Proposes an end-to-end pipeline: Audio  YAMNet (Speaker ID)  ASR  Abstractive Summarization.
* **Why it fits:** It validates your "Week 1" goal but introduces a "Pre-Diarization" step that your plan misses (see Gap 1).


* **Secondary Paper:** *“AutoMeet: A Proof-of-Concept Study of GenAI to Automate Meetings”* (arXiv, 2025)
* **Focus:** Evaluates the latency and accuracy trade-offs of using Large Language Models (LLMs) for extracting "Action Items" and "Decisions" from raw transcripts.



#### **For Week 3 (Video Retrieval & Clipping)**

* **Primary Paper:** *“Context-Aware Video Retrieval and Clipping Using Text Queries”* (2025)
* **Focus:** Discusses how to retrieve a specific video segment based on a text question (e.g., "Show me where they discussed the budget").
* **Why it fits:** It argues that simple keyword search fails for video. It proposes a "Joint Visual-Semantic Embedding" (mapping text vectors and video frame vectors in the same space).


* **Secondary Paper:** *“Weakly Supervised Video Moment Retrieval From Text Queries”*
* **Focus:** How to find start/end times for a query when you don't have perfect training data.



---

### **Part 2: The Gap Analysis (Research vs. Your Implementation)**

Research papers often assume "ideal" conditions. Your 30-day plan deals with "engineering" reality. Here are the 4 critical gaps you must bridge.

#### **Gap 1: The "Timestamp Drift" Problem (Week 1)**

* **The Theory (Papers):** Papers often assume ASR timestamps are perfect. They merge Speaker ID and Text simply by checking time overlaps.
* **Your Plan:** `ASR -> Store Timestamps`
* **The Reality:** Standard ASR (like Whisper) often "hallucinates" timestamps or drifts by 1-2 seconds on long files. If you just merge by time, you will attribute **Speaker A's** words to **Speaker B**.
* **The Fix:** You need **Forced Alignment**.
* *Implementation:* Do not trust the ASR's raw timestamps. Use a library like `whisperX` or `ctc-segmentation`  which forces the text to align phoneme-by-phoneme with the audio waveform.



#### **Gap 2: The "Anaphora" Retrieval Failure (Week 2)**

* **The Theory (Papers):** Papers evaluate retrieval on explicit queries (e.g., "Find the budget discussion").
* **Your Plan:** `Chunk Transcript -> Vector DB -> Search`
* **The Reality:** Users ask implicit questions: *"What did **he** say about **that**?"*
* If you chunk the text `He said it is too expensive`, the vector embedding has **zero** knowledge of who "he" is or what "it" refers to. Your search will fail.


* **The Fix:** **Contextual Chunking**.
* *Implementation:* Before embedding a chunk, strictly prepend the metadata: `[Speaker: Alice, Topic: Q3 Budget] "It is too expensive..."`.



#### **Gap 3: Video Clipping Granularity (Week 3)**

* **The Theory (Papers):** Video retrieval papers often return a "visual shot" (e.g., a camera angle change).
* **Your Plan:** `Search Text -> Get Timestamp -> Slice Video`
* **The Reality:** Meeting videos are often static (webcams). If you slice exactly at the text start/end time, you will cut off the user's breath or start mid-word (audio clipping), which feels "broken" to the user.
* **The Fix:** **Audio-Aware Padding**.
* *Implementation:* You must implement a heuristic: `Clip_Start = Text_Start - 1.5s`, `Clip_End = Text_End + 1.5s`. This "padding" captures the natural pause before/after speaking.



#### **Gap 4: Action Item Attribution (Week 2)**

* **The Theory (Papers):** Papers use **ROUGE scores** (word overlap) to grade summaries. They don't heavily penalize assigning a task to the wrong person.
* **Your Plan:** `Raw Transcript -> LLM -> MoM`
* **The Reality:** In a real product, assigning a task to the wrong person is a critical failure. LLMs are notoriously bad at tracking speakers in long contexts.
* **The Fix:** **Diarized Prompt Injection**.
* *Implementation:* Do not feed raw text. Feed a script format:
`SPEAKER_01: I will handle the database.`
`SPEAKER_02: Okay.`
* *Prompt:* "You are a secretary. Extract action items and explicitly link them to the `SPEAKER_ID` listed in the text."




### **Module 1: Ingestion, Transcription & Diarization (Week 1)**

*Papers in this category focus on converting raw audio/video into labeled text.*

#### **1. Paper: "Overlap-Adaptive Hybrid Speaker Diarization" (arXiv, 2025)**

* **What it proposes:** A hybrid model using `WavLM` (end-to-end segmentation) combined with traditional clustering to handle "overlapping speech" (when two people talk at once).
* **Why it fits:** It directly addresses the hardest part of meeting transcription: interruption handling.

#### **2. Paper: "AMMGS: An AI Driven Framework for Automatic Meeting Minutes Generation" (2025)**

* **What it proposes:** A sequential pipeline: `Audio`  `YAMNet` (Speaker ID)  `Whisper` (ASR)  `Text`.

#### **⚠️ The Implementation Gaps (Week 1)**

| Gap | The Reality vs. The Paper | The Fix |
| --- | --- | --- |
| **Timestamp Drift** | Papers assume ASR timestamps are perfect. In reality, `Whisper` timestamps often drift by 0.5–2s on long files (1hr+), causing you to assign Speaker A's text to Speaker B. | **Word-Level Forced Alignment:** Don't trust raw ASR timestamps. Use **`whisperX`** to force-align text to the audio waveform phoneme-by-phoneme. |
| **Speaker Hallucination** | Overlapping speech (interruptions) often results in ASR transcribing the louder person but assigning it to the wrong speaker ID from the diarization track. | **Clustering Check:** Implement a "Voting Logic." If the Diarization model says "Speaker A" but the Audio Classifier detects "Silence/Noise," discard the segment. |

---

### **Module 2: MoM & Action Item Extraction (Week 2)**

*Papers in this category focus on turning text into structured intelligence (Decisions, Tasks).*

#### **3. Paper: "Action-Item-Driven Summarization of Long Meeting Transcripts" (arXiv, 2024)**

* **What it proposes:** Instead of summarizing the whole text, it recursively extracts "Action Items" first, then generates the summary *around* those items.
* **Why it fits:** This matches your goal of generating structured Minutes of Meeting (MoM) rather than just a generic summary.

#### **4. Paper: "AutoMeet: A Proof-of-Concept Study of GenAI to Automate Meetings" (2025)**

* **What it proposes:** Evaluates using LLMs (like GPT-4) to parse transcripts for "Decision Points" and compares it against human notes.

#### **⚠️ The Implementation Gaps (Week 2)**

| Gap | The Reality vs. The Paper | The Fix |
| --- | --- | --- |
| **Attribution Failure** | Papers use **ROUGE scores** (word overlap) to grade success. They don't heavily penalize assigning a task to the wrong person. In your app, this is a critical bug. | **Structured Injection:** Do not feed raw text to the LLM. Feed a script format: `SPEAKER_01: I'll do it.` Explicitly prompt the LLM to *only* assign tasks to the Speaker ID in that line. |
| **Context Forgetting** | In long meetings (2 hrs+), "Recursive Summarization" often causes the LLM to forget the context from hour 1 (e.g., a constraint set early on). | **Refinement Prompting:** Don't just summarize chunks. Use a "Running Summary" approach where the summary of Chunk 1 is passed as context to Chunk 2. |

---

### **Module 3: Retrieval (RAG) & Video Clipping (Week 3)**

*Papers in this category focus on finding "that exact moment" a user asks for.*

#### **5. Paper: "MSRS: Evaluating Multi-Source Retrieval-Augmented Generation" (2025)**

* **What it proposes:** A benchmark for RAG specifically on *meeting transcripts* (MSRS-MEET), arguing that standard RAG fails because meeting queries require synthesizing information from multiple speakers.

#### **6. Paper: "Bridging Multimodal and Video Summarization" (ACL Anthology, 2025)**

* **What it proposes:** A unified taxonomy for retrieving video segments using text queries ("Text-to-Video Retrieval").

#### **⚠️ The Implementation Gaps (Week 3)**

| Gap | The Reality vs. The Paper | The Fix |
| --- | --- | --- |
| **The "Anaphora" Problem** | Papers test explicit queries ("Find the budget"). Users ask implicit queries ("What did **he** say about **that**?"). Vector DBs fail here because the chunk "He said it's bad" has no keywords. | **Contextual Chunking:** Before embedding a chunk, prepend metadata: `[Speaker: Alice, Topic: Budget] He said it's bad...`. This "injects" the keywords into the vector. |
| **Static Video Clipping** | Video papers use "Visual Change Detection" (scene cuts) to clip video. Meeting videos are static (talking heads). "Visual" clipping will give you 60 minutes of one clip. | **Audio-Aware Padding:** You must implement a heuristic: `Clip_Start = Text_Start - 1.5s`, `Clip_End = Text_End + 1.5s`. This prevents the audio from cutting off mid-word. |

### **Summary of Your Action Plan**

1. **For Week 1:** Ignore standard `Whisper`. Go straight to `whisperX` or `NVIDIA NeMo` to solve the **Timestamp Gap**.
2. **For Week 2:** Do not simply "chunk" text. Use **Speaker-Enriched Chunking** (Prepend Speaker ID to every chunk) to solve the **Attribution Gap**.
3. **For Week 3:** Do not rely on "Visual" scene detection. Build a simple **Time-Based Clipper** with +/- 1.5s padding to solve the **Clipping Gap**.