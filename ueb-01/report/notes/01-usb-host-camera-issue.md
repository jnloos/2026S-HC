# Issue: USB-Kamera am UNO Q wird nicht erkannt (gelöst)

**Status:** gelöst am 2026-06-04. Persistenter Fix als systemd-Service installiert.

## Symptom
- Nach einem **Reboot** wird die USB-Webcam (Logitech C270, `046d:0825`) nicht
  mehr erkannt; die App meldet sinngemäß „No Camera Device Found".
- `lsusb` zeigt **keine** USB-Geräte (nur Root-Hubs).
- **Drei verschiedene USB-Hubs** ausprobiert — kein Unterschied.

## Diagnose (live am Board belegt)
Aktueller Zustand vor dem Fix:
```
usb role  = device          # sollte "host" sein
usb_vbus  = disabled         # Port liefert keinen Strom
lsusb     = leer
```
dmesg-Zeitachse direkt nach dem Boot:
```
[12.75] uvcvideo 1-1.3:1.0: Found UVC 1.00 device C270 HD WEBCAM (046d:0825)  ← Kamera kurz da
[17.04] xhci-hcd ... remove        ← Host-Controller wird abgebaut
[17.08] usb 1-1.3: USB disconnect  ← Kamera weg
[33.76] usb_vbus: disabling        ← Board schaltet die Port-Versorgung ab
```
→ Die Kamera ist beim Boot **kurz** da und verschwindet dann.

## Ursache (bestätigt)
Der UNO Q hat **einen einzigen USB-C-Port**, der gleichzeitig **Strom-Eingang
und USB-Host-Port** ist. Wird das Board über **VIN oder den 5V-Pin** versorgt
(nötig in unserem Aufbau, damit der USB-C-Port für die Kamera frei ist), bootet
der Qualcomm-/DWC3-USB-Controller im **Device-Modus** und lässt den
`usb_vbus`-Regulator **aus**. Der Port scannt dann gar keinen Bus.

> Offizielle Aussage eines Arduino-Entwicklers im Forum:
> *„It is not possible to use the USB-C port as a power outlet when the board is
> powered via VIN. This is not a supported scenario."*

**Deshalb war der Hub nie schuld:** Im Device-Modus wurde der Bus nie gescannt —
unabhängig davon, welcher (auch aktiver, eigenversorgter) Hub angeschlossen war.
Das erklärt, warum drei Hubs nichts geändert haben.

Board-Image im Test: `BUILD_ID=20251210-442`, Debian 13 (trixie). Auch die
neuesten Images brauchen den manuellen Switch (Stand Foren Q2/2026).

## Fix
Datenrolle des Ports per debugfs auf **host** zwingen:
```bash
echo host > /sys/kernel/debug/usb/4e00000.usb/mode
```
Ergebnis sofort:
```
mode = host
lsusb -> 046d:0825 Logitech Webcam C270  (+ Hub)
/dev/video1, /dev/video2 erscheinen (UVC-Knoten der C270)
```
**Bemerkenswert:** `usb_vbus` meldet danach weiterhin `disabled`, die Kamera
enumeriert aber trotzdem — den Strom liefert der (aktive) Hub. Entscheidend war
also allein die **Daten-Rolle (host)**, nicht der VBUS-Regulator. (Das
korrigiert die frühere Vermutung in `uno-q-usb-host-problem.md`, die VBUS
als Kern-Blocker ansah.)

## Persistenz (Reboot-fest)
Der debugfs-Write ist flüchtig (Reboot setzt zurück → genau der ursprüngliche
Fehler). Daher als systemd-Service hinterlegt:

`/etc/systemd/system/uno-q-usb-host.service`
```ini
[Unit]
Description=Force UNO Q USB-C port into host mode (workaround for VIN/5V power; dwc3 boots in device mode otherwise)
After=sys-kernel-debug.mount
Requires=sys-kernel-debug.mount

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c "echo host > /sys/kernel/debug/usb/4e00000.usb/mode"

[Install]
WantedBy=multi-user.target
```
`systemctl enable --now uno-q-usb-host.service` → aktiviert.

## Offene Punkte / Empfehlungen
- **Reboot-Test ausstehend:** verifizieren, dass der Service nach einem echten
  Reboot greift (der Port kippt ~17 s nach Boot in den Device-Modus; der
  oneshot muss danach laufen bzw. erneut auf host setzen). Falls nicht stabil:
  Service zeitversetzt/wiederholt re-asserten (z. B. per Timer oder kurzer Sleep).
- **Sauberste Hardware-Alternative:** Board über den **`5VIN`-Pin** versorgen
  (liegt direkt an der USB-Stromschiene) → Host-Modus + VBUS funktionieren ohne
  Software-Fix.

## Quellen
- Arduino-Forum: „USB Power disabled, if using VIN Power pin"
  https://forum.arduino.cc/t/usb-power-disabled-if-using-vin-power-pin/1411831
- Arduino-Forum: „UNO Q – USB Host Mode Fix (VIN Power)"
  https://forum.arduino.cc/t/arduino-uno-q-usb-host-mode-fix-vin-power/1428592
- Arduino-Forum: „Connecting USB Camera to Uno Q"
  https://forum.arduino.cc/t/connecting-usb-camera-to-uno-q/1412062
- GitHub: Psalmustrack/arduino-uno-q-usb-fix (systemd-Service-Vorlage)
  https://github.com/Psalmustrack/arduino-uno-q-usb-fix
