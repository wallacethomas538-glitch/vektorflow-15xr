# Meta Model API — key-day runbook

Prepared 2026-10-21 for the Meta Global AI Developer Hackathon
(VektorMind 2.0). The integration code is in `src/meta_model.py`, wired
into `main.py`. It is inert — honestly "not configured" — until the
environment variables below are set. No code change is needed on key day.

## What to set (Render → vektorflow-15xr backend → Environment)

| Variable | Value |
| --- | --- |
| `META_MODEL_API_KEY` | The Meta Model API key from the hackathon credits claim. |
| `META_MODEL_API_BASE` | API root URL from the claim instructions, with **no** trailing `/v1` (paths are appended by the code). |
| `META_MUSE_MODEL` | The Muse Spark chat model id, exactly as the API names it. |
| `META_IMAGE_MODEL` | The Muse Image model id, exactly as the API names it. |

Then redeploy (Wallace's manual step, as always).

## What happens when the variables land

- **Muse Spark chat:** `src/meta_model.py` bridges `META_*` into the
  pre-existing `LLM_GATEWAY_*` env (only where unset), so agent calls made
  with model `gateway/<META_MUSE_MODEL>` reach the Meta API through
  `llm_handler.call_gateway`. Policy authorization (kill switch, usage
  recording) applies because the route is `llm_gateway.agent_llm`.
  Programmatic entry point: `src.meta_model.meta_chat(agent, prompt)`.
- **Muse Image:** `POST /api/ads/generate-image` with `model="muse-image"`
  routes to `MetaImageClient` instead of the Pollinations AdSpecialist.
  Same response shape (`data[0].url`); a `b64_json` upstream reply is
  normalized to a data: URL server-side.
- **Dashboard:** the Ads Studio's Image Engine toggle reads
  `GET /api/meta/status` and unlocks the Muse Image option only when the
  backend reports the image side ready.

## Verify after setting the variables

1. `GET /api/meta/status` → `configured: true`, `chat.ready: true`,
   `image.ready: true`, `gateway_bridge: "bridged-to-meta"`.
2. Ads Studio → engine "MUSE IMAGE (META)" → generate one creative.
3. One `meta_chat` call → result `meta_served: true`.

## Caveats — read before the demo

- `llm_handler.call_llm` fails over to `openrouter/free` if a `gateway/`
  call errors. For demo honesty, check `meta_served` on Muse Spark
  results; `false` means the fallback answered, not Muse.
- `LLM_GATEWAY_PROVIDER` (default `openrouter`) is sent in the gateway
  payload. If the Meta API rejects the payload on first contact, this —
  and the `/v1/chat/completions` path in `call_gateway` — are the two
  spots to adjust to the API's published shape. Both are one-line changes.
- The status route exposes no secrets: only set/unset flags, the base
  URL, and model ids.
