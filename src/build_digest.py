#!/usr/bin/env python3
"""
Create a 2–3 k-token ‘values digest’ from a book (PDF or TXT).

Usage
-----
python build_digest.py \
       --book path/to/book.pdf \
       --out  resources/persona_digest.txt \
       --model gpt-4o-mini
"""
import argparse, json, os, pathlib, re, textwrap
import openai, tiktoken
from collections import OrderedDict
from dotenv import load_dotenv, find_dotenv

# ── 0. ENV & constants ─────────────────────────────────────────
load_dotenv(find_dotenv())   # finds .env anywhere above this file :contentReference[oaicite:2]{index=2}
openai.api_key = os.getenv("OPENAI_API_KEY")

TOKENIZER     = tiktoken.encoding_for_model("gpt-4o-mini")
CHUNK_TOKENS  = 6000         # prompt stays < 8 k even after instructions

PROMPT_TMPL = textwrap.dedent("""
    You are an expert literary analyst.
    Read the excerpt below and *extend* (do NOT overwrite) a cumulative digest
    with three sections:
      1. Core moral attitudes
      2. Typical language & tone
      3. Behaviour lenses (6–10 broad categories)
    Respond in JSON:
    {
      "core_attitudes":   [ "…", … ],
      "tone_features":    [ "…", … ],
      "behaviour_lenses": { "Lens name": "One-line definition", … }
    }
    ### EXCERPT ###
    {chunk}
    ### END ###
""").strip()

# ── 1. Helpers ─────────────────────────────────────────────────
def read_book(path: pathlib.Path) -> str:
    """Return full text as a single string (handles .pdf or .txt)."""
    if path.suffix.lower() == ".pdf":
        from PyPDF2 import PdfReader  # lazily import
        reader = PdfReader(str(path))
        pages  = [p.extract_text() or "" for p in reader.pages]  # text-based PDFs only :contentReference[oaicite:1]{index=1}
        return "\n".join(pages)
    return path.read_text(encoding="utf-8")

def chunk_text(text: str, max_tokens: int):
    words, buf, count = text.split(), [], 0
    for w in words:
        t = len(TOKENIZER.encode(w + " "))
        if count + t > max_tokens and buf:
            yield " ".join(buf); buf, count = [], 0
        buf.append(w); count += t
    if buf: yield " ".join(buf)

def merge_json(a: dict, b: dict) -> dict:
    m = {}
    m["core_attitudes"] = list(OrderedDict.fromkeys(a.get("core_attitudes", []) +
                                                    b.get("core_attitudes", [])))
    m["tone_features"]  = list(OrderedDict.fromkeys(a.get("tone_features", []) +
                                                    b.get("tone_features", [])))
    m["behaviour_lenses"] = {**a.get("behaviour_lenses", {}), **b.get("behaviour_lenses", {})}
    return m

# ── digest_chunk (fixed) ──────────────────────────────────────
def digest_chunk(chunk: str, seed: dict, model: str) -> dict:
    # 1. build the system prompt (we already escaped/replace the {chunk})
    sys_content = PROMPT_TMPL.replace("{chunk}", chunk)

    # 2. assemble the message list
    messages = [{"role": "system", "content": sys_content}]
    if seed:
        # feed the running digest back to the model so it appends, not repeats
        messages.insert(1, {
            "role": "assistant",
            "content": json.dumps(seed, ensure_ascii=False)
        })

    # 3. call the API
    resp = openai.chat.completions.create(
        model=model,
        messages=messages,          # ← use the right variable here
        response_format={"type": "json_object"},
        temperature=0
    )
    return json.loads(resp.choices[0].message.content)


# ── 2. Main ────────────────────────────────────────────────────
def main(book_path: str, out_path: str, model: str):
    full_text = read_book(pathlib.Path(book_path))
    digest    = {}
    for i, chunk in enumerate(chunk_text(full_text, CHUNK_TOKENS), 1):
        print(f"[chunk {i}] → {len(chunk)//1000} k chars")
        digest = merge_json(digest, digest_chunk(chunk, digest, model))

    # Light trimming → keep script output near the 2–3 k-token target
    digest["core_attitudes"]   = digest["core_attitudes"][:12]
    digest["tone_features"]    = digest["tone_features"][:12]
    digest["behaviour_lenses"] = dict(list(digest["behaviour_lenses"].items())[:10])

    out_file = pathlib.Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(digest, ensure_ascii=False, indent=2))
    tokens = len(TOKENIZER.encode(out_file.read_text()))
    print(f"✓ Saved {out_file}  (≈ {tokens} tokens)")

# ── 3. CLI ─────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--book", required=True, help="Book file (.pdf or .txt)")
    p.add_argument("--out",  required=True, help="Output digest path")
    p.add_argument("--model", default="gpt-4o-mini")
    args = p.parse_args()
    main(args.book, args.out, args.model)
