

## Relay server 

.. for my Socks5 server

- that accepts relayed requests and sends the data to the website and send responses back to the relay client.
- Inspired by https://github.com/Amaindex/asyncio-socks-server 

## protocol

- like Haproxy PROXY v1
- allows TCP/UDP

Header: 

```
MPROXY TCP 4 DST DSTPORT ORIG_SRC_ADDR ORIG_SRC_PORT USERNAME\r\n
```


