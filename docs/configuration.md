# Configuration

The data folder is set in the app (Setup or Settings). Everything else is in
`.env` (see [`.env.example`](../.env.example)): the address the server listens on,
CORS and the terminal are security settings, and a web page cannot change them.

| Variable | Default | Purpose |
|---|---|---|
| `SP_DATA_ROOT` | `~/.slightly-parallel` | The data folder. Set it in the app; it is saved here. Made on the first start, with the example project in it. `SCAN_DATA_ROOT` and `DATA_ROOT` are also read |
| `HOST` / `SP_PORT` | `127.0.0.1` / `8123` | The address and port the backend listens on; `SCAN_PORT` and `PORT` are also read |
| `VITE_PORT` | `5173` | The hot-reload UI's port (`./run.sh` with no flag) |
| `SP_REBUILD_UI` | off | A production start rebuilds the UI (needs Node 20+); otherwise it serves the build that comes with the release, `frontend/dist` |
| `SP_ALLOW_LAN` | off | Needed to start with a `HOST` other than `127.0.0.1`; see below |
| `SP_CORS_ORIGINS` | localhost dev origins | The addresses the pages are opened at; `SCAN_CORS_ORIGINS` is also read |
| `SP_ENABLE_TERMINAL` | off | Forces the terminal on (it is otherwise a switch in Settings) |

> **Security note:** Slightly Parallel has no login. It is built to be reached from the computer it runs on.
>
> - **Other web pages.** The server answers only requests addressed to this computer (`127.0.0.1`, `localhost`, or an address listed in `SP_CORS_ORIGINS`), and refuses a write made by another site's page. A page open in your browser cannot read your chats or change settings through it.
> - **The network.** With `HOST=0.0.0.0` every machine on the network could read every chat and change every setting, so the server starts that way only with `SP_ALLOW_LAN=1`. If you set it, also list the address you open (`http://192.168.1.5:8123`) in `SP_CORS_ORIGINS`.
> - **The terminal** runs a real shell on the host. It is off until switched on in Settings › Terminal. The server makes the token and hands it only to Slightly Parallel's own pages; every connection carries it, and requests from other sites are refused.
> - **Writes as the operator.** The server gives its own pages a cookie the first time they load (`HttpOnly`, `SameSite=Strict`). A write that names no agent and comes without the cookie is refused. A plain request from a script or an agent, such as `curl`, cannot write as the operator.
> - **Agents.** "Agents write through MCP only" and "only the operator moves a task to done" are rules for agents that follow instructions. They are not a defence against a hostile program on the same computer: it can load the page to get the cookie, or edit the data files directly. Run agents you would trust with your files.
> - **Artifacts** are files an agent wrote. Slightly Parallel shows them in a sandbox, where a script in one cannot reach the dashboard.

## The data folder

Everything Slightly Parallel records is in the data folder you chose: CSV files
and Markdown detail documents. Every file is optional; a missing one shows as an
empty list.

```
~/.slightly-parallel/
├── scans.csv                     # one row per scan (append-only)
├── snapshots/*.md                # the text of each scan
├── decisions.csv  tasks.csv  standups.csv  sprints.csv  ...
│                                 # one CSV per kind of entry (see docs/api.md)
├── <entity>_details/*.md         # detail documents referenced by md_ref
└── projects/
    └── <project-code>/
        ├── chats/<agent-id>/
        │   ├── meta.json         # agent identity + headline
        │   └── chat.md           # the chat, word for word
        ├── artifacts/<name>/     # folders an agent wrote for #artifact
        ├── architecture/vNNN.md  # the architecture page, one file per version
        ├── map/vNNN.json         # the map of the program, one file per version
        └── log.md                # the project's own notes
```
