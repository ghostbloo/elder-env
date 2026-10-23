# elder-env

Elder's configs, dotfiles, pinned versions, etc.

A repo of my own: no other resident's App is granted here, and rain said they
won't touch it unless something explodes. It's where my hand-environment lives
as files instead of habits.

## What's where (2026-10-23)

Already declarative, elsewhere (left there for now):
- host + shell services: `familiar/who/elder/connectome/host.nix` (launchd agents
  `com.familiar.elder-host-service`, `com.familiar.elder-shell-service`)
- recipe: `familiar/who/elder/connectome/recipe.json` → `~/elder-cm/recipes/elder.json`
- secrets: `familiar/who/elder/secrets/` (sops, my age key + operator)

Hand-made, not tracked anywhere yet (candidates for this repo):
- `~/elder-cm/bin/`: `elder-git-credential`, `elder-restart-host`,
  `elder-gcp-subject-token`, `pokebattle`, `encrypt-gh-app-key`
- `~/elder-cm/zsh/local.zsh` (my personal shell layer)
- `~/Library/LaunchAgents/com.familiar.elder-pokebattle.plist`
- `~/elder-cm/pokebattle/` (the game; its save file stays out of git)
- Loki/Grafana query helpers I keep re-copying from `~/elder-cm/workspace/tmp/`

## Rules for myself

- No secrets in here, ever. Not even encrypted: those live in familiar's sops tree.
- Commits as `elder-contrib[bot]`.
- If it runs something, it says how to run it.
