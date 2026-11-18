# Shared AI tools — installation inventory

Updated 2026-11-18 (Codex inventory, finished by Claude). `skill-installed` = active for both agents. `library` = downloaded at a pinned commit under `~/.openjarvis/shared-tools/library/` and indexed in the shared catalog; agents read a guide when a task needs it. Nothing downloaded was executed; no hooks, proxies, billing or accounts were enabled.

| Name | Category | State | Detail |
|---|---|---|---|
| [Ponytail](https://github.com/DietrichGebert/ponytail) | coding | existing-skill | Existing Codex skill and shared reviewed Claude plugin preserved. |
| [RTK](https://github.com/rtk-ai/rtk) | coding | runtime-installed | Local executable installed; see usage restrictions in the shared guide. |
| [Graphify](https://github.com/Graphify-Labs/graphify) | coding | runtime-installed | Local executable installed; see usage restrictions in the shared guide. |
| [OmniRoute](https://github.com/cheaper-inference/OmniRoute) | coding | not-integrated | Source identified; runtime integration not installed or verified. A separate proxy/memory system could overlap Jarvis; no automatic hook or proxy enabled. |
| [Caveman](https://github.com/JuliusBrussee/caveman) | coding | not-integrated | Source identified; runtime integration not installed or verified. |
| [Headroom](https://github.com/headroomlabs-ai/headroom) | coding | not-integrated | Source identified; runtime integration not installed or verified. A separate proxy/memory system could overlap Jarvis; no automatic hook or proxy enabled. |
| [Claudex](https://github.com/ed0ted/claudex) | coding | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Inference Optimisation](https://github.com/sybil-solutions/inference-optimisation-skill) | coding | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Superpowers](https://github.com/obra/superpowers) | coding | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Matt Pocock Skills](https://github.com/mattpocock/skills) | coding | library | Downloaded at pinned commit; 39 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [Everything Claude Code (ECC)](https://github.com/affaan-m/ECC) | coding | library | Downloaded at pinned commit; 1087 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [Karpathy Skills](https://github.com/multica-ai/andrej-karpathy-skills) | coding | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: LOW 0/100. |
| [Addy Osmani Agent Skills](https://github.com/addyosmani/agent-skills) | coding | library | Downloaded at pinned commit; 25 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [gstack](https://github.com/garrytan/gstack) | coding | library | Downloaded at pinned commit; 76 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [GSD](https://github.com/gsd-build/get-shit-done) | coding | library | Downloaded at pinned commit; 0 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD) | coding | library | Downloaded at pinned commit; 36 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [Claude Code Setup](https://github.com/anthropics/claude-plugins-official) | coding | library | Downloaded at pinned commit; 57 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| Claude Automation Recommender | coding | existing-skill | Existing Codex skill and shared reviewed Claude plugin preserved. |
| [Claude Mods](https://github.com/karanb192/awesome-claude-code-mods) | coding | source-identified | Closest match: index of 8,000+ Claude Code mods with permissions shown. Exact video source unknown. |
| TaskObserver | coding | unresolved | Still unresolved after searching GitHub; no confident match or substitute. |
| [Deep Project](https://github.com/piercelamb/deep-project) | coding | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: LOW 18/100. |
| [Deep Plan](https://github.com/piercelamb/deep-plan) | coding | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: LOW 18/100. |
| [Deep Implement](https://github.com/piercelamb/deep-implement) | coding | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: MEDIUM 40/100 (auto-runs commands; review before use). |
| Morph | coding | source-identified | Morph fast-apply is a hosted API (morphllm.com); no open repo. Not free-only safe. |
| [CodeBurn](https://github.com/getagentseal/codeburn) | coding | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [DevSwarm](https://github.com/devswarm-ai/devswarm) | coding | source-identified | Parallel multi-agent coding environment; separate app. |
| [OpenCode](https://github.com/anomalyco/opencode) | coding | source-identified | Open-source terminal coding agent; separate CLI install. |
| [Obsidian Skills](https://github.com/obsidianmd/obsidian-skills) | knowledge | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Claude Obsidian](https://github.com/AgriciDaniel/claude-obsidian) | knowledge | not-integrated | Source identified; runtime integration not installed or verified. A separate proxy/memory system could overlap Jarvis; no automatic hook or proxy enabled. |
| [Obsidian Second Brain](https://github.com/eugeniughelbur/obsidian-second-brain) | knowledge | not-integrated | Source identified; runtime integration not installed or verified. A separate proxy/memory system could overlap Jarvis; no automatic hook or proxy enabled. |
| [LLM Wiki SecondBrain](https://github.com/DimitrisLianos/LLM_Wiki_SecondBrain) | knowledge | not-integrated | Source identified; runtime integration not installed or verified. A separate proxy/memory system could overlap Jarvis; no automatic hook or proxy enabled. |
| [Claude Mem](https://github.com/thedotmack/claude-mem) | knowledge | not-integrated | Source identified; runtime integration not installed or verified. A separate proxy/memory system could overlap Jarvis; no automatic hook or proxy enabled. |
| [Agent Reach](https://github.com/Panniantong/Agent-Reach) | knowledge | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: LOW 0/100. |
| [Understand Anything](https://github.com/Egonex-AI/Understand-Anything) | knowledge | library | Downloaded at pinned commit; 9 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: CRITICAL 100/100 (credential access + anti-refusal text; do not activate). |
| [Last 30 Days](https://github.com/mvanhorn/last30days-skill) | knowledge | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: scan timed out; not verified. |
| [Career Ops](https://github.com/career-ops-hq/career-ops) | knowledge | library | Downloaded at pinned commit; 11 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| Head Hunter | knowledge | unresolved | Still unresolved after searching GitHub; no confident match or substitute. |
| [Context7](https://github.com/upstash/context7) | knowledge | library | Downloaded at pinned commit; 10 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [Watch](https://github.com/bradautomates/claude-video) | knowledge | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Scrapling](https://github.com/D4Vinci/Scrapling) | knowledge | runtime-installed | Local executable installed; see usage restrictions in the shared guide. |
| [Composio](https://github.com/ComposioHQ/composio) | knowledge | source-identified | Hosted toolkit platform; needs a Composio account. |
| [Impeccable](https://github.com/pbakaus/impeccable) | design | existing-skill | Existing Codex skill and shared reviewed Claude plugin preserved. |
| [Taste](https://github.com/Leonxlnx/taste-skill) | design | not-integrated | Source identified; runtime integration not installed or verified. |
| [MotionSites](https://github.com/Motionsites-AI/claude-skill) | design | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Dimensional Drawing](https://github.com/enesozturk/dimensional-drawing) | design | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Oil UI](https://github.com/oil-oil/oil-ui) | design | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Emil Kowalski Skills](https://github.com/emilkowalski/skills) | design | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Brand Identity](https://github.com/fatihaydost/brand-identity-skill) | design | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [Awwwards MCP](https://github.com/INSANE0777/Awwwards-mcp) | design | not-integrated | Source identified; runtime integration not installed or verified. |
| [Annotated Illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations) | design | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| UI UX Pro Max | design | existing-skill | Existing Codex skill and shared reviewed Claude plugin preserved. |
| Frontend Design | design | existing-skill | Existing Codex skill and shared reviewed Claude plugin preserved. |
| [Awesome Design MD](https://github.com/VoltAgent/awesome-design-md) | design | library | Downloaded at pinned commit; 0 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| Web Design Guidelines | design | existing-skill | Existing Codex skill and shared reviewed Claude plugin preserved. |
| [Figma MCP](https://github.com/figma/mcp-server-guide) | design | source-identified | Official Figma MCP; needs Figma desktop/account. Free two-way alternative: awdr74100/figwright. |
| [Skill UI](https://github.com/Cryptoyankees/skill-ui-claude) | design | source-identified | Weak match only; exact source unknown. |
| [Stage Show](https://github.com/rizaardiyanto1412/stageshow-js) | design | source-identified | Faux product UI + cursor demo skill (port of benjitaylor's StageShow). |
| [Archify](https://github.com/tt-a1i/archify) | design | library | Downloaded at pinned commit; 5 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: scan timed out; not verified. |
| [PPT Master](https://github.com/hugohe3/ppt-master) | design | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: scan timed out; not verified. |
| [Diagram Design](https://github.com/AlanYu04/excalidraw-generator-skill) | design | source-identified | Substitute: Excalidraw diagram skill. Archify (in library) also covers diagrams. |
| Framer | design | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Emergent | design | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| GSAP | design | web-library | Front-end library used when building a site (npm/CDN), not an agent tool. |
| Lenis | design | web-library | Front-end library used when building a site (npm/CDN), not an agent tool. |
| React Bits | design | web-library | Front-end library used when building a site (npm/CDN), not an agent tool. |
| 21st.dev | design | web-library | Front-end library used when building a site (npm/CDN), not an agent tool. |
| Motion.dev | design | web-library | Front-end library used when building a site (npm/CDN), not an agent tool. |
| Anime.js | design | web-library | Front-end library used when building a site (npm/CDN), not an agent tool. |
| shadcn Charts | design | web-library | Front-end library used when building a site (npm/CDN), not an agent tool. |
| transitions.dev | design | web-library | Front-end library used when building a site (npm/CDN), not an agent tool. |
| [HyperFrames](https://github.com/heygen-com/hyperframes) | creative | runtime-installed | Local executable installed; see usage restrictions in the shared guide. |
| [Lemo-Opuscar](https://github.com/lemomo-ai/lemo-opuscar) | creative | skill-installed | Same instruction files installed for Codex and Claude Code. Optional runtime/account requirements remain separate. |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | creative | not-integrated | Source identified; runtime integration not installed or verified. |
| [Teardown](https://github.com/elvarofficial/teardown) | creative | not-integrated | Source identified; runtime integration not installed or verified. |
| [OneTake](https://github.com/feitangyuan/onetake) | creative | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| Collage B-roll | creative | unresolved | Still unresolved after searching GitHub; no confident match or substitute. |
| [Clawd Animation Base](https://github.com/EveryCatchLiu/ClawdAnimation) | creative | source-identified | Closest match: Clawd pixel animations; exact creator download unknown. |
| [Open Montage](https://github.com/OpenMontageInc/OpenMontage) | creative | library | Downloaded at pinned commit; 141 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| Banana Pro Director | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Cinema World Builder | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| OpenHiggsfield | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| [OpenWhispr](https://github.com/OpenWhispr/openwhispr) | creative | source-identified | Local voice dictation app (Whisper/Parakeet). |
| [Cap](https://github.com/CapSoftware/Cap) | creative | source-identified | Open-source Loom alternative (screen recording app). |
| Blender | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| [Blender MCP](https://github.com/ahujasid/mcp-for-blender) | creative | source-identified | Blender add-on + MCP server; install Blender (free) first. |
| DaVinci Resolve | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| [DaVinci Resolve MCP](https://github.com/samuelgursky/davinci-resolve-mcp) | creative | source-identified | Requires DaVinci Resolve Studio (paid) for scripting. |
| Photoshop | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Illustrator | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Premiere Pro | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| After Effects | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Adobe MCP | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Canva | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| CapCut | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| ElevenLabs | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Midjourney | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Stable Diffusion | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| DeepFloyd | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Unity AI | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| iBaila | creative | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| [Playwright MCP](https://github.com/microsoft/playwright-cli) | testing | library | Downloaded at pinned commit; 2 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| Playwright CLI | testing | existing-skill | Existing Codex skill and shared reviewed Claude plugin preserved. |
| [Code Review](https://github.com/anthropics/claude-plugins-official) | testing | library | Downloaded at pinned commit; 57 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [Security Guidance](https://github.com/anthropics/claude-plugins-official) | testing | library | Downloaded at pinned commit; 57 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [Claude Security](https://github.com/anthropics/claude-code-security-review) | testing | source-identified | Security review GitHub Action; Claude Code also has /security-review built in. |
| [Strix](https://github.com/usestrix/strix) | testing | library | Downloaded at pinned commit; 9 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [NVIDIA SkillSpector](https://github.com/NVIDIA/skillspector) | testing | runtime-installed | Local executable installed; see usage restrictions in the shared guide. |
| [Council](https://github.com/karpathy/llm-council) | testing | source-identified | Multi-model council web app; uses OpenRouter credits. Skill version: aiwithremy/claude-skills-llm-council. |
| REA | testing | not-activated | No bypass tools, trading, financial access, or account changes activated. |
| [Pinocchio (uncertain transcription)](https://github.com/pinokiocomputer/pinokio) | testing | source-identified | Likely 'Pinokio': one-click local AI app browser. |
| Humanizer | productivity | existing-skill | Existing Codex skill and shared reviewed Claude plugin preserved. |
| [Stop Slop](https://github.com/hardikpandya/stop-slop) | productivity | library | Downloaded at pinned commit; 1 skill files indexed. Read the guide when a task needs it; nothing was executed. Scan: LOW 0/100. |
| [Anthropic Skills](https://github.com/anthropics/skills) | productivity | library | Downloaded at pinned commit; 20 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [Anthropic Plugins](https://github.com/anthropics/claude-plugins-official) | productivity | library | Downloaded at pinned commit; 57 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [Marketing Skills](https://github.com/coreyhaines31/marketingskills) | productivity | library | Downloaded at pinned commit; 53 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| [I Have ADHD](https://github.com/Leonw98/adhd-claude-skill) | productivity | source-identified | Closest match: focus-session skill for ADHD-style work. |
| [Seed Skill](https://github.com/Jakeschincariol/seed-skill) | productivity | library | Downloaded at pinned commit; 11 skill files indexed. Read the guide when a task needs it; nothing was executed. |
| TraderSkill | productivity | not-activated | No bypass tools, trading, financial access, or account changes activated. |
| Alpaca | productivity | not-activated | No bypass tools, trading, financial access, or account changes activated. |
| [OpenSEO](https://github.com/TahaHachana/OpenSEO) | productivity | source-identified | Open-source SEO tool; skills: every-app/seo-party-skills. |
| [AppFlowy](https://github.com/AppFlowy-IO/AppFlowy) | productivity | source-identified | Open-source Notion alternative app. |
| [OpenProject](https://github.com/opf/openproject) | productivity | source-identified | Self-hosted project management. |
| [Cal.diy](https://github.com/calcom/cal.diy) | productivity | source-identified | Self-hosted scheduling (Cal.com open source). |
| [Cal.com](https://github.com/calcom/cal.diy) | productivity | source-identified | Same project as Cal.diy (self-hosted). |
| [Chatwoot](https://github.com/chatwoot/chatwoot) | productivity | source-identified | Self-hosted support inbox. |
| Hiring.cafe | productivity | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Plaid | productivity | not-activated | No bypass tools, trading, financial access, or account changes activated. |
| Cassidy AI | productivity | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Jack Claude Code OS | productivity | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| Chase Claude OS | productivity | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| VIR Manuscript Assistant | productivity | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| GetLayers | productivity | external-service | Commercial/desktop app or hosted service; needs its own install or account. Don't enable billing. |
| 42-skill team bundle | productivity | unresolved | Still unresolved after searching GitHub; no confident match or substitute. |
| First 100 Customers Skill | productivity | unresolved | Still unresolved after searching GitHub; no confident match or substitute. |
| iOS Agents | productivity | unresolved | Still unresolved after searching GitHub; no confident match or substitute. |
| [Atticus](https://github.com/SaarthurR/atticus-mac) | productivity | platform-blocked | Mac-only; this setup is Windows. |
| Cloudflare Pages | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Cloudflare R2 | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Neon | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Clerk | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Resend | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Supabase | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Vercel | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Namecheap | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Stripe | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| GitHub | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Notion | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Semrush | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Wispr Flow | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Asana | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Calendly | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Intercom | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Loom | services | external-service | Requires a real account/plan/integration; do not enable billing. |
| Rose | inspiration | inspiration | Design/behavior reference, not a plugin to install. |
| Glassy Dashboard V24 | inspiration | inspiration | Design/behavior reference, not a plugin to install. |
| Raspberry Pi Smart Mirror | inspiration | inspiration | Design/behavior reference, not a plugin to install. |
| AI agency demo | inspiration | inspiration | Design/behavior reference, not a plugin to install. |
| Animated reels demo | inspiration | inspiration | Design/behavior reference, not a plugin to install. |
| One-agent playbook workflow | inspiration | inspiration | Design/behavior reference, not a plugin to install. |
| Security audit prompt examples | inspiration | inspiration | Design/behavior reference, not a plugin to install. |
| Codex subscription | models | existing-route | Use Jarvis provider status and existing free-only guards; no new credentials created. |
| Claude Code subscription | models | existing-route | Use Jarvis provider status and existing free-only guards; no new credentials created. |
| Gemini | models | configured-unhealthy | Last generation attempt returned HTTP 503. |
| Grok | models | account-blocked | API key absent; no verified free API entitlement. |
| Kimi | models | account-blocked | API key absent; no verified free API entitlement. |
| OpenRouter free routes | models | existing-route | Use Jarvis provider status and existing free-only guards; no new credentials created. |
| Groq | models | existing-route | Use Jarvis provider status and existing free-only guards; no new credentials created. |
| Local Ollama | models | existing-route | Use Jarvis provider status and existing free-only guards; no new credentials created. |
| [animate](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [animation-performance](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [animation-vocabulary](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [apple-design](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [ask-emil](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [ask-sonner](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [brainstorming](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [brand-identity](https://github.com/fatihaydost/brand-identity-skill) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [break-ui](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [choreograph](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [claudex](https://github.com/ed0ted/claudex) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [defuddle](https://github.com/obsidianmd/obsidian-skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [diagnosing-superpowers](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [dimensional-drawing](https://github.com/enesozturk/dimensional-drawing) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [dimensional-drawing-motion](https://github.com/enesozturk/dimensional-drawing) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [dispatching-parallel-agents](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [emil-design-eng](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [executing-plans](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [find-animation-opportunities](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [finishing-a-development-branch](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [gestures](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [hyperframes](https://github.com/heygen-com/hyperframes) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [hyperframes-cli](https://github.com/heygen-com/hyperframes) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [hyperframes-registry](https://github.com/heygen-com/hyperframes) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [ian-xiaohei-illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [improve-animations](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [inference-optimisation](https://github.com/sybil-solutions/inference-optimisation-skill) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [json-canvas](https://github.com/obsidianmd/obsidian-skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [knap](https://github.com/obsidianmd/obsidian-skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [learn-taste](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [media-use](https://github.com/heygen-com/hyperframes) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [mobile-native](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [motionsites-web-builder](https://github.com/Motionsites-AI/claude-skill) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [obsidian-bases](https://github.com/obsidianmd/obsidian-skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [obsidian-cli](https://github.com/obsidianmd/obsidian-skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [obsidian-headless](https://github.com/obsidianmd/obsidian-skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [obsidian-markdown](https://github.com/obsidianmd/obsidian-skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [oil-ui](https://github.com/oil-oil/oil-ui) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [pick-ui-library](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [prototype](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [receiving-code-review](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [remotion-to-hyperframes](https://github.com/heygen-com/hyperframes) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [remove-animations](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [requesting-code-review](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [reverse-any-video](https://github.com/heygen-com/hyperframes) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [review-animations](https://github.com/emilkowalski/skills) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [scrapling-official](https://github.com/D4Vinci/Scrapling) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [skill-inspector](https://github.com/NVIDIA/skillspector) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [slideshow](https://github.com/heygen-com/hyperframes) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [style-sampling](https://github.com/heygen-com/hyperframes) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [subagent-driven-development](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [systematic-debugging](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [design-taste-frontend](https://github.com/Leonxlnx/taste-skill) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [test-driven-development](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [using-git-worktrees](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [using-superpowers](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [verification-before-completion](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [watch](https://github.com/bradautomates/claude-video) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [writing-plans](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |
| [writing-skills](https://github.com/obra/superpowers) | skill | skill-installed | Instructions installed; optional runtimes and account access are separate. |

Library skills indexed in the catalog: 1601.
