# Fixtures

The claude-context lab reads code from local checkouts of two fixtures.
Neither of them is committed to this repo; both are cloned separately and
addressed by absolute path, so nothing about them touches this repository's
git history.

## The fixtures

### `gratibot` (public, JS / Node)

Repo: [`liatrio/gratibot`](https://github.com/liatrio/gratibot)

Small (195 files, 148 tracked `.js`), Slack-bot shape, established as the
shared "public" fixture across every lab in the round. Used as the
smoke-test fixture for Waves 1–5.

```bash
git clone https://github.com/liatrio/gratibot.git ~/liatrio/repos/gratibot
```

### `liatrio-knowledge` (private, TS / SQL / Gherkin / Docusaurus)

Repo: `liatrio-labs/liatrio-knowledge` (private; access via Liatrio SSO)

Bigger (5,370 tracked files: 1,739 `.ts`, 164 `.tsx`, 208 `.sql`, 176
`.feature`, 1,151 `.md`, 277 `.mdx`), mixed-language, real-world shape.
Used as the size-and-language-diversity fixture for Wave 6.

```bash
git clone git@github.com:liatrio-labs/liatrio-knowledge.git \
  ~/liatrio/repos/liatrio-knowledge
```

Because this fixture is private, **the lab runs it fully local** — no
Zilliz Cloud, no hosted OpenAI/Voyage/Gemini keys. That is a hard
constraint of the whole PoC's `setup.py`: `FORBIDDEN_ENV_VARS` in
`versions.env` refuses to proceed if any of them are set.

## Wiring a fixture into a run

`setup.py --install-fixture` **does not** copy or edit anything in the
fixture directory. It reads the fixture path from `--fixture` (or
`CLAUDE_CONTEXT_FIXTURE`), computes claude-context's per-path index
identity (MD5 of the absolute fixture path — the same collection-naming
scheme the tool itself uses), and writes that identity into a per-fixture
state file under `CLAUDE_CONTEXT_LAB_STATE`.

That means: two absolute paths that resolve to the same fixture (e.g.
`~/gratibot` and `/Users/you/gratibot`) will be seen as two different
codebases by claude-context, because the MD5 differs. **Use a single
canonical absolute path per fixture and stick to it for all waves.**

## Fixture provenance for reproducibility

For Waves 1–6 the lab pins fixtures to specific commits (recorded in the
per-fixture state file). If you re-clone a fixture on a new machine, run
`setup.py --check` — it prints the current fixture commit and refuses to
run further if it does not match the recorded pin.
