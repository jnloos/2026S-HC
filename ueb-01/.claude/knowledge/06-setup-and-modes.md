# Setup & Operating Modes

App Lab is the desktop/board software for creating and launching Apps on the
UNO Q. The board can be used in three modes.

## First-time setup (required once)
Connect via USB-C and run the install/first-setup flow. You provide:
- **Wi-Fi credentials**
- A **board name (hostname)**
- A **login password** (default `arduino`)

The flow also updates the board to the latest version. Network and SBC modes are
only available **after** this USB first-setup is done.

## Three modes

### 1. Host computer (USB-C, "desktop mode")
1. Start App Lab on your computer.
2. Connect the board via USB-C.
3. Select the board (USB option) in App Lab.
4. Run the installation flow (Wi-Fi, name, password).

### 2. Network mode (Remote / SSH)
Access the board over local Wi-Fi via SSH — works just like USB but wireless.
1. Start App Lab.
2. Ensure the board is on Wi-Fi (shown in App Lab's bottom bar).
3. Select the **Network** option.
Available only after the board has been configured.

### 3. Single-Board Computer (SBC)
Use the board standalone with screen/keyboard/mouse (must do USB setup first):
1. Connect a USB-C dongle to the board's USB-C port.
2. Power the dongle separately with a 5 V USB-C supply.
3. Attach keyboard, mouse, and HDMI display to the dongle.
4. Board boots Debian; log in (`arduino / arduino` by default). App Lab launches
   automatically and you run Apps directly on the board.

> **Bonus:** while in SBC mode you can *also* connect via Network mode — develop
> on your computer, test live on the board.

## Auto-update
On startup the system checks for and installs updates; App Lab restarts when
done.

## Accessing a running App over the network
- On the board (with display): `http://localhost:7000`
- From another device on the same network: `http://<board-hostname>.local:7000`

### Port forwarding to your dev machine (USB/Network mode)
When developing from a laptop, opening `http://127.0.0.1:7000` on the **laptop**
is expected — it's **not** a local server. The app (and its Web UI Brick) run on
the board; App Lab **forwards the ports declared in `app.yaml` (`ports:`) to the
laptop's localhost** over the USB/Network connection, purely as a dev
convenience.
- Only **declared** ports are forwarded. `ports: []` ⇒ no local access at all;
  add the Web UI port (e.g. `ports: [7000]`) to get the `127.0.0.1:7000` tunnel.
- The "real" address is still `http://<board-hostname>.local:7000`, reachable
  from any device on the same Wi-Fi; `localhost:7000` only works on the laptop
  App Lab is forwarding to.

## CLI
App Lab ships a command-line tool (docs:
`docs.arduino.cc/software/app-lab/cli/`) for managing apps/boards from a terminal
— useful for scripting and headless workflows.
