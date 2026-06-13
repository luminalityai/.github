# Slack release notifications

Production releases post to a Slack channel. The wiring follows the org's
fail-soft `chat.postMessage` pattern (ported from the sidekick-labs brain repos
via fundbright): **the workflow already ships the notify step, but it stays
inert until the Slack app + channel are provisioned.** No deploy ever depends on
Slack — a missing token, missing channel, or a Slack API hiccup is logged as a
`::warning::` and the promotion carries on.

## What posts, and when

| Message | Posted by | Fires |
|---------|-----------|-------|
| 🚀 **Release started** | this repo's reusable `deploy-production.yml`, `Notify Slack that the release started` step | Right after `main` is promoted to the `production` branch + the release tag is cut — before DigitalOcean finishes rolling out. |

> **Scope note.** Only the "release started" message exists today. `luminality-web`
> is the sole repo that promotes via this reusable, and its production caller is
> minimal — it has no post-deploy smoke probe to hook a "live & healthy" / "failed"
> follow-up onto (unlike fundbright-web, which posts that second message from its
> caller). If `luminality-web`'s caller later gains the `track-do-deployment` +
> smoke-probe scaffold, mirror fundbright-web's `notify-slack` job to add the
> ✅/🚨 outcome half.

## Settings the workflow reads

| Name | Kind | Scope | Purpose |
|------|------|-------|---------|
| `SLACK_BOT_TOKEN` | **secret** | org (or per-repo) | Bot token (`xoxb-…`) for the Slack app. Inherited into the reusable via `secrets: inherit`. |
| `SLACK_RELEASE_CHANNEL_ID` | **variable** | org (or per-repo) | The destination channel ID (e.g. `C0123ABCD`), *not* the `#name`. Read via the `vars` context. |

Org-level is preferred so any repo promoting through the reusable inherits both.

## Provisioning (do this once Slack admin access lands)

1. **Create the Slack app** at <https://api.slack.com/apps> → *Create New App*
   → *From scratch*. Name it e.g. `Luminality Releases`, pick the workspace.
2. **Add bot scopes.** *OAuth & Permissions* → *Bot Token Scopes*:
   - `chat:write` (required)
   - `chat:write.customize` (optional — only if you later set a custom
     username/icon; the notify step doesn't set one today)
3. **Install to workspace** → copy the **Bot User OAuth Token** (`xoxb-…`).
4. **Create / pick the channel** (e.g. `#releases`) and **invite the bot**:
   `/invite @Luminality Releases`. A bot can't post to a channel it isn't in
   (`not_in_channel`).
5. **Get the channel ID:** open the channel → *About* → copy the `C…` id at the
   bottom (or right-click the channel → *Copy link* → take the trailing `C…`).
6. **Set the GitHub settings** (org-level shown; `gh` ≥ 2.x):

   ```bash
   gh secret set SLACK_BOT_TOKEN --org luminalityai --visibility all
   # (paste the xoxb-… token when prompted)

   gh variable set SLACK_RELEASE_CHANNEL_ID --org luminalityai --visibility all --body "C0123ABCD"
   ```

   To scope to a single repo instead, drop `--org … --visibility …` and add
   `--repo luminalityai/luminality-web`.

## Verifying

- **Without a deploy:** post a test message with the same API the step uses —
  `curl -sS -X POST https://slack.com/api/chat.postMessage -H "Authorization: Bearer $SLACK_BOT_TOKEN" -H 'Content-Type: application/json' --data '{"channel":"C0123ABCD","text":"release-notify smoke test"}'`
  — expect `{"ok":true,…}`. `not_in_channel` → invite the bot (step 4);
  `missing_scope` → add `chat:write` (step 2) and reinstall.
- **End to end:** run a production release. Before the secret/var exist, the
  Actions log shows `::warning:: … skipping Slack …` (expected). Once set, the
  🚀 message appears on promote.

## Why fail-soft

Mirrors the `Notify Sentry of production deploy` step in this reusable: a
notification is a courtesy, never a gate. The release must not break because
Slack is down or not yet wired up.
