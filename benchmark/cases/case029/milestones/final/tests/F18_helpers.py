# feature: F18
"""Local Realtime protocol peer; all session behavior runs in the product."""
import asyncio
import base64
import json
from contextlib import asynccontextmanager

# Reuse the suite's source import setup and bounded observation machinery.
from F01_helpers import RecordingModel as _SourceImportSetup
from _helpers import bounded, consume
from velmora.realtime import RealtimeAgent, RealtimeRunner
from velmora.realtime.openai_realtime import OpenAIRealtimeWebSocketModel
from websockets.asyncio.server import serve


class RealtimePeer:
    def __init__(self):
        self.requests = []
        self.changed = asyncio.Condition()
        self.connected = asyncio.Event()
        self.socket = None
        self.failure = None
        self.expected_close_code = 1000

    async def handle(self, socket):
        self.socket = socket
        self.connected.set()
        try:
            async for payload in socket:
                request = json.loads(payload)
                async with self.changed:
                    self.requests.append(request)
                    self.changed.notify_all()
        except Exception as error:
            from websockets.exceptions import ConnectionClosedError
            if isinstance(error, ConnectionClosedError) and socket.close_code == self.expected_close_code:
                return
            self.failure = error
            async with self.changed:
                self.changed.notify_all()

    async def request(self, kind, *, after=0, matches=lambda value: True):
        async def find():
            async with self.changed:
                while True:
                    for value in self.requests[after:]:
                        if value['type'] == kind and matches(value):
                            return value
                    if self.failure is not None:
                        raise self.failure
                    await self.changed.wait()
        return await bounded(find())

    async def send(self, kind, **fields):
        await bounded(self.connected.wait())
        await self.socket.send(json.dumps(dict(type=kind, event_id=fields.pop('event_id', kind), **fields)))

    async def response(self, response_id, *, done=False, usage=None):
        response = dict(id=response_id, object='realtime.response', status='completed' if done else 'in_progress', output=[])
        if usage is not None:
            response['usage'] = usage
        await self.send('response.done' if done else 'response.created', response=response)

    async def audio(self, response_id, item_id, data, *, content_index=0):
        await self.send('response.output_audio.delta', response_id=response_id, item_id=item_id,
                        output_index=0, content_index=content_index, delta=base64.b64encode(data).decode())

    async def delta(self, response_id, item_id, text, *, audio=True):
        await self.send('response.output_audio_transcript.delta' if audio else 'response.output_text.delta',
                        response_id=response_id, item_id=item_id, output_index=0, content_index=0, delta=text)

    async def item(self, item_id, text, *, audio=False):
        await self.send('response.output_item.done', response_id='history-response', output_index=0,
                        item=dict(id=item_id, type='message', role='assistant', status='completed',
                                  content=[dict(type='output_audio', transcript=text) if audio else dict(type='output_text', text=text)]))

    async def call(self, name, call_id, arguments):
        await self.send('response.output_item.done', response_id='tool-response', output_index=0,
                        item=dict(id='item-'+call_id, type='function_call', status='completed',
                                  name=name, call_id=call_id, arguments=json.dumps(arguments)))

    async def fence(self, events, label):
        await self.send('rate_limits.updated', event_id=label, rate_limits=[])
        await events.until(lambda e: e.type == 'raw_model_event' and e.data.type == 'raw_server_event'
                           and e.data.data['event_id'] == label)


class RealtimeEvents:
    def __init__(self, session):
        self.iterator = session.__aiter__()
        self.seen = []

    async def until(self, predicate):
        async def read():
            async for event in self.iterator:
                self.seen.append(event)
                if event.type == 'error':
                    raise AssertionError(f'Unexpected model error: {event.error!r}')
                if predicate(event):
                    return event
            raise AssertionError('Session ended before the required event.')
        return await bounded(read())

    async def read_audio(self, size):
        offset = len(self.seen)
        await self.until(lambda event: event.type == 'audio' and
                         sum(len(item.audio.data) for item in self.seen[offset:] if item.type == 'audio') >= size)
        return b''.join(item.audio.data for item in self.seen[offset:] if item.type == 'audio')

    async def rest(self):
        events = await consume(self.iterator)
        self.seen.extend(events)
        return events


@asynccontextmanager
async def realtime_connection(agent=None, *, settings=None, tracker=None, config=None, runner=None, model=None, call_id=None):
    peer = RealtimePeer()
    async with serve(peer.handle, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        peer.model = model or OpenAIRealtimeWebSocketModel()
        runner = runner or RealtimeRunner(starting_agent=agent or RealtimeAgent(name='Conversation'), model=peer.model,
                                        config={'tracing_disabled': True, 'async_tool_calls': False, **(config or {})})
        options = dict(url=f'ws://127.0.0.1:{port}', headers={}, initial_model_settings=settings or {})
        if call_id is not None:
            options['call_id'] = call_id
        if tracker is not None:
            options['playback_tracker'] = tracker
        async with await runner.run(model_config=options) as session:
            initial = await peer.request('session.update')
            await peer.send('session.updated', session=initial['session'])
            events = RealtimeEvents(session)
            await peer.fence(events, 'ready')
            yield session, peer, events, initial['session']
        if peer.failure is not None:
            raise peer.failure
