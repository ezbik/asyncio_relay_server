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


def query(config, name):
    resolver=config.resolver
    def _q(name, query_type):
        try:
            answers = resolver.query(name, query_type)
            for rdata in answers: 
                return rdata.to_text()
        except:
            return False
        
    RESOLVING_ORDER=config.RESOLVING_ORDER
    if RESOLVING_ORDER == 4:  ret= _q(name, 'A') 
    if RESOLVING_ORDER == 6:  ret= _q(name, 'AAAA') 
    if RESOLVING_ORDER == 64: ret= _q(name, 'AAAA') or _q(name, 'AAAA')
    if RESOLVING_ORDER == 46: ret= _q(name, 'A') or _q(name, 'AAAA')
    return ret

        
#def acl(config, DST_ADDR):
#    for banned_dst in config.BANNED_DST :
#        if re.search(rf'\.?{banned_dst}$' , DST_ADDR):
#            return -1

class LocalTCP(asyncio.Protocol):
    STAGE_NEGOTIATE = 0
    STAGE_CONNECT = 1
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


    def write(self, data):
        if not self.transport.is_closing():
            self.transport.write(data)

    def connection_made(self, transport):
        self.transport = transport
        self.peername = transport.get_extra_info("peername")
        self.stream_reader.set_transport(transport)
        self.config.ACCESS_LOG and access_logger.debug(
            f"Made LocalTCP connection from {self.peername}"
        )
        #loop = asyncio.get_event_loop()
        #self.negotiate_task = loop.create_task(self.process_header_and_feed_the_rest())
        self.stage = self.STAGE_NEGOTIATE

    async def process_header_and_feed_the_rest2(self, data):
            #print('start negotiate')
            data_leftover=b'' # something that left after reading headers.
            buf=data[0:6]
            try:
                # Step 1
                # The client sends a MPROXY header.
                if buf != b'MPROXY' :
                    raise NoVersionAllowed(f"Received wrong header: {buf}")
                else:
                    HEADER=buf

                i=6-1
                # The client send rest of the header ending with \r\n
                while True:
                    i+=1
                    buf =  data[i:i+1]
                    #print(buf)
                    if buf == b'\r':
                        i+=1   # read \n
                        break
                    else:
                        HEADER+=buf

                HEADER=HEADER.decode()
                self.config.ACCESS_LOG and access_logger.debug(
                    f'Incoming Relay request. Header ,,{HEADER}``'
                )

                data_leftover= data[len(HEADER)+2:] # something that left after reading header
                #print('data_leftover', data_leftover)

                try:
                    _, PROTO, DST_ADDR, DST_PORT = HEADER.split(' ')
                except:
                    raise CommandExecError(f"Can't parse HEADER: {HEADER}")

                #print('header processing stop;')

                self.config.ACCESS_LOG and access_logger.info(
                    f'Incoming Relay request to {PROTO}://{DST_ADDR}:{DST_PORT}'
                )


                # resolve if needed.
                if not ':' in DST_ADDR or not re.match(r'^\d', DST_ADDR):
                    HNAME=DST_ADDR

                    self.config.ACCESS_LOG and access_logger.debug(
                        f'Resolving remote name {HNAME}'
                    )
                    DST_ADDR = query(self.config, HNAME )
                    if not DST_ADDR:
                        raise CommandExecError(f"Can't resolve hostname {HNAME}")
                    self.config.ACCESS_LOG and access_logger.debug(
                        f'{HNAME} resolved to {DST_ADDR}'
                    )
                # Now DST_ADDR is Ipv4/Ipv6. 

                # Step 2
                # The server handles the command and returns a reply.
                if PROTO == 'TCP':
                    self.stage = self.STAGE_CONNECT
                    TCP_CONNECT_TIMEOUT=2
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

                        if ':' in DST_ADDR :
                            bind_addr, bind_port, _, _ = remote_tcp_transport.get_extra_info( "sockname")
                        else:
                            bind_addr, bind_port = remote_tcp_transport.get_extra_info( "sockname")

                        self.config.ACCESS_LOG and access_logger.debug(
                            f"Talking to the remote side from local ip {bind_addr} local port {bind_port}"
                        )

                        self.config.ACCESS_LOG and access_logger.info(
                            f"Established TCP stream between"
                            f" {self.peername} and {self.remote_tcp.peername}"
                        )

                    if data_leftover:
                        try:
                            self.remote_tcp.write(data_leftover)
                        except Exception as e:
                            raise CommandExecError(f"Could not write data leftover to the remote side, {e}")
                            self.close()
                    else:
                        pass


                elif PROTO == 'UDP' :
                    self.stage = self.STAGE_CONNECT
                    try:
                        loop = asyncio.get_event_loop()
                        task = loop.create_datagram_endpoint(
                            lambda: RemoteUDP(self,  self.config),
                            #local_addr=("0.0.0.0", 0),
                            remote_addr=(DST_ADDR, DST_PORT),
                        )
                        remote_udp_transport, remote_udp = await asyncio.wait_for(task, 5)
                    except Exception as e:
                        raise CommandExecError(
                            f"General socks server failure occurred {e} "
                        ) from None
                    else:
                        self.remote_udp = remote_udp

                        if ':' in DST_ADDR :
                            bind_addr, bind_port, _, _ = remote_udp_transport.get_extra_info( "sockname")
                        else:
                            bind_addr, bind_port = remote_udp_transport.get_extra_info( "sockname")

                        self.config.ACCESS_LOG and access_logger.info(
                            f"Established UDP relay for client {self.peername} "
                            f"at local side {bind_addr,bind_port}"
                        )
                    if data_leftover:
                        try:
                            self.remote_udp.write(data_leftover)
                        except Exception as e:
                            raise CommandExecError(f"Could not write data leftover to the remote side, {e}")
                            self.close()
                    else:
                        pass
                else:
                    raise NoCommandAllowed(f"Unsupported CMD value: {CMD}")


            except Exception as e:
                error_logger.warning(f"{e} during the negotiation with {self.peername}")
                self.close()
            

    async def feed_remote_tcp(self, data):
        #print('feed_remote_tcp', data[:100])
        loop = asyncio.get_event_loop()
        try:
            while True:
                #wait till self.remote_tcp is ready
                if self.remote_tcp:
                    #print('remote tcp ready')
                    self.remote_tcp.write(data)
                    return
                else:
                    await asyncio.sleep(0.1)
        except Exception as e:
            self.config.ACCESS_LOG and access_logger.debug(f"Could not write data to the remote side: {e}")
            self.close()

        
    def data_received(self, data):
        #print(f'LocalTCP: at stage {self.stage} rcvd data {data[:100]} , length {len(data)}')
        if self.stage == self.STAGE_NEGOTIATE:
            loop = asyncio.get_event_loop()
            pro_task = loop.create_task(self.process_header_and_feed_the_rest2(data))
        elif self.stage == self.STAGE_CONNECT:
            #print('= sending directly to remote side')
            loop = asyncio.get_event_loop()
            feed_task = loop.create_task(self.feed_remote_tcp(data))
            #self.remote_tcp.write(data)

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
        #self.local_udp and self.local_udp.close()

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
            #print('RemoteTCP written data',data[:100],'length',len(data))

    def connection_made(self, transport):
        self.transport = transport
        self.peername = transport.get_extra_info("peername")

        self.config.ACCESS_LOG and access_logger.debug(
            f"Made RemoteTCP connection to {self.peername}"
        )

    def data_received(self, data):
        #print('RemoteTCP data_received',data)
        self.local_tcp.write(data)

    def eof_received(self):
        #print('RemoteTCP eof_received')
        self.close()

    def pause_writing(self) -> None:
        try:
            self.local_tcp.transport.pause_reading()
        except AttributeError:
            pass

    def resume_writing(self) -> None:
        self.local_tcp.transport.resume_reading()

    def connection_lost(self, exc):
        #print('RemoteTCP connection_lost')
        self.close()

    def close(self):
        #print('RemoteTCP close')
        if self.is_closing:
            return
        self.is_closing = True
        self.transport and self.transport.close()
        self.local_tcp.close()

        self.config.ACCESS_LOG and access_logger.debug(
            f"Closed RemoteTCP connection to {self.peername}"
        )


class RemoteUDP(asyncio.DatagramProtocol):
    def __init__(self, local_tcp, config: Config):
        self.local_tcp = local_tcp
        self.config = config
        self.transport = None
        self.sockname = None
        self.is_closing = False

    def connection_made(self, transport) -> None:
        self.transport = transport
        self.sockname = transport.get_extra_info("sockname")

        self.config.ACCESS_LOG and access_logger.debug(
            f"Made RemoteUDP at local endpoint {self.sockname}"
        )

    def write(self, data):
        if not self.transport.is_closing():
            self.transport.sendto(data)

    def datagram_received(self, data: bytes, remote_host_port: Tuple[str, int]) -> None:
        try:
            self.local_tcp.write( data)
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
        self.local_tcp.close
        self.local_tcp = None

        self.config.ACCESS_LOG and access_logger.debug(
            f"Closed RemoteUDP endpoint at {self.sockname}"
        )

    def error_received(self, exc):
        self.close()

    def connection_lost(self, exc):
        self.close()
