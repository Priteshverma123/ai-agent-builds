# Video hooks · 05 RAG from Scratch

- **hook:** Ask your docs anything. When they don't know, it says so.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  Indexed 4 documents -> 12 chunks -> 118 distinct terms
  | question : Do you ship to Canada, and how long does international delivery |
  | retrieve : [1] 0.52 ######...... shipping.md#1                             |
  |            [2] 0.34 ####........ shipping.md#2                             |
  | answer   : International delivery takes 7 to 12 business days and costs a  |
  |            flat $15. [1] We ship to Canada and the United Kingdom. [1]     |
  | question : What is your CEO's favourite film?                              |
  | retrieve : no chunk above the similarity floor -> skip the LLM entirely    |
  | answer   : I don't know -- nothing in the documents matches that question. |
  ```
- **diagram:** `Docs → Chunks` → `TF-IDF vectors` → `Top-k retrieval` → `LLM + numbered sources` → `Cited answer`
- **real_world:** A coffee shop's support bot that answers refund and shipping questions from its own help center, with links to the exact paragraph.
- **try_it:** Drop your own `.md` notes in a folder and run `python demo.py --docs that_folder "your question"`.
- **flow_steps:**
  1. `index.py` loads every `.md` file in `examples/docs/` and `chunking.py` cuts them into small, overlapping, citable chunks like `shipping.md#1`.
  2. `embed.py` turns each chunk into a TF-IDF vector: rare, meaningful words weigh more than common ones.
  3. For your question, `VectorIndex.search()` ranks chunks by cosine similarity and keeps the top few above a score floor (all set in `config.py`).
  4. `answer.py` puts those chunks in the prompt as numbered sources; if nothing matched, it says "I don't know" without calling the model at all.
  5. The model in `llm.py` answers with `[n]` citations, `answer.py` checks every citation is real, and `cli.py` prints the scores, answer and quoted sources.
