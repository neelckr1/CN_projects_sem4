from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.recoco import Timer

log = core.getLogger()

# Example: Block traffic from h1 (10.0.0.1)
BLOCKED_IP = "10.0.0.1"

def request_stats():
    for connection in core.openflow._connections.values():
        connection.send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))

def handle_flowstats(event):
    log.info("Flow Stats:")
    for stat in event.stats:
        if stat.packet_count > 0:
            log.info("Packets: %s Bytes: %s", stat.packet_count, stat.byte_count)

def packet_in_handler(event):
    packet = event.parsed
    ip_packet = packet.find('ipv4')

    if ip_packet:
        src_ip = str(ip_packet.srcip)

       
        if src_ip == BLOCKED_IP:
            log.info("Blocked traffic from %s", src_ip)
            return  # Drop packet

  
    msg = of.ofp_packet_out()
    msg.data = event.ofp
    msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
    event.connection.send(msg)

def launch():
    core.openflow.addListenerByName("PacketIn", packet_in_handler)
    core.openflow.addListenerByName("FlowStatsReceived", handle_flowstats)
    Timer(5, request_stats, recurring=True)
