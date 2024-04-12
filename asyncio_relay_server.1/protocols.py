import asyncio
import itertools
import socket
from asyncio.streams import StreamReader
from socket import AF_INET, AF_INET6, inet_ntop, inet_pton
from typing import Optional, Tuple

from asyncio_relay_server.config import Config
from asyncio_relay_server.exceptions import (
    AuthenticationError,
    CommandExecError,
    HeaderParseError,
    NoAtypAllowed,
    NoAuthMethodAllowed,
    NoCommandAllowed,
    NoVersionAllowed,
    SocksException,
)
from asyncio_relay_server.logger import access_logger, error_logger, logger
import re
import time

class SpeedAnalyzer:
    def __init__(self):
        self.data = []  # Data structure to store (timestamp, amount_of_bytes) tuples

    def add_data(self, timestamp, amount_of_bytes):
        self.data.append((timestamp, amount_of_bytes))

    def calculate_average_speed(self):
        duration=3
        current_time = time.time()
        start_time = current_time - duration

        total_bytes = 0
        count = 0

        if len(self.data)>1000:
            self.cleanup_data()

        for timestamp, bytes_ in self.data[::-1]:
            if timestamp < start_time :
                break

            total_bytes += bytes_
            count += 1
        if count == 0:
            return 0
        else:
            return round(total_bytes / ( duration * 1000 * 1.1 ) ) 
            #Average Kbytes/s

    def cleanup_data(self):
            current_time = time.time()
            ten_seconds_ago = current_time - 10
            self.data = [(ts, bytes_) for ts, bytes_ in self.data if ts >= ten_seconds_ago]

#DL=SpeedAnalyzer()
#UL=SpeedAnalyzer()


def query(resolver, name, query_type):
    try:
        answers = resolver.query(name, query_type)
        for rdata in answers: 
            return rdata.to_text()
    except Exception as e:
        print(e)

#def acl(config, DST_ADDR):
#    for banned_dst in config.BANNED_DST :
#        if re.search(rf'\.?{banned_dst}$' , DST_ADDR):
#            return -1

class LocalTCP(asyncio.Protocol):
    STAGE_NEGOTIATE = 0
    STAGE_CONNECT = 1
    STAGE_UDP_ASSOCIATE = 3
    STAGE_DESTROY = -1

    def __init__(self, config: Config):
        self.config = config
        self.stage = None
        self.transport = None
        self.remote_tcp = None
        self.local_udp = None
        self.peername = None
        self.stream_reader = StreamReader()
        self.negotiate_task = None
        self.is_closing = False
        #self.__init_authenticator_cls()

#    def __init_authenticator_cls(self):
#        for cls in AUTHENTICATORS_CLS_LIST:
#            if cls.METHOD == self.config.AUTH_METHOD:
#                self.authenticator_cls = cls

    def write(self, data):
        if not self.transport.is_closing():
            self.transport.write(data)
###### with speed limit:
#        if not self.transport.is_closing():
#            global DL
#            DL.add_data( time.time() , len(data))
#            DL_SPEED = DL.calculate_average_speed()
#            MAX_DL_SPEED=self.config.MAX_DL_SPEED
#            if MAX_DL_SPEED and DL_SPEED > MAX_DL_SPEED :
#                SL=0.2
#                CHUNKSIZE=round( len(data) / 8 )
#                for data_chunk in [data[i:i+CHUNKSIZE] for i in range(0, len(data), CHUNKSIZE)]:
#                    time.sleep(SL)
#                    if not self.transport.is_closing():
#                        self.transport.write(data_chunk)
#            else:
#                self.transport.write(data)

    def connection_made(self, transport):
        self.transport = transport
        self.peername = transport.get_extra_info("peername")
        self.stream_reader.set_transport(transport)
        self.config.ACCESS_LOG and access_logger.debug(
            f"Made LocalTCP connection from {self.peername}"
        )
        loop = asyncio.get_event_loop()
        self.negotiate_task = loop.create_task(self.negotiate())
        self.stage = self.STAGE_NEGOTIATE


#    @staticmethod
#    def gen_reply(
#        rep: SocksRep,
#        bind_host: str = "0.0.0.0",
#        bind_port: int = 0,
#    ) -> bytes:
#        """Generate reply for negotiation."""
#
#        VER, RSV = b"\x05", b"\x00"
#        ATYP = get_socks_atyp_from_host(bind_host)
#        if ATYP == SocksAtyp.IPV4:
#            BND_ADDR = inet_pton(AF_INET, bind_host)
#        elif ATYP == SocksAtyp.IPV6:
#            BND_ADDR = inet_pton(AF_INET6, bind_host)
#        else:
#            BND_ADDR = len(bind_host).to_bytes(2, "big") + bind_host.encode("UTF-8")
#        REP = rep.to_bytes(1, "big")
#        ATYP = ATYP.to_bytes(1, "big")
#        BND_PORT = int(bind_port).to_bytes(2, "big")
#        return VER + REP + RSV + ATYP + BND_ADDR + BND_PORT

    async def negotiate(self):

        print('start negotiate')
        try:
            # Step 1
            # The client sends a MPROXY header.
            data  = await self.stream_reader.readexactly(6)
            if data != b'MPROXY' :
                raise NoVersionAllowed(f"Received wrong header: {data}")
            else:
                HEADER=data

            # The client send rest of the header ending with \r\n
            while True:
                data = await self.stream_reader.readexactly(1)
                #print(data)
                if data == b'\r':
                    await self.stream_reader.readexactly(1) # read \n
                    break
                else:
                    HEADER+=data
            
            HEADER=HEADER.decode()
            #print('read HEADER', HEADER)

            try:
                _, PROTO, DST_ADDR, DST_PORT = HEADER.split(' ')
            except:
                raise CommandExecError(f"Can't parse HEADER: {HEADER}")

            self.config.ACCESS_LOG and access_logger.info(
                f'Incoming Relay request to {PROTO}://{DST_ADDR}:{DST_PORT}'
            )


            # resolve if needed.
            if ':' in DST_ADDR or not re.match(r'\d', DST_ADDR):
                HNAME=DST_ADDR

                self.config.ACCESS_LOG and access_logger.debug(
                    f'Resolving remote name {HNAME}'
                )
                DST_ADDR = query(self.config.resolver, HNAME , 'A')
                if not DST_ADDR:
                    raise CommandExecError("Can't resolve hostname {HNAME}")
                self.config.ACCESS_LOG and access_logger.debug(
                    f'{HNAME} resolved to {DST_ADDR}'
                )
            # Now DST_ADDR is Ipv4/Ipv6. 
                

            # Step 2
            # The server handles the command and returns a reply.
            TCP_CONNECT_TIMEOUT=2
            if PROTO == 'TCP':
                self.stage = self.STAGE_CONNECT
                #print('my stage', self.stage)
                try:
                    loop = asyncio.get_event_loop()
                    task = loop.create_connection(
                        lambda: RemoteTCP(self, self.config), DST_ADDR, DST_PORT
                    )
                    remote_tcp_transport, remote_tcp = await asyncio.wait_for(task, TCP_CONNECT_TIMEOUT)
                except ConnectionRefusedError:
                    raise CommandExecError("Connection was refused") from None
                except socket.gaierror:
                    raise CommandExecError("Host is unreachable") from None
                except Exception as e:
                    raise CommandExecError(
                        f"General socks server failure occurred {e}"
                    ) from None
                else:
                    self.remote_tcp = remote_tcp
                    bind_addr, bind_port = remote_tcp_transport.get_extra_info(
                        "sockname"
                    )

                    self.config.ACCESS_LOG and access_logger.info(
                        f"Established TCP stream between"
                        f" {self.peername} and {self.remote_tcp.peername}"
                    )
            elif PROTO == 'UDP' :
                try:
                    loop = asyncio.get_event_loop()
                    task = loop.create_datagram_endpoint(
                        lambda: LocalUDP((DST_ADDR, DST_PORT), self.config),
                        local_addr=("0.0.0.0", 0),
                    )
                    local_udp_transport, local_udp = await asyncio.wait_for(task, 5)
                except Exception:
                    raise CommandExecError(
                        "General socks server failure occurred"
                    ) from None
                else:
                    self.local_udp = local_udp
                    bind_addr, bind_port = local_udp_transport.get_extra_info(
                        "sockname"
                    )
                    self.stage = self.STAGE_UDP_ASSOCIATE

                    self.config.ACCESS_LOG and access_logger.info(
                        f"Established UDP relay for client {self.peername} "
                        f"at local side {bind_addr,bind_port}"
                    )
            else:
                raise NoCommandAllowed(f"Unsupported CMD value: {CMD}")

        except Exception as e:
            error_logger.warning(f"{e} during the negotiation with {self.peername}")
            self.close()

    def data_received(self, data):
        print(f'LocalTCP: at stage {self.stage} rcvd data {data}')
        if self.stage == self.STAGE_NEGOTIATE:
            self.stream_reader.feed_data(data)
        elif self.stage == self.STAGE_CONNECT:
            self.remote_tcp.write(data)
        elif self.stage == self.STAGE_UDP_ASSOCIATE:
            pass
        elif self.stage == self.STAGE_DESTROY:
            self.close()

    def eof_received(self):
        self.close()

    def pause_writing(self) -> None:
        try:
            self.remote_tcp.transport.pause_reading()
        except AttributeError:
            pass

    def resume_writing(self) -> None:
        self.remote_tcp.transport.resume_reading()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self.close()

    def close(self):
        if self.is_closing:
            return
        self.stage = self.STAGE_DESTROY
        self.is_closing = True

        self.negotiate_task and self.negotiate_task.cancel()
        self.transport and self.transport.close()
        self.remote_tcp and self.remote_tcp.close()
        self.local_udp and self.local_udp.close()

        self.config.ACCESS_LOG and access_logger.debug(
            f"Closed LocalTCP connection from {self.peername}"
        )


class RemoteTCP(asyncio.Protocol):
    def __init__(self, local_tcp, config: Config):
        self.local_tcp = local_tcp
        self.config = config
        self.peername = None
        self.transport = None
        self.is_closing = False

    def write(self, data):
        if not self.transport.is_closing():
            self.transport.write(data)
            print('RemoteTCP written data',data)

    def connection_made(self, transport):
        self.transport = transport
        self.peername = transport.get_extra_info("peername")

        self.config.ACCESS_LOG and access_logger.debug(
            f"Made RemoteTCP connection to {self.peername}"
        )
        #print( 'stage', self.local_tcp.stage)

    def data_received(self, data):
        print('RemoteTCP data_received',data)
        self.local_tcp.write(data)

    def eof_received(self):
        self.close()

    def pause_writing(self) -> None:
        try:
            self.local_tcp.transport.pause_reading()
        except AttributeError:
            pass

    def resume_writing(self) -> None:
        self.local_tcp.transport.resume_reading()

    def connection_lost(self, exc):
        self.close()

    def close(self):
        if self.is_closing:
            return
        self.is_closing = True
        self.transport and self.transport.close()
        self.local_tcp.close()

        self.config.ACCESS_LOG and access_logger.debug(
            f"Closed RemoteTCP connection to {self.peername}"
        )


#class LocalUDP(asyncio.DatagramProtocol):


class RemoteUDP(asyncio.DatagramProtocol):
    def __init__(self, local_udp, local_host_port, config: Config):
        self.local_udp = local_udp
        self.local_host_port = local_host_port
        self.config = config
        self.transport = None
        self.sockname = None
        self.is_closing = False

    def connection_made(self, transport) -> None:
        self.transport = transport
        self.sockname = transport.get_extra_info("sockname")

        self.config.ACCESS_LOG and access_logger.debug(
            f"Made RemoteUDP endpoint at {self.sockname}"
        )

    def write(self, data, host_port):
        if not self.transport.is_closing():
            self.transport.sendto(data, host_port)

    @staticmethod
    def gen_udp_reply_header(remote_host_port: Tuple[str, int], config):
        return ""

    def datagram_received(self, data: bytes, remote_host_port: Tuple[str, int]) -> None:
        try:
            header = self.gen_udp_reply_header(remote_host_port, self.config)
            self.local_udp.write(header + data, self.local_host_port)
        except Exception as e:
            error_logger.warning(
                f"{e} during relaying the response from {remote_host_port}"
            )
            return

    def close(self):
        if self.is_closing:
            return
        self.is_closing = True
        self.transport and self.transport.close()
        self.local_udp = None

        self.config.ACCESS_LOG and access_logger.debug(
            f"Closed RemoteUDP endpoint at {self.sockname}"
        )

    def error_received(self, exc):
        self.close()

    def connection_lost(self, exc):
        self.close()