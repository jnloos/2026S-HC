# Problem: USB-Kamera am Arduino UNO Q wird nicht (dauerhaft) erkannt

## Setup
- **Board:** Arduino UNO Q (Qualcomm-basierte Linux-MPU, Kernel `7.0.0`,
  USB-Controller `dwc3` @ `4e00000.usb`).
- **Peripherie:** USB-Hub am USB-C-Port des Boards, daran eine USB-Webcam
  (Logitech C270, `046d:0825`).
- **Zugang zum Board:** über WLAN/SSH (der einzige USB-C-Port ist also frei für
  den Hub, nicht durch das Laptop belegt).
- **Ziel:** Die Kamera soll dauerhaft als Capture-Device (`/dev/videoN`) zur
  Verfügung stehen, damit eine App darauf zugreifen kann.

## Symptom
- Direkt nach dem Boot wird die Kamera **kurz erkannt**, verschwindet dann aber
  nach wenigen Sekunden wieder.
- Im laufenden Betrieb ist `lsusb` leer (nur Root-Hubs), die App meldet
  „No Camera Device Found".

## Diagnose (Belege)

**1. Beim Boot funktioniert es kurz — dann Disconnect:**
```
[12.78] uvcvideo 1-1.2:1.0: Found UVC 1.00 device C270 HD WEBCAM (046d:0825)
[16.86] usb 1-1.2: USB disconnect, device number 4      # Kamera weg
[16.87] usb 1-1:   USB disconnect                        # Hub weg
[17.01] xhci-hcd ... USB bus 1 deregistered
[33.76] usb_vbus: disabling                              # Board schaltet VBUS ab
```

**2. Der USB-C-Port ist OTG/Dual-Role und kippt auf „device":**
```
/sys/.../usb@4e00000/dr_mode                 = otg
/sys/class/usb_role/4e00000.usb-role-switch/role = device   # sollte host sein
```

**3. Der Type-C-Port kann selbst keinen Strom liefern (nur Sink):**
```
/sys/class/typec/port0/power_role = [sink]   # keine "source"-Option
/sys/class/typec/port0/data_role  = host [device]
```

**4. Die VBUS-Versorgung ist ein separater Regulator — und ist aus:**
```
/sys/class/regulator/.../name  = usb_vbus
                         state = disabled
                         num_users = 0        # kein Treiber hält ihn an
```

**5. Daten-Rolle per sysfs auf „host" zwingen reicht NICHT:**
```
echo host > /sys/class/usb_role/4e00000.usb-role-switch/role
# -> role = host, xHCI-Host-Controller startet neu, ABER:
# -> usb_vbus bleibt "disabled" -> Port liefert keinen Strom
# -> lsusb zeigt nur Root-Hubs, Kamera erscheint nicht
```

## Analyse / Vermutung
- Der Port startet beim Boot als **Host** (VBUS an, Kamera wird erkannt), fällt
  dann durch die OTG-State-Machine in den **Device-Modus** und schaltet dabei
  die eigene **VBUS ab**.
- Verdacht: Der verwendete **aktive (eigenversorgte) USB-Hub** speist VBUS
  **rückwärts** in den Port. Der Type-C-Controller wertet das als „ich werde
  versorgt → ich bin Sink/Device" und kippt in den Device-Modus.
- Das nachträgliche Setzen der **Daten-Rolle** auf `host` reaktiviert die
  **Strom-Versorgung (VBUS)** nicht — vermutlich, weil VBUS hier über einen
  separaten Regulator (`usb_vbus`) läuft, der ohne Consumer/OTG-Session nicht
  eingeschaltet wird.
- **Unsicherheit:** Einmalig lief es *mit* dem aktiven Hub im Host-Modus inkl.
  VBUS — d.h. der Hub ist nicht eindeutig allein schuld; die OTG/VBUS-Logik
  spielt mit hinein.

## Konkrete Fragen an den Prof
1. Ist der **aktive Hub** (VBUS-Back-Feed) hier plausibel die Ursache, oder eher
   die OTG-Konfiguration des Ports?
2. Sauberster Weg, den Port **dauerhaft als Host mit aktiver VBUS** zu betreiben?
   - Device-Tree `dr_mode = "host"` (statt `otg`) — auf diesem EFI/dtb-Image
     ohne einfaches Overlay; wie am besten umsetzen?
   - Oder den `usb_vbus`-Regulator zur Laufzeit erzwingen (GPIO/Consumer)?
3. Reicht in der Praxis ein **passiver (bus-powered) Hub** bzw. ein direkter
   **USB-C→USB-A-OTG-Adapter**, um das Problem hardwareseitig zu umgehen?

## Schneller Eingrenzungstest (geplant)
Kamera **direkt** per einfachem USB-C→USB-A-OTG-Adapter (ohne aktiven Hub)
anschließen, rebooten, `lsusb` prüfen:
- Kamera bleibt → der aktive Hub war die Ursache (passiver Hub/Adapter genügt).
- Kamera verschwindet trotzdem → Ursache ist die OTG/VBUS-Logik (Software-Fix
  `dr_mode=host` nötig, anderer Hub hilft nicht).
