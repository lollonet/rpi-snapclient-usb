SNAPCLIENT — QUICK INSTALL
============================

1. Flash "Raspberry Pi OS Lite (64-bit)" with Raspberry Pi Imager
   -> Configure WiFi and hostname in the Imager settings

2. Re-insert SD card in your computer

3. Copy this entire "snapclient" folder to the boot partition
   (the partition that opens automatically on your computer)

4. Eject SD card, insert in Pi, power on

5. Wait ~5 minutes — Pi installs everything and reboots automatically


Your audio HAT is detected automatically.
Edit snapclient.conf ONLY if auto-detection does not work.

After install, play music on your Snapserver and enjoy!


MANUAL INSTALL (alternative):
  SSH into the Pi after boot and run:
  sudo bash /boot/firmware/snapclient/scripts/setup.sh


TROUBLESHOOTING:
  Check install log: cat /var/log/snapclient-install.log
  Check service:     sudo systemctl status snapclient
  Re-run setup:      sudo bash /opt/snapclient/scripts/setup.sh
