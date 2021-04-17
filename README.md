# Bootstrap EVE-NG NX-OS devices

This script was written to bootstrap EVE-NG NXOS devices by logging in through
console of each device and configuring DHCP. An ansible host file will be generated
locally with the name of the device and it's assigned IP.

1. You must create the labs with the admin user or the telnet ports will not be calculated
   properly
2. You must have unique names for each device, the devices dictionary created
   takes into account that you will have a unique key name (the device name)
3. You must have mgmt0 connected to a DHCP server that will provide an IP
   address within 30 seconds of configuration.
4. You must use an NXOS device that has a default username of admin and no
   password configured.


