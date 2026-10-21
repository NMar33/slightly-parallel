# Running Slightly Parallel

You need **Python 3.11+** and **git**. On Debian or Ubuntu also
`sudo apt install python3-venv`. The UI comes built (`frontend/dist`);
**Node 20+** is needed only to rebuild it (`SP_REBUILD_UI=1` in `.env`, or
`npm run build` in `frontend/`) and for the hot-reload start. `tmux` is optional: with it, the
terminals stay open after a reload or a restart.

```bash
git clone https://github.com/nmar33/slightly-parallel.git slightly-parallel
cd slightly-parallel
./run.sh --prod       # serves everything from http://127.0.0.1:8123
```

The first start takes a minute: it makes the backend's environment. To work on Slightly Parallel's own
code, `./run.sh` with no flag starts the backend on :8123 and a hot-reload UI
on :5173. On Windows: `sp run --prod` and `sp run`.

When a start fails (a port in use, Node not found), the last line says what to do.

## As a service

One launcher, `sp.py`, on Linux, macOS and Windows (Python 3.11+;
Node 20+ to rebuild the UI). `sp.sh` (Linux, macOS) and `sp.cmd` (Windows) run it;
`run.sh` is `sp.sh run`. In the background, a server that crashes is
restarted:

```bash
./sp.sh up            # prod mode, auto-restarting, in the background
./sp.sh up --dev      # same, with the hot-reload dev pair
./sp.sh status        # supervisor / health / terminal state
./sp.sh logs          # follow the server log
./sp.sh restart       # down, then up in the same mode
./sp.sh down          # stop everything
./sp.sh run [--prod]  # in the foreground; Ctrl+C stops it
./sp.sh terminal on   # switch the embedded terminal on (the same switch as Settings › Terminal)
./sp.sh terminal off
```

On Windows the same commands are `sp up`, `sp status`, … in the
repository folder (Command Prompt or PowerShell).

## At login, and a shortcut

```bash
./sp.sh autostart on  # start the server (sp up) when you log in
./sp.sh autostart off # remove exactly what "on" wrote
./sp.sh shortcut      # a shortcut that runs sp open; "shortcut off" removes it
./sp.sh open          # start the server if it is not running, then open the page
```

The same two switches are in Setup (Integrate your project, off by
default) and in Settings › On this computer. Without administrator rights,
each system its own way:

| | at login | shortcut |
|---|---|---|
| Linux | `~/.config/autostart/slightly-parallel.desktop` | the applications menu, and the desktop folder |
| macOS | `~/Library/LaunchAgents/dev.slightly-parallel.server.plist` | `Slightly Parallel.app` on the desktop |
| Windows | `Slightly Parallel.cmd` in the Startup folder | `Slightly Parallel.lnk` on the desktop and in the Start menu |

At login the server starts in production mode with the built UI, so Node
is not needed. What was written is listed in `.sp/autostart.json`. Memory
and load: [performance.md](performance.md).

Configuration, the ports and the network: [configuration.md](configuration.md).

## When something is wrong

`python sp.py report` writes `slightly-parallel-report-<date>.md` into the app
folder: the machine and version, the server's memory now and at its peak, its
memory hour by hour for a day, slow requests, warnings and errors from the log,
the capture hooks' errors, the size of the data and of the tools' transcripts,
and the supervisor's output. Monitor › Server › **download report** gives the
same file from the running server. It holds no chat text and no values from
`.env`, with query strings cut; paths under the home folder start with `~`.
Read it before sending it. When the server does not
answer, the command builds the file from the logs and the data alone.

The server writes its memory into the log every 5 minutes (`sp.memory`), and a
warning when it passes 1 GB or grew by 300 MB since the last line. Test servers
(`SP_SANDBOX=1`) log into `.sp/sandbox/`, not beside the real one.

What is recorded, where, for how long, and where to look: `docs/monitoring.md`.
