# jan/02/1970 03:43:19 by RouterOS 6.49.7
# software id = PLF5-PCE8
#
# model = 751U-2HnD
# serial number = 45E402F90E85
/interface bridge
add admin-mac=D4:CA:6D:96:73:99 auto-mac=no comment=defconf igmp-snooping=yes \
    name=bridge
/interface vlan
add interface=bridge name=vlan99-olt vlan-id=99
add interface=bridge name=vlan200 vlan-id=200
add interface=bridge name=vlan300-iptv vlan-id=300
add interface=bridge name=vlan400-voip vlan-id=400
add interface=bridge name=vlan1000-datos vlan-id=1000
/interface list
add comment=defconf name=WAN
add comment=defconf name=LAN
/interface wireless security-profiles
set [ find default=yes ] supplicant-identity=MikroTik
add authentication-types=wpa2-psk mode=dynamic-keys name=wifi-security \
    supplicant-identity=MikroTik wpa2-pre-shared-key=gpon1234
/interface wireless
set [ find default-name=wlan1 ] band=2ghz-b/g/n country=argentina disabled=no \
    frequency=2437 installation=indoor mode=ap-bridge noise-floor-threshold=\
    -110 security-profile=wifi-security ssid=MQTT wps-mode=disabled
/ip pool
add name=default-dhcp ranges=192.168.88.10-192.168.88.254
add name=pool-ether3 ranges=10.1.1.10-10.1.1.254
add name=pool-onus ranges=10.1.1.10-10.1.1.254
add name=pool-gestion ranges=192.168.10.10-192.168.10.20
add name=dhcp_pool4 ranges=192.168.20.10-192.168.20.200
/ip dhcp-server
add address-pool=pool-onus disabled=no interface=vlan200 name=dhcp-onus
add address-pool=pool-gestion disabled=no interface=ether5 name=dhcp-gestion
add address-pool=dhcp_pool4 disabled=no interface=bridge name=dhcp1
/interface bridge port
add bridge=bridge comment=defconf interface=ether2
add bridge=bridge comment=defconf interface=ether3
add bridge=bridge comment=defconf interface=ether4
add bridge=bridge interface=wlan1
/ip neighbor discovery-settings
set discover-interface-list=LAN
/interface bridge vlan
add bridge=bridge tagged=bridge,ether2,ether3,ether4,ether5 vlan-ids=200
/interface list member
add comment=defconf interface=bridge list=LAN
add comment=defconf interface=ether1 list=WAN
add interface=ether5 list=LAN
add interface=wlan1 list=LAN
/ip address
add address=10.1.1.1/24 interface=vlan200 network=10.1.1.0
add address=192.168.10.1/24 interface=ether5 network=192.168.10.0
add address=10.99.99.1/24 interface=vlan99-olt network=10.99.99.0
add address=10.30.0.1/24 interface=vlan300-iptv network=10.30.0.0
add address=192.168.20.1/24 interface=bridge network=192.168.20.0
/ip dhcp-client
add comment=defconf disabled=no interface=ether1
/ip dhcp-server lease
add address=192.168.20.199 client-id=1:8:a6:f7:a8:6f:e8 comment=\
    "Sensor ESP Facu" mac-address=08:A6:F7:A8:6F:E8 server=dhcp1
add address=192.168.20.198 client-id=1:4c:d5:77:be:45:41 comment=\
    "Notebook Facu" mac-address=4C:D5:77:BE:45:41 server=dhcp1
/ip dhcp-server network
add address=10.1.1.0/24 dns-server=10.1.1.1 gateway=10.1.1.1
add address=192.168.10.0/24 dns-server=8.8.8.8 gateway=192.168.10.1
add address=192.168.20.0/24 dns-server=192.168.20.1 gateway=192.168.20.1
/ip dns
set allow-remote-requests=yes servers=1.1.1.1,8.8.8.8
/ip dns static
add address=192.168.88.1 comment=defconf name=router.lan
/ip firewall filter
add action=accept chain=forward dst-port=1883 protocol=tcp
add action=accept chain=input comment=\
    "defconf: accept established,related,untracked" connection-state=\
    established,related,untracked
add action=accept chain=input comment="defconf: accept ICMP" protocol=icmp
add action=accept chain=input comment=\
    "defconf: accept to local loopback (for CAPsMAN)" dst-address=127.0.0.1
add action=drop chain=input comment="defconf: drop all not coming from LAN" \
    disabled=yes in-interface-list=!LAN
add action=accept chain=forward comment="defconf: accept in ipsec policy" \
    ipsec-policy=in,ipsec
add action=accept chain=forward comment="defconf: accept out ipsec policy" \
    ipsec-policy=out,ipsec
add action=fasttrack-connection chain=forward comment="defconf: fasttrack" \
    connection-state=established,related
add action=accept chain=forward comment=\
    "defconf: accept established,related, untracked" connection-state=\
    established,related,untracked
add action=drop chain=forward comment="defconf: drop invalid" \
    connection-state=invalid disabled=yes
add action=drop chain=forward comment=\
    "defconf: drop all from WAN not DSTNATed" connection-nat-state=!dstnat \
    connection-state=new disabled=yes in-interface-list=WAN
add action=drop chain=input comment="defconf: drop invalid" connection-state=\
    invalid disabled=yes
/ip firewall nat
add action=dst-nat chain=dstnat disabled=yes dst-port=1883 protocol=tcp \
    to-addresses=192.168.20.198
add action=masquerade chain=srcnat comment="defconf: masquerade" \
    ipsec-policy=out,none out-interface-list=WAN
add action=masquerade chain=srcnat disabled=yes dst-address=0.0.0.0 \
    out-interface=ether1 src-address=0.0.0.0
add action=masquerade chain=srcnat out-interface=ether1
/ip service
set ssh address=0.0.0.0/0
/tool mac-server
set allowed-interface-list=LAN
/tool mac-server mac-winbox
set allowed-interface-list=LAN
