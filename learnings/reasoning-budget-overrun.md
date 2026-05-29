# Reasoning-budget overrun on local Gemma — why structured calls silently failed

Discovered: 2026-05-29 (while prototyping the mechanic council in `mtg-mech-lab`).

## TL;DR

`vlad-gemma4-26b-dynamic` is a **reasoning model**. llama-server parses its
chain-of-thought into a separate `reasoning_content` field, and **llmfacade
drops that field** (its `_parse_response` reads only `message.content`). On a
heavy call the CoT can run 7k–8k+ tokens *before* the answer; if `max_tokens`
isn't big enough for **reasoning + answer**, generation hits the cap mid-thought
and the answer is never emitted — `finish_reason=length` with empty
`content`/`tool_calls`. From our side that looked like "the model produced
nothing" (and was misdiagnosed as a repetition loop).

It is **not** a token-repetition loop and **not** fixable with `repeat_penalty`
(verified: identical truncation at 1.1 / 1.15 / 1.20). The reasoning is genuine,
high-quality deliberation — just long, and unbudgeted.

## How it presented

- The mechanic-council **synth** call (re-emit whole mechanic + consensus prose,
  fed 3 full reviews) hit `max_tokens` every time with empty output. Bumping
  3072 → 8192 didn't help.
- Free-text replay of the *same* prompt sometimes succeeded (`finish=stop`,
  clean answer) and sometimes didn't — pure run-to-run variance in CoT length
  straddling the cap.

## How we confirmed it

Hit llama-server's HTTP endpoint directly (bypassing llmfacade) and dumped the
raw response body:

```
finish_reason: length   completion_tokens: 8192
message['content']:           len=0       ← empty
message['reasoning_content']: len=30370   ← the whole budget went here
```

Re-running at `max_tokens=24576`: `finish=stop`, `completion_tokens=8282`,
**complete** well-formed answer (`content` 2,761 chars, `reasoning_content`
28,514 chars). So the 8192 cap was failing by ~90 tokens. Note the server
reports only the *combined* `completion_tokens` (no `reasoning_tokens`
breakdown), so the thinking/answer token split is char-estimated: ~7,550
reasoning + ~730 answer. The 8192-cap run is the exception — its `content` was
empty, so essentially all 8,192 tokens were reasoning (measured, not estimated).

## It already bit the main app — invisibly

Scanning historical transcripts (`sets (new)/transformers/`, `backend/logs/`):

- **3× `generate_card`** in the Transformers run hit the 4096 card-gen cap with
  **zero output** (reasoning overran the budget; no card emitted). Each raised
  `OutputTruncatedError`, which `card_generator` caught and **silently retried**
  in a fresh convo — so it surfaced as extra latency, not a visible failure.
- Pervasive hidden reasoning: many calls with `completion_tokens` 10–18× the
  parsed output (e.g. `generate_card` burning 4,997 tokens for a 275-token card;
  `submit_review` 7,052 → 757). All of that CoT was generated, billed, and
  dropped.

Three layers conspired to hide it: the model reasons invisibly → llmfacade
discards `reasoning_content` → the retry path papers over the truncations.

## Fixes

1. **Done — centralized, raised budgets.** `mtgai/generation/token_budgets.py`
   (`STANDARD=8192`, `BATCH=12288`, `HEAVY=16384`, ceiling 16384). All structured
   call sites reference these. Sized for reasoning + answer + headroom. **Do not
   set to the model max:** it removes the circuit breaker (a true loop would run
   to full context — minutes locally, real cost on the API), and locally
   `check_pre_call` reserves `max_tokens` against the context window so
   `max_tokens == ctx` raises `ContextOverflowError`.

2. **Recommended — surface `reasoning_content`.** Patch llmfacade's llamacpp
   provider (`_parse_response` + the streaming `_chunk_to_events`) to expose
   `reasoning_content` (e.g. as `Response.thinking`). Makes the CoT visible and
   lets the truncation guard distinguish "still thinking → raise budget" from
   real truncation.

3. **Recommended — escalate-on-overrun.** When a call truncates mid-reasoning,
   retry at a higher budget instead of re-rolling at the same one (only pay the
   big budget when actually needed). Pairs with #2.

4. **Optional — suppress reasoning** for calls that don't need it
   (`chat_template_kwargs:{enable_thinking:false}` / `--reasoning-budget 0`, if
   the template honors it). Faster + cheaper, at some quality cost on the
   reasoning-heavy steps (council, gates).

## Note on configuration

Nobody "turned reasoning on." The app sends no reasoning control at any layer
(`models.toml`, `_llamacpp_new_model`, per-call `convo_kwargs`), and llmfacade
sends none either (no `--jinja`/`--reasoning-format` launch flag, no reasoning
field in the request body). It's a default of the model + the llama-server build
at `C:\Tools\llama.cpp`. It was simply invisible until a call reasoned past its
budget.
