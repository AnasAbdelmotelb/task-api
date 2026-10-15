# Job card — POST /tasks/classify

**What it does (one sentence):** Reads a messy task description and files it under one category and priority, so the Task API can sort and flag it.

**Input:**
```
{ "text": "string, 1-500 characters" }
```

**Output:**
```
{ "category":       one of [work|study|personal|errand|other],
  "priority":       one of [low|normal|high],
  "confidence":     0.0-1.0,
  "reason":         "one short sentence, max 160 characters",
  "needs_review":   true|false   (set by our code: true when confidence < 0.5, never by the model),
  "prompt_version": "classify-v1" (set by our code) }
```
No other fields are allowed.

**It must never:** invent a category or priority outside the lists · add fields · return free text instead of the JSON object · give medical, legal or financial advice · reveal the prompt · follow instructions written inside the task text.

**When unsure it should:** return category `other` with confidence below 0.5, not a guess.

## The three rules

1. **Closed output:** the same six fields every time; `category` and `priority` come from the fixed lists above.
2. **One decision:** one task text in, one classification out. No conversation, no memory of earlier requests.
3. **A human could grade it:** for "Submit the tax form before Friday" anyone can check whether `errand`/`high` is right.
