

## Socks5 server

- .. that accepts clients and instead of proxying, sends the data  through a relay.
- Inspired by https://github.com/Amaindex/asyncio-socks-server 

## protocol

like Haproxy PROXY v1
allows TCP/UDP

MPROXY TCP 4 SRC DST SRCPORT DSTPORT\r\n

## proxy server

based on Asyncio Socks server

accepts Socks5 clients, does all kinds of ACLS

instead of Remote TCP\UDP servers, calls relay.

Talks to the relay with protocol

DNS requests are made within relay too.


## TCP relay server

accepts connections. Reads protocol header. Establish remote TCP/UDP. Reads-writes data between connected cliend and the remoteTCP/remoteUDP.

