# feature: F17
"""Acceptance checks for application TUN/TAP packet channels."""
import velnora
import pytest

from _helpers import bounded, run_async
from F08_helpers import application_stream, channel_connection, delivery_fence
from F17_helpers import (PacketEndpoint, packet_connection, packet_material,
                         packet_transfer)


def test_packet_selection_and_bidirectional_boundaries():
    async def scenario():
        ip_packets, frames = packet_material()
        async with packet_connection() as (connection, policy, _):
            # Both channel kinds must carry both interface selection forms.
            for kind, create, packets in (
                    ('tun', connection.create_tun, ip_packets),
                    ('tap', connection.create_tap, frames)):
                for unit in (None, 9):
                    if unit is None:
                        channel, endpoint = await bounded(create(PacketEndpoint))
                    else:
                        channel, endpoint = await bounded(create(PacketEndpoint, unit))
                    try:
                        requested_kind, requested_unit, peer = await bounded(policy.requests.get())
                        assert (requested_kind, requested_unit) == (kind, unit)
                        await bounded(peer.started.wait())
                        # Different bursts in each direction exclude an echo-only
                        # implementation; repeated packets must not be deduplicated.
                        await packet_transfer(channel, peer, packets + [packets[0]])
                        await packet_transfer(peer.channel, endpoint,
                                              list(reversed(packets)) + [packets[-1]])
                    finally:
                        channel.close()
                        await bounded(channel.wait_closed())
        return 'test_packet_selection_and_bidirectional_boundaries'
    assert run_async(scenario()) == 'test_packet_selection_and_bidirectional_boundaries'


def test_packet_refusal_unsupported_mode_and_independent_close():
    async def scenario():
        # This peer inherits the product's unchanged default packet policy.
        async with channel_connection() as (connection, ready):
            writer, reader, _, _ = await application_stream(
                connection, ready, 'echo', encoding=None)
            await delivery_fence(writer, reader)
            for create in (connection.create_tun, connection.create_tap):
                with pytest.raises(velnora.ChannelOpenError):
                    await bounded(create(PacketEndpoint))
                await delivery_fence(writer, reader)

        async with packet_connection() as (connection, policy, ready):
            writer, reader, _, _ = await application_stream(
                connection, ready, 'echo', encoding=None)
            tun, tun_endpoint = await bounded(connection.create_tun(PacketEndpoint, 4))
            kind, unit, tun_peer = await bounded(policy.requests.get())
            assert (kind, unit) == ('tun', 4)
            await bounded(tun_peer.started.wait())
            tap, tap_endpoint = await bounded(connection.create_tap(PacketEndpoint, 5))
            _, _, tap_peer = await bounded(policy.requests.get())
            await bounded(tap_peer.started.wait())
            ip_packets, frames = packet_material()
            # Establish a live baseline before exercising refusal and closure.
            await packet_transfer(tun, tun_peer, ip_packets)
            await packet_transfer(tun_peer.channel, tun_endpoint, list(reversed(ip_packets)))
            await packet_transfer(tap_peer.channel, tap_endpoint, frames)
            # A tunnel mode other than layer 2 or layer 3 is refused even while
            # the application would accept every packet request, and the
            # application is not asked to accept it.
            assert policy.requests.empty()
            invalid = connection.create_tuntap_channel()
            with pytest.raises(velnora.ChannelOpenError):
                await bounded(invalid.open(PacketEndpoint, 32, None))
            await delivery_fence(writer, reader)
            assert policy.requests.empty()
            policy.allowed = False
            for kind, create in (('tun', connection.create_tun),
                                 ('tap', connection.create_tap)):
                with pytest.raises(velnora.ChannelOpenError):
                    await bounded(create(PacketEndpoint, 11))
                assert (await bounded(policy.requests.get()))[:2] == (kind, 11)
            tun.close()
            await bounded(tun.wait_closed())
            await bounded(tun_endpoint.closed.wait())
            await bounded(tun_peer.closed.wait())
            await packet_transfer(tap, tap_peer, frames)
            await packet_transfer(tap_peer.channel, tap_endpoint, list(reversed(frames)))
            await delivery_fence(writer, reader)
            tap.close()
            await bounded(tap.wait_closed())
            await bounded(tap_peer.closed.wait())
            await delivery_fence(writer, reader)
        return 'test_packet_refusal_unsupported_mode_and_independent_close'
    assert run_async(scenario()) == 'test_packet_refusal_unsupported_mode_and_independent_close'
