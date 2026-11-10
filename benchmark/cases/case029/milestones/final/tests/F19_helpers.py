# feature: F19
"""Local speech protocol services and application-owned voice boundaries."""
import asyncio
import base64
import io
import json
import threading
import wave
from contextlib import contextmanager, asynccontextmanager
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from openai import AsyncOpenAI
from F01_helpers import RecordingModel as _SourceImportSetup
from F18_helpers import RealtimePeer
from F10_helpers import BoundaryStreamModel
from _helpers import invoke_and_consume
from velmora.voice import (VoiceWorkflowBase, STTModel, TTSModel, StreamedTranscriptionSession,
                          VoiceModelProvider, AudioInput, StreamedAudioInput)
from velmora.voice.models.openai_model_provider import OpenAIVoiceModelProvider
from websockets.asyncio.server import serve


class SpeechWorkflow(VoiceWorkflowBase):
    def __init__(self, *, error=None):
        self.inputs = []
        self.error = error

    async def run(self, transcription):
        self.inputs.append(transcription)
        if self.error is not None:
            raise self.error
        # Several streamed text pieces form one reply; all of them must be spoken.
        yield 'Spoken reply: '
        yield transcription
        yield '.'


@contextmanager
def speech_http(*, transcript='The blue parcel', samples=None, audio_for_text=None):
    """Serve transcription and PCM responses over the real HTTP transport."""
    if samples is None:
        samples = np.array([-24001, -803, 0, 912, 21007], dtype=np.int16)
    pcm = samples.tobytes()
    requests, failures = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                raw = self.rfile.read(int(self.headers['Content-Length']))
                if self.path == '/v1/audio/transcriptions':
                    message = BytesParser(policy=default).parsebytes(
                        ('Content-Type: ' + self.headers['Content-Type'] + '\r\n\r\n').encode() + raw)
                    body = {part.get_param('name', header='content-disposition'):
                            part.get_payload(decode=True) for part in message.iter_parts()}
                    with wave.open(io.BytesIO(body['file']), 'rb') as audio:
                        body['samples'] = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').copy()
                    data, content_type = json.dumps({'text': transcript}).encode(), 'application/json'
                elif self.path == '/v1/audio/speech':
                    body = json.loads(raw)
                    data = pcm if audio_for_text is None else audio_for_text(body['input']).tobytes()
                    content_type = 'application/octet-stream'
                else:
                    raise AssertionError('Unexpected speech endpoint: ' + self.path)
                requests.append((self.path, body))
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except BaseException as error:
                failures.append(error)
                raise

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', requests, samples
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'Speech HTTP service did not stop.'
        if failures:
            raise failures[0]


@asynccontextmanager
async def speech_provider(**options):
    with speech_http(**options) as (url, requests, samples):
        async with AsyncOpenAI(api_key='local-service-key', base_url=url, max_retries=0) as client:
            yield OpenAIVoiceModelProvider(openai_client=client), requests, samples


@asynccontextmanager
async def transcription_socket(transcripts):
    """Use the existing protocol recorder with a transcription service driver."""
    peer = RealtimePeer()
    failures = []

    async def handler(socket):
        recorder = asyncio.create_task(peer.handle(socket))
        try:
            await peer.send('session.created', session={})
            update = await peer.request('session.update')
            await peer.send('session.updated', session=update['session'])
            if transcripts:
                await peer.request('input_audio_buffer.append')
            for index, text in enumerate(transcripts):
                await peer.send('input_audio_buffer.committed', item_id=f'turn-{index}')
                await peer.send('conversation.item.input_audio_transcription.completed',
                                item_id=f'turn-{index}', transcript=text)
            await peer.request('input_audio_buffer.clear')
            await peer.send('input_audio_buffer.cleared')
            await recorder
        except Exception as error:
            failures.append(error)
            raise
        finally:
            if not recorder.done():
                recorder.cancel()
            await asyncio.gather(recorder, return_exceptions=True)

    async with serve(handler, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f'ws://127.0.0.1:{port}/v1', peer
    if peer.failure is not None:
        raise peer.failure
    if failures:
        raise failures[0]


async def voice_events(pipeline, audio, *, observation=None, on_event=None):
    async def stream(result):
        async for event in result.stream():
            if on_event is not None:
                on_event(event)
            yield event
    _, events = await invoke_and_consume(pipeline.run, audio,
        stream_from=stream, observation=observation)
    return events


def synthesis_requests(requests):
    return [body for path, body in requests if path == '/v1/audio/speech']


def text_samples(text):
    """Independent service response composable across arbitrary request boundaries."""
    return np.array([sample for character in text for sample in (ord(character), -ord(character))],
                    dtype=np.int16)


def repeated_samples(samples, count):
    assert count > 0, 'No synthesis request delivered.'
    return np.tile(samples, count)


def speech_samples(events):
    chunks = [event.data for event in events if event.type == 'voice_stream_event_audio']
    assert chunks, 'No speech delivered.'
    for chunk in chunks:
        assert chunk is not None
        assert chunk.ndim == 1 or (chunk.ndim == 2 and chunk.shape[1] == 1)
    return np.concatenate([chunk.reshape(-1) for chunk in chunks])


def voice_order(events):
    order = []
    for event in events:
        label = 'audio' if event.type == 'voice_stream_event_audio' else event.event
        if label != 'audio' or not order or order[-1] != 'audio':
            order.append(label)
    return order


class TurnSession(StreamedTranscriptionSession):
    def __init__(self, turns, *, error=None, close_error=None):
        self.turns, self.error, self.close_error = turns, error, close_error
        self.closed = False

    async def transcribe_turns(self):
        for turn in self.turns:
            yield turn
        if self.error is not None:
            raise self.error

    async def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class ApplicationSTT(STTModel):
    model_name = 'application-transcriber'

    def __init__(self, session=None, error=None):
        self.session, self.error = session, error

    async def transcribe(self, input, settings, *privacy):
        if self.error is not None:
            raise self.error
        return 'Application transcription'

    async def create_session(self, input, settings, *privacy):
        if self.error is not None:
            raise self.error
        return self.session


class ApplicationTTS(TTSModel):
    model_name = 'application-synthesizer'

    def __init__(self, *, error=None, delivery_gate=None):
        self.error = error
        self.delivery_gate = delivery_gate
        self.inputs = []

    async def run(self, text, settings):
        self.inputs.append(text)
        yield np.array([1001, -7002], dtype=np.int16).tobytes()
        if self.error is not None:
            if self.delivery_gate is not None:
                await self.delivery_gate.wait()
            raise self.error


class ApplicationVoiceProvider(VoiceModelProvider):
    def __init__(self):
        self.selections = []
        self.stt, self.tts = ApplicationSTT(), ApplicationTTS()

    def get_stt_model(self, model_name):
        self.selections.append(('stt', model_name))
        return self.stt

    def get_tts_model(self, model_name):
        self.selections.append(('tts', model_name))
        return self.tts


class VoiceStreamModel(BoundaryStreamModel):
    def __init__(self, *outputs):
        super().__init__(*outputs)
        self.instructions_seen = []

    async def stream_response(self, system_instructions, *args, **kwargs):
        self.instructions_seen.append(system_instructions)
        async for event in super().stream_response(system_instructions, *args, **kwargs):
            yield event
